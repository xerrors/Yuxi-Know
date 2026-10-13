import re
from typing import Literal

from fastapi import Response, Form, APIRouter, Body, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.api.dependencies.auth import get_admin_user, get_db, get_required_user

# OIDC 认证相关导入
from yuxi.api.routers.identity.oidc import (
    get_oidc_config_handler,
    oidc_callback_handler,
    oidc_exchange_code_handler,
    oidc_login_url_handler,
    oidc_logout_handler,
)
from yuxi.api.uploads import read_upload_with_limit
from yuxi.infrastructure.minio import upload_image_to_minio
from yuxi.infrastructure.minio.client import normalize_public_minio_url
from yuxi.modules.identity.models import User
from yuxi.modules.identity.repositories.departments import DepartmentRepository
from yuxi.modules.identity.repositories.users import UserRepository
from yuxi.modules.identity.security import AuthUtils
from yuxi.modules.identity.services.administration import (
    IdentityConflictError,
    SystemAlreadyInitializedError,
    initialize_system_admin,
    list_managed_users_page,
    lock_member_management,
)
from yuxi.modules.identity.services.cli_auth import (
    CLI_AUTH_POLL_INTERVAL_SECONDS,
    CLI_AUTH_SESSION_TTL_SECONDS,
    CLIAuthError,
    approve_cli_auth_session,
    create_cli_auth_session,
    exchange_cli_auth_token,
    get_cli_auth_session_for_user,
)
from yuxi.modules.identity.services.login_limits import extract_client_ip
from yuxi.modules.identity.services.password_login import PasswordLoginRejected, login_with_password
from yuxi.modules.identity.services.usernames import generate_unique_uid, is_valid_phone_number, validate_username

# 创建路由器
auth = APIRouter(prefix="/auth", tags=["authentication"])


# 请求和响应模型
class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    username: str
    uid: str  # 用于登录的user_id
    phone_number: str | None = None
    avatar: str | None = None
    role: str
    department_id: int | None = None
    department_name: str | None = None


class UserCreate(BaseModel):
    username: str
    password: str = Field(min_length=8)
    role: Literal["user", "admin", "superadmin"] = "user"
    phone_number: str | None = None
    department_id: int | None = None


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "admin", "superadmin"] | None = None
    username: str | None = None
    password: str | None = Field(default=None, min_length=8)
    phone_number: str | None = None
    avatar: str | None = None
    department_id: int | None = None


class UserProfileUpdate(BaseModel):
    username: str | None = None
    phone_number: str | None = None


class UserResponse(BaseModel):
    id: int
    username: str
    uid: str
    phone_number: str | None = None
    avatar: str | None = None
    role: str
    department_id: int | None = None
    department_name: str | None = None  # 部门名称
    created_at: str
    last_login: str | None = None


class ManagedUserResponse(UserResponse):
    """用户管理列表中的身份类型与 APP 来源。"""

    user_kind: Literal["human", "end_user"]
    app_id: str | None = None


class UserPageResponse(BaseModel):
    items: list[ManagedUserResponse]
    total: int
    limit: int
    offset: int


class UserAccessOption(BaseModel):
    uid: str
    username: str
    role: str
    department_id: int | None = None
    department_name: str | None = None


class InitializeAdmin(BaseModel):
    uid: str  # 直接输入用户ID
    password: str = Field(min_length=8)
    phone_number: str | None = None


class UsernameValidation(BaseModel):
    username: str


class UidGeneration(BaseModel):
    username: str
    uid: str
    is_available: bool


class OIDCConfigResponse(BaseModel):
    """OIDC 配置响应"""

    enabled: bool
    login_url: str | None = None
    provider_name: str | None = "OIDC登录"


class OIDCLoginResponse(BaseModel):
    """OIDC 登录响应"""

    access_token: str
    token_type: str
    user_id: int
    username: str
    uid: str
    phone_number: str | None = None
    avatar: str | None = None
    role: str
    department_id: int | None = None
    department_name: str | None = None


class CLIAuthSessionCreate(BaseModel):
    key_name: str | None = Field(default=None, max_length=100)


class CLIAuthTokenRequest(BaseModel):
    device_code: str


class CLIAuthSessionCreateResponse(BaseModel):
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class CLIAuthSessionResponse(BaseModel):
    user_code: str
    status: str
    key_name: str
    created_at: str
    expires_at: str
    approved_at: str | None = None


