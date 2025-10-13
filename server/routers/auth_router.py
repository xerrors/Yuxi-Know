import re

from fastapi import APIRouter, Depends, HTTPException, Request, status, UploadFile, File
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.storage.db.manager import db_manager
from src.storage.db.models import User
from server.utils.auth_middleware import get_admin_user, get_current_user, get_db, get_required_user
from server.utils.auth_utils import AuthUtils
from server.utils.user_utils import generate_unique_user_id, validate_username, is_valid_phone_number
from server.utils.common_utils import log_operation
from src.storage.minio import upload_image_to_minio
from src.utils.datetime_utils import utc_now

# 创建路由器
auth = APIRouter(prefix="/auth", tags=["authentication"])


# 请求和响应模型
class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    username: str
    user_id_login: str  # 用于登录的user_id
    phone_number: str | None = None
    avatar: str | None = None
    role: str


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "user"
    phone_number: str | None = None


class UserUpdate(BaseModel):
    username: str | None = None
    password: str | None = None
    role: str | None = None
    phone_number: str | None = None
    avatar: str | None = None


class UserProfileUpdate(BaseModel):
    username: str | None = None
    phone_number: str | None = None


class UserResponse(BaseModel):
    id: int
    username: str
    user_id: str
    phone_number: str | None = None
    avatar: str | None = None
    role: str
    created_at: str
    last_login: str | None = None


class InitializeAdmin(BaseModel):
    user_id: str  # 直接输入用户ID
    password: str
    phone_number: str | None = None


class UsernameValidation(BaseModel):
    username: str


class UserIdGeneration(BaseModel):
    username: str
    user_id: str
    is_available: bool


# =============================================================================
# === 工具函数 ===
# =============================================================================


# 路由：登录获取令牌
# =============================================================================
# === 认证分组 ===
# =============================================================================


@auth.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # 查找用户 - 支持user_id和phone_number登录
    login_identifier = form_data.username  # OAuth2表单中的username字段作为登录标识符

    # 尝试通过user_id查找
    user = db.query(User).filter(User.user_id == login_identifier).first()

    # 如果通过user_id没找到，尝试通过phone_number查找
    if not user:
        user = db.query(User).filter(User.phone_number == login_identifier).first()

    # 如果用户不存在，为防止用户名枚举攻击，返回通用错误信息
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录标识或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 检查用户是否已被删除
    if user.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该账户已注销",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 检查用户是否处于登录锁定状态
    if user.is_login_locked():
        remaining_time = user.get_remaining_lock_time()
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"登录被锁定，请等待 {remaining_time} 秒后再试",
            headers={"WWW-Authenticate": "Bearer", "X-Lock-Remaining": str(remaining_time)},
        )

    # 验证密码
    if not AuthUtils.verify_password(user.password_hash, form_data.password):
        # 密码错误，增加失败次数
        user.increment_failed_login()
        db.commit()

        # 记录失败操作
        log_operation(db, user.id if user else None, "登录失败", f"密码错误，失败次数: {user.login_failed_count}")

        # 检查是否需要锁定
        if user.is_login_locked():
            remaining_time = user.get_remaining_lock_time()
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"由于多次登录失败，账户已被锁定 {remaining_time} 秒",
                headers={"WWW-Authenticate": "Bearer", "X-Lock-Remaining": str(remaining_time)},
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # 登录成功，重置失败计数器
    user.reset_failed_login()
    user.last_login = utc_now()
    db.commit()

    # 生成访问令牌
    token_data = {"sub": str(user.id)}
    access_token = AuthUtils.create_access_token(token_data)

    # 记录登录操作
    log_operation(db, user.id, "登录")

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
        "user_id_login": user.user_id,
        "phone_number": user.phone_number,
        "avatar": user.avatar,
        "role": user.role,
    }


# 路由：校验是否需要初始化管理员
@auth.get("/check-first-run")
async def check_first_run():
    is_first_run = db_manager.check_first_run()
    return {"first_run": is_first_run}