class CLIAuthApproveResponse(BaseModel):
    user_code: str
    status: str
    approved_at: str | None = None


class CLIAuthTokenResponse(BaseModel):
    api_key: dict
    secret: str
    user: dict


# =============================================================================
# === 工具函数 ===
# =============================================================================


def _raise_cli_auth_error(exc: CLIAuthError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.code, "message": exc.message},
    ) from exc


# 路由：登录获取令牌
# =============================================================================
# === 认证分组 ===
# =============================================================================


@auth.post("/token", response_model=Token)
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """适配密码登录表单、拒绝原因与 HTTP 响应。"""
    try:
        result = await login_with_password(db, form_data.username, form_data.password, extract_client_ip(request))
    except PasswordLoginRejected as error:
        headers = {"WWW-Authenticate": "Bearer"}
        if error.reason == "rate_limited":
            code, detail = 429, "登录尝试过于频繁，请稍后再试"
            headers = {"Retry-After": str(error.remaining_seconds)}
        elif error.reason == "deleted":
            code, detail = 403, "该账户已注销"
        elif error.reason in {"locked", "newly_locked"}:
            code = 423
            remaining = error.remaining_seconds
            detail = (
                f"登录被锁定，请等待 {remaining} 秒后再试" if error.reason == "locked" else f"由于多次登录失败，账户已被锁定 {remaining} 秒"
            )
            headers["X-Lock-Remaining"] = str(remaining)
        else:
            code = 401
            detail = "登录标识或密码错误" if error.reason == "unknown_account" else "用户名或密码错误"
        raise HTTPException(status_code=code, detail=detail, headers=headers) from error

    user = result.user
    access_token = result.access_token
    department_name = result.department_name
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
        "uid": user.uid,
        "phone_number": user.phone_number,
        "avatar": normalize_public_minio_url(user.avatar),
        "role": user.role,
        "department_id": user.department_id,
        "department_name": department_name,
    }


# =============================================================================
# === CLI 浏览器登录授权分组 ===
# =============================================================================


@auth.post("/cli/sessions", response_model=CLIAuthSessionCreateResponse)
async def create_cli_session(data: CLIAuthSessionCreate, db: AsyncSession = Depends(get_db)):
    session, device_code = await create_cli_auth_session(db, key_name=data.key_name)
    return CLIAuthSessionCreateResponse(
        device_code=device_code,
        user_code=session.user_code,
        verification_uri="/auth/cli/authorize",
        expires_in=CLI_AUTH_SESSION_TTL_SECONDS,
        interval=CLI_AUTH_POLL_INTERVAL_SECONDS,
    )


@auth.get("/cli/sessions/{user_code}", response_model=CLIAuthSessionResponse)
async def get_cli_session(
    user_code: str,
    _current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        session = await get_cli_auth_session_for_user(db, user_code)
    except CLIAuthError as exc:
        _raise_cli_auth_error(exc)
    return CLIAuthSessionResponse(**session.to_dict())


@auth.post("/cli/sessions/{user_code}/approve", response_model=CLIAuthApproveResponse)
async def approve_cli_session(
    user_code: str,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        session = await approve_cli_auth_session(db, user_code, current_user)
    except CLIAuthError as exc:
        _raise_cli_auth_error(exc)
    return CLIAuthApproveResponse(**session.to_dict())


@auth.post("/cli/sessions/token", response_model=CLIAuthTokenResponse)
async def exchange_cli_session_token(data: CLIAuthTokenRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await exchange_cli_auth_token(db, data.device_code)
    except CLIAuthError as exc:
        _raise_cli_auth_error(exc)


# 路由：校验是否需要初始化管理员
@auth.get("/check-first-run")
async def check_first_run():
    is_first_run = await UserRepository().is_first_run()
    return {"first_run": is_first_run}


# 路由：初始化管理员账户
@auth.post("/initialize", response_model=Token)
async def initialize_admin(admin_data: InitializeAdmin, db: AsyncSession = Depends(get_db)):
    # 验证用户ID格式（只支持字母数字和下划线）
    if not re.match(r"^[a-zA-Z0-9_]+$", admin_data.uid):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户ID只能包含字母、数字和下划线",
        )

    if len(admin_data.uid) < 3 or len(admin_data.uid) > 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户ID长度必须在3-20个字符之间",
        )

    # 验证手机号格式（如果提供了）
    if admin_data.phone_number and not is_valid_phone_number(admin_data.phone_number):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="手机号格式不正确")

    try:
        created = await initialize_system_admin(
            db,
            uid=admin_data.uid,
            password=admin_data.password,
            phone_number=admin_data.phone_number,
        )
    except SystemAlreadyInitializedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except IdentityConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    new_admin = created.admin

    # 生成访问令牌
    token_data = {"sub": str(new_admin.id)}
    access_token = AuthUtils.create_access_token(token_data)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": new_admin.id,
        "username": new_admin.username,
        "uid": new_admin.uid,
        "phone_number": new_admin.phone_number,
        "avatar": new_admin.avatar,
        "role": new_admin.role,
    }