# 路由：初始化管理员账户
@auth.post("/initialize", response_model=Token)
async def initialize_admin(admin_data: InitializeAdmin, db: Session = Depends(get_db)):
    # 检查是否是首次运行
    if not db_manager.check_first_run():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="系统已经初始化，无法再次创建初始管理员",
        )

    # 创建管理员账户
    hashed_password = AuthUtils.hash_password(admin_data.password)

    # 验证用户ID格式（只支持字母数字和下划线）
    if not re.match(r"^[a-zA-Z0-9_]+$", admin_data.user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户ID只能包含字母、数字和下划线",
        )

    if len(admin_data.user_id) < 3 or len(admin_data.user_id) > 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户ID长度必须在3-20个字符之间",
        )

    # 验证手机号格式（如果提供了）
    if admin_data.phone_number and not is_valid_phone_number(admin_data.phone_number):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="手机号格式不正确")

    # 由于是首次初始化，直接使用输入的user_id
    user_id = admin_data.user_id

    new_admin = User(
        username=admin_data.user_id,  # username和user_id设置为相同值
        user_id=user_id,
        phone_number=admin_data.phone_number,
        avatar=None,  # 初始化时头像为空
        password_hash=hashed_password,
        role="superadmin",
        last_login=utc_now(),
    )

    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)

    # 生成访问令牌
    token_data = {"sub": str(new_admin.id)}
    access_token = AuthUtils.create_access_token(token_data)

    # 记录操作
    log_operation(db, new_admin.id, "系统初始化", "创建超级管理员账户")

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": new_admin.id,
        "username": new_admin.username,
        "user_id_login": new_admin.user_id,
        "phone_number": new_admin.phone_number,
        "avatar": new_admin.avatar,
        "role": new_admin.role,
    }


# 路由：获取当前用户信息
# =============================================================================
# === 用户信息分组 ===
# =============================================================================


@auth.get("/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user.to_dict()


# 路由：更新个人资料
@auth.put("/profile", response_model=UserResponse)
async def update_profile(
    profile_data: UserProfileUpdate,
    request: Request,
    current_user: User = Depends(get_required_user),
    db: Session = Depends(get_db),
):
    """更新当前用户的个人资料"""
    update_details = []

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
        existing_user = (
            db.query(User).filter(User.username == profile_data.username, User.id != current_user.id).first()
        )
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户名已存在",
            )

        current_user.username = profile_data.username
        update_details.append(f"用户名: {profile_data.username}")

    # 更新手机号
    if profile_data.phone_number is not None:
        # 如果手机号不为空，验证格式
        if profile_data.phone_number and not is_valid_phone_number(profile_data.phone_number):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="手机号格式不正确")

        # 检查手机号是否已被其他用户使用
        if profile_data.phone_number:
            existing_phone = (
                db.query(User)
                .filter(User.phone_number == profile_data.phone_number, User.id != current_user.id)
                .first()
            )
            if existing_phone:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="手机号已被其他用户使用")

        current_user.phone_number = profile_data.phone_number
        update_details.append(f"手机号: {profile_data.phone_number or '已清空'}")

    db.commit()

    # 记录操作
    if update_details:
        log_operation(db, current_user.id, "更新个人资料", f"更新个人资料: {', '.join(update_details)}", request)

    return current_user.to_dict()


# 路由：创建新用户（管理员权限）
# =============================================================================
# === 用户管理分组 ===
# =============================================================================


@auth.post("/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreate, request: Request, current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)
):
    # 验证用户名
    is_valid, error_msg = validate_username(user_data.username)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg,
        )

    # 检查用户名是否已存在
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在",
        )

    # 检查手机号是否已存在（如果提供了）
    if user_data.phone_number:
        existing_phone = db.query(User).filter(User.phone_number == user_data.phone_number).first()
        if existing_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="手机号已存在",
            )

    # 生成唯一的user_id
    existing_user_ids = [user.user_id for user in db.query(User.user_id).all()]
    user_id = generate_unique_user_id(user_data.username, existing_user_ids)

    # 创建新用户
    hashed_password = AuthUtils.hash_password(user_data.password)

    # 检查角色权限
    # 超级管理员可以创建任何类型的用户
    if user_data.role == "superadmin" and current_user.role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有超级管理员才能创建超级管理员账户",
        )

    # 管理员只能创建普通用户
    if current_user.role == "admin" and user_data.role != "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理员只能创建普通用户账户",
        )

    new_user = User(
        username=user_data.username,
        user_id=user_id,
        phone_number=user_data.phone_number,
        password_hash=hashed_password,
        role=user_data.role,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 记录操作
    log_operation(db, current_user.id, "创建用户", f"创建用户: {user_data.username}, 角色: {user_data.role}", request)

    return new_user.to_dict()


# 路由：获取所有用户（管理员权限）
@auth.get("/users", response_model=list[UserResponse])
async def read_users(
    skip: int = 0, limit: int = 100, current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)
):
    users = db.query(User).filter(User.is_deleted == 0).offset(skip).limit(limit).all()
    return [user.to_dict() for user in users]


# 路由：获取特定用户信息（管理员权限）
@auth.get("/users/{user_id}", response_model=UserResponse)
async def read_user(user_id: int, current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id, User.is_deleted == 0).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    return user.to_dict()


# 路由：更新用户信息（管理员权限）
@auth.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    request: Request,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id, User.is_deleted == 0).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    # 检查权限
    if user.role == "superadmin" and current_user.role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有超级管理员才能修改超级管理员账户",
        )

    # 超级管理员账户不能被降级（只能由其他超级管理员修改）
    if user.role == "superadmin" and user_data.role and user_data.role != "superadmin" and current_user.id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="不能降级超级管理员账户",
        )

    # 更新信息
    update_details = []

    if user_data.username is not None:
        # 检查用户名是否已被其他用户使用
        existing_user = db.query(User).filter(User.username == user_data.username, User.id != user_id).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户名已存在",
            )
        user.username = user_data.username
        update_details.append(f"用户名: {user_data.username}")

    if user_data.password is not None:
        user.password_hash = AuthUtils.hash_password(user_data.password)
        update_details.append("密码已更新")

    if user_data.role is not None:
        user.role = user_data.role
        update_details.append(f"角色: {user_data.role}")

    db.commit()

    # 记录操作
    log_operation(db, current_user.id, "更新用户", f"更新用户ID {user_id}: {', '.join(update_details)}", request)

    return user.to_dict()


# 路由：删除用户（管理员权限）
@auth.delete("/users/{user_id}", response_model=dict)
async def delete_user(
    user_id: int, request: Request, current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id, User.is_deleted == 0).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    # 检查权限
    if user.role == "superadmin":
        # 只有超级管理员可以删除超级管理员
        if current_user.role != "superadmin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有超级管理员才能删除超级管理员账户",
            )

        # 检查是否是最后一个超级管理员
        superadmin_count = db.query(User).filter(User.role == "superadmin", User.is_deleted == 0).count()
        if superadmin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能删除最后一个超级管理员账户",
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

    deletion_detail = f"删除用户: {user.username}, ID: {user.id}, 角色: {user.role}"

    # 软删除：标记删除状态并脱敏
    import hashlib

    # 生成4位哈希（基于user_id保证唯一性）
    hash_suffix = hashlib.md5(user.user_id.encode()).hexdigest()[:4]

    user.is_deleted = 1
    user.deleted_at = utc_now()
    user.username = f"已注销用户-{hash_suffix}"
    user.phone_number = None  # 清空手机号，释放该手机号供其他用户使用
    user.password_hash = "DELETED"  # 禁止登录
    user.avatar = None  # 清空头像

    db.commit()

    # 记录操作
    log_operation(db, current_user.id, "删除用户", deletion_detail, request)

    return {"success": True, "message": "用户已删除"}


# 路由：验证用户名并生成user_id
@auth.post("/validate-username", response_model=UserIdGeneration)
async def validate_username_and_generate_user_id(
    validation_data: UsernameValidation, current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)
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
    existing_user = db.query(User).filter(User.username == validation_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在",
        )

    # 生成唯一的user_id
    existing_user_ids = [user.user_id for user in db.query(User.user_id).all()]
    user_id = generate_unique_user_id(validation_data.username, existing_user_ids)

    return UserIdGeneration(username=validation_data.username, user_id=user_id, is_available=True)


# 路由：检查user_id是否可用
@auth.get("/check-user-id/{user_id}")
async def check_user_id_availability(
    user_id: str, current_user: User = Depends(get_admin_user), db: Session = Depends(get_db)
):
    """检查user_id是否可用"""
    existing_user = db.query(User).filter(User.user_id == user_id).first()
    return {"user_id": user_id, "is_available": existing_user is None}


# 路由：上传用户头像
@auth.post("/upload-avatar")
async def upload_user_avatar(
    file: UploadFile = File(...), current_user: User = Depends(get_required_user), db: Session = Depends(get_db)
):
    """上传用户头像"""
    # 检查文件类型
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能上传图片文件")

    # 检查文件大小（5MB限制）
    file_size = 0
    file_content = await file.read()
    file_size = len(file_content)

    if file_size > 5 * 1024 * 1024:  # 5MB
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件大小不能超过5MB")

    try:
        # 获取文件扩展名
        file_extension = file.filename.split(".")[-1].lower() if file.filename and "." in file.filename else "jpg"

        # 上传到MinIO
        avatar_url = upload_image_to_minio(file_content, file_extension)

        # 更新用户头像
        current_user.avatar = avatar_url
        db.commit()

        # 记录操作
        log_operation(db, current_user.id, "上传头像", f"更新头像: {avatar_url}")

        return {"success": True, "avatar_url": avatar_url, "message": "头像上传成功"}

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"头像上传失败: {str(e)}")