# 路由：获取当前用户信息
# =============================================================================
# === 用户信息分组 ===
# =============================================================================


@auth.get("/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_required_user), db: AsyncSession = Depends(get_db)):
    """获取当前登录用户的个人信息"""
    user_dict = current_user.to_dict()

    if current_user.department_id:
        user_dict["department_name"] = await DepartmentRepository(db).get_name_by_id(current_user.department_id)

    return user_dict


# 路由：更新个人资料
@auth.put("/profile", response_model=UserResponse)
async def update_profile(
    profile_data: UserProfileUpdate,
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """更新当前用户的个人资料"""
    user_repository = UserRepository(db)

    # 更新用户名（仅允许修改显示名，不修改 user_id）
    if profile_data.username is not None:
        # 验证用户名格式
        is_valid, error_msg = validate_username(profile_data.username)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg,
            )

        # 检查用户名是否已被其他用户使用
        existing_user = await user_repository.get_by_username(profile_data.username, exclude_user_id=current_user.id)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户名已存在",
            )

        current_user.username = profile_data.username

    # 更新手机号
    if profile_data.phone_number is not None:
        # 如果手机号不为空，验证格式
        if profile_data.phone_number and not is_valid_phone_number(profile_data.phone_number):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="手机号格式不正确")

        # 检查手机号是否已被其他用户使用
        if profile_data.phone_number:
            existing_phone = await user_repository.get_by_phone_excluding(profile_data.phone_number, current_user.id)
            if existing_phone:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="手机号已被其他用户使用")

        current_user.phone_number = profile_data.phone_number

    await user_repository.save(current_user)

    await db.commit()

    return current_user.to_dict()


# 路由：创建新用户（管理员权限）
# =============================================================================
# === 用户管理分组 ===
# =============================================================================


@auth.post("/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """创建新用户（管理员权限）"""
    try:
        current_user, _ = await lock_member_management(db, actor_id=current_user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    user_repo = UserRepository(db)

    # 验证用户名
    is_valid, error_msg = validate_username(user_data.username)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        )

    # 检查用户名是否已存在
    if await user_repo.get_by_username(user_data.username) is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在",
        )

    # 检查手机号是否已存在（如果提供了）
    if user_data.phone_number:
        if await user_repo.exists_by_phone(user_data.phone_number):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="手机号已存在",
            )

    # 生成唯一的 uid
    existing_uids = await user_repo.get_all_uids()
    uid = generate_unique_uid(user_data.username, existing_uids)

    # 创建新用户
    hashed_password = AuthUtils.hash_password(user_data.password)

    # 检查角色权限
    # 管理员只能创建普通用户
    if current_user.role == "admin" and user_data.role != "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理员只能创建普通用户账户",
        )

    # 部门分配逻辑
    if current_user.role == "superadmin":
        # 超级管理员创建用户时，使用指定的部门或默认部门
        department_id = user_data.department_id
        if department_id is None:
            # 获取默认部门
            dept_repo = DepartmentRepository(db)
            departments = await dept_repo.list_departments()
            default_dept = next((d for d in departments if d.name == "默认部门"), None)
            department_id = default_dept.id if default_dept else None
    else:
        # 普通管理员创建用户时，自动继承该管理员的部门
        department_id = current_user.department_id
        if department_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="管理员必须属于部门才能创建用户",
            )
        # 非超级管理员不能指定部门
        if user_data.department_id is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="普通管理员不能指定部门",
            )

    new_user = await user_repo.create(
        {
            "username": user_data.username,
            "uid": uid,
            "phone_number": user_data.phone_number,
            "password_hash": hashed_password,
            "role": user_data.role,
            "department_id": department_id,
        }
    )

    await db.commit()

    return new_user.to_dict()


@auth.get("/users/page", response_model=UserPageResponse)
async def read_users_page(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None, max_length=100),
    department_id: int | None = Query(None, ge=1),
    role: Literal["superadmin", "admin", "user"] | None = None,
    user_kind: Literal["human", "end_user", "all"] = "human",
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """分页查询当前管理员可管理的有效用户。"""
    return await list_managed_users_page(
        db,
        offset=offset,
        limit=limit,
        is_superadmin=current_user.role == "superadmin",
        visible_department_id=current_user.department_id,
        department_id=department_id,
        role=role,
        search=search.strip() if search else None,
        user_kind=None if user_kind == "all" else user_kind,
    )


# 路由：获取所有用户（管理员权限）
@auth.get("/users", response_model=list[UserResponse])
async def read_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    user_repo = UserRepository(db)

    # 部门隔离逻辑
    if current_user.role == "superadmin":
        # 超级管理员可以看到所有用户
        users_with_dept = await user_repo.list_with_department(skip=skip, limit=limit)
    else:
        # 普通管理员只能看到本部门用户
        users_with_dept = await user_repo.list_with_department(skip=skip, limit=limit, department_id=current_user.department_id)

    users = []
    for user, dept_name in users_with_dept:
        user_dict = user.to_dict()
        user_dict["department_name"] = dept_name
        users.append(user_dict)
    return users


def _ensure_user_in_current_department(current_user: User, target_user: User) -> None:
    if current_user.role == "superadmin":
        return
    if target_user.department_id != current_user.department_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能管理本部门用户",
        )


@auth.get("/users/access-options", response_model=list[UserAccessOption])
async def read_user_access_options(
    skip: int = 0,
    limit: int = 1000,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    users_with_dept = await UserRepository(db).list_with_department(skip=skip, limit=limit)
    return [
        {
            "uid": user.uid,
            "username": user.username,
            "role": user.role,
            "department_id": user.department_id,
            "department_name": dept_name,
        }
        for user, dept_name in users_with_dept
    ]


# 路由：获取特定用户信息（管理员权限）
@auth.get("/users/{user_id}", response_model=UserResponse)
async def read_user(
    user_id: int,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    user = await UserRepository(db).get_active_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    _ensure_user_in_current_department(current_user, user)
    return user.to_dict()


# 路由：更新用户信息（管理员权限）
@auth.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    user_repository = UserRepository(db)
    try:
        current_user, user = await lock_member_management(db, actor_id=current_user.id, member_id=user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    _ensure_user_in_current_department(current_user, user)

    # 检查权限
    if user.role == "superadmin" and current_user.role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有超级管理员才能修改超级管理员账户",
        )

    if current_user.role == "admin":
        if user.role != "user":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="管理员只能修改普通用户账户",
            )

    if current_user.role != "superadmin" and user_data.password is not None:
        raise HTTPException(status_code=403, detail="普通管理员不能重置已有成员密码")
    if user_data.role is not None:
        if current_user.role != "superadmin":
            raise HTTPException(status_code=403, detail="只有系统管理员可以提升角色")
        from yuxi.modules.identity.services.administration import promote_user_role

        try:
            await promote_user_role(db, user=user, role=user_data.role)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    # 更新信息
    if user_data.username is not None:
        # 检查用户名是否已被其他用户使用
        existing_user = await user_repository.get_by_username(user_data.username, exclude_user_id=user_id)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户名已存在",
            )
        user.username = user_data.username

    if user_data.password is not None:
        user.password_hash = AuthUtils.hash_password(user_data.password)

    if user_data.phone_number is not None:
        user.phone_number = user_data.phone_number

    if user_data.avatar is not None:
        user.avatar = user_data.avatar

    # 部门修改权限控制（只有超级管理员可以修改用户部门）
    if user_data.department_id is not None and user_data.department_id != user.department_id:
        if current_user.role != "superadmin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有超级管理员才能修改用户部门",
            )

        user.department_id = user_data.department_id

    await user_repository.save(user)

    await db.commit()

    return user.to_dict()


# 路由：删除用户（管理员权限）
@auth.delete("/users/{user_id}", response_model=dict)
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    user_repository = UserRepository(db)
    try:
        current_user, user = await lock_member_management(db, actor_id=current_user.id, member_id=user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    _ensure_user_in_current_department(current_user, user)

    if current_user.role == "admin" and user.role != "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理员只能删除普通用户账户",
        )

    # 不能删除自己的账户
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能删除自己的账户",
        )

    # 检查是否已经被删除
    if user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该用户已经被删除",
        )

    try:
        await user_repository.delete_for_admin(user)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await db.commit()

    return {"success": True, "message": "用户已删除"}


# 路由：验证用户名并生成user_id
@auth.post("/validate-username", response_model=UidGeneration)
async def validate_username_and_generate_uid(
    validation_data: UsernameValidation,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """验证用户名格式并生成可用的user_id"""
    # 验证用户名格式
    is_valid, error_msg = validate_username(validation_data.username)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        )

    # 检查用户名是否已存在
    user_repository = UserRepository(db)
    existing_user = await user_repository.get_by_username(validation_data.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在",
        )

    # 生成唯一的 uid
    existing_uids = await user_repository.get_all_uids()
    uid = generate_unique_uid(validation_data.username, existing_uids)

    return UidGeneration(username=validation_data.username, uid=uid, is_available=True)


# 路由：检查 uid 是否可用
@auth.get("/check-uid/{uid}")
async def check_uid_availability(
    uid: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """检查 uid 是否可用"""
    return {"uid": uid, "is_available": not await UserRepository(db).exists_by_uid(uid)}


# 路由：上传用户头像
@auth.post("/upload-avatar")
async def upload_user_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_required_user),
    db: AsyncSession = Depends(get_db),
):
    """上传用户头像"""
    try:
        content = await read_upload_with_limit(
            file,
            max_size_bytes=5 * 1024 * 1024,
            too_large_message="文件大小不能超过5MB",
        )
        avatar_url = await upload_image_to_minio(
            content,
            object_prefix=f"avatar/{current_user.id}",
            max_size_bytes=5 * 1024 * 1024,
            too_large_message="文件大小不能超过5MB",
        )

        current_user.avatar = avatar_url
        await UserRepository(db).save(current_user)
        await db.commit()

        return {"success": True, "avatar_url": avatar_url, "message": "头像上传成功"}

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"头像上传失败: {str(e)}")


# =============================================================================
# === OIDC 认证分组 ===
# =============================================================================


@auth.get("/oidc/config", response_model=OIDCConfigResponse)
async def get_oidc_config():
    """获取 OIDC 配置（供前端使用）"""
    return await get_oidc_config_handler()


@auth.get("/oidc/login-url")
async def get_oidc_login_url(request: Request, response: Response):
    """获取 OIDC 登录 URL"""
    return await oidc_login_url_handler(request, response)


@auth.get("/oidc/callback", response_class=RedirectResponse)
async def oidc_callback(request: Request, code: str = Query(default="", max_length=2048), state: str = Query(default="", max_length=128),
                        error: str = Query(default="", max_length=128), db: AsyncSession = Depends(get_db)):
    """处理 OIDC 回调 - 重定向到前端 Vue 路由"""
    return await oidc_callback_handler(code, state, request, db, error)


@auth.post("/oidc/exchange-code", response_model=OIDCLoginResponse)
async def oidc_exchange_code(request: Request, response: Response, code: str = Body(..., embed=True, min_length=1, max_length=128),
                             db: AsyncSession = Depends(get_db)):
    """使用一次性 code 交换 OIDC 登录数据"""
    return await oidc_exchange_code_handler(code, request, response, db)


@auth.post("/oidc/logout")
async def oidc_logout(request: Request, response: Response, user=Depends(get_required_user), db=Depends(get_db)):
    """当前用户只撤销 Yuxi 本地凭据，保留认证中心共享会话。"""
    response.headers["Cache-Control"] = "no-store"
    return await oidc_logout_handler(request, db)


@auth.post("/oidc/backchannel-logout")
async def oidc_backchannel_logout(logout_token: str = Form(..., max_length=16384), db=Depends(get_db)):
    """接收认证中心签名的标准登出通知。"""
    from yuxi.modules.identity.services.oidc import OIDCService
    from yuxi.shared.errors import DomainError

    try:
        await OIDCService(db).backchannel_logout(logout_token)
    except DomainError as exc:
        raise HTTPException(400, "OIDC 登出通知无效") from exc
    return Response(status_code=200, headers={"Cache-Control": "no-store"})
