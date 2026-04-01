"""OIDC 认证路由模块

此模块包含 OIDC 认证相关的路由，需要被导入到主 auth_router.py 中使用。
"""
from urllib.parse import urlencode
import hashlib
from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from yuxi.utils import logger
from yuxi.storage.postgres.models_business import User, Department
from yuxi.repositories.user_repository import UserRepository
from server.utils.auth_utils import AuthUtils
from server.utils.oidc_config import oidc_config
from server.utils.oidc_utils import OIDCUtils
from server.utils.common_utils import log_operation
from yuxi.utils.datetime_utils import utc_now_naive

# 前端 OIDC 回调路由路径（与 web/src/router/index.js 中的路由保持一致）
FRONTEND_CALLBACK_PATH = "/auth/oidc/callback"
# 登录页路径（用于错误重定向）
FRONTEND_LOGIN_PATH = "/login"


# =============================================================================
# === OIDC 请求和响应模型 ===
# =============================================================================

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
    user_id_login: str
    phone_number: str | None = None
    avatar: str | None = None
    role: str
    department_id: int | None = None
    department_name: str | None = None


# =============================================================================
# === OIDC 工具函数 ===
# =============================================================================

async def get_or_create_oidc_department(db) -> Department | None:
    """获取或创建 OIDC 用户的默认部门"""
    dept_name = oidc_config.default_department

    result = await db.execute(select(Department).filter(Department.name == dept_name))
    dept = result.scalar_one_or_none()

    if not dept:
        dept = Department(
            name=dept_name,
            description=f"{dept_name}部门",
        )
        db.add(dept)
        try:
            await db.commit()
            await db.refresh(dept)
            logger.info(f"Created OIDC department: {dept_name}")
        except IntegrityError:
            await db.rollback()
            result = await db.execute(select(Department).filter(Department.name == dept_name))
            dept = result.scalar_one_or_none()

    return dept


async def find_user_by_oidc_sub(db, sub: str) -> User | None:
    """通过 OIDC sub 查找用户"""
    oidc_user_id = f"oidc:{sub}"

    # 优先匹配标准 user_id（oidc:{sub}）
    result = await db.execute(select(User).filter(User.user_id == oidc_user_id, User.is_deleted == 0))
    user = result.scalar_one_or_none()
    if user:
        return user

    # 兼容历史后缀 user_id（oidc:{sub}:xxxx）
    legacy_result = await db.execute(
        select(User)
        .filter(User.user_id.like(f"{oidc_user_id}:%"), User.is_deleted == 0)
        .order_by(User.id.asc())
    )
    legacy_users = list(legacy_result.scalars().all())
    if legacy_users:
        if len(legacy_users) > 1:
            logger.warning(f"Multiple legacy OIDC users matched for sub={sub}, use earliest id={legacy_users[0].id}")
        return legacy_users[0]

    return None


async def find_deleted_oidc_user_by_sub(db, sub: str) -> User | None:
    """查找已注销的 OIDC 账户（标准与历史后缀）"""
    oidc_user_id = f"oidc:{sub}"

    result = await db.execute(select(User).filter(User.user_id == oidc_user_id, User.is_deleted == 1))
    deleted_user = result.scalar_one_or_none()
    if deleted_user:
        return deleted_user

    legacy_result = await db.execute(
        select(User)
        .filter(User.user_id.like(f"{oidc_user_id}:%"), User.is_deleted == 1)
        .order_by(User.id.asc())
    )
    return legacy_result.scalar_one_or_none()


async def build_unique_oidc_username(db, preferred_username: str, sub: str) -> str:
    """为 OIDC 用户生成不冲突的用户名"""
    base_username = preferred_username.strip() if preferred_username else ""
    if not base_username:
        base_username = f"oidc_{sub[:8]}"

    result = await db.execute(select(User.id).filter(User.username == base_username))
    if result.scalar_one_or_none() is None:
        return base_username

    hash_suffix = hashlib.sha256(sub.encode()).hexdigest()[:6]
    candidate = f"{base_username}-{hash_suffix}"
    result = await db.execute(select(User.id).filter(User.username == candidate))
    if result.scalar_one_or_none() is None:
        return candidate

    for i in range(2, 100):
        indexed_candidate = f"{candidate}-{i}"
        result = await db.execute(select(User.id).filter(User.username == indexed_candidate))
        if result.scalar_one_or_none() is None:
            return indexed_candidate

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="无法生成可用用户名，请联系管理员",
    )


async def create_oidc_user(db, user_info: dict, department_id: int | None = None) -> User:
    """创建 OIDC 用户"""
    user_repo = UserRepository()

    sub = user_info["sub"]
    preferred_username = user_info["name"] or user_info["username"]
    user_id = f"oidc:{sub}"

    # 生成随机密码（OIDC 用户不需要密码登录）
    import secrets
    random_password = secrets.token_urlsafe(32)
    password_hash = AuthUtils.hash_password(random_password)

    username = await build_unique_oidc_username(db, preferred_username, sub)

    # 并发场景下兜底：若创建时发生唯一键冲突，优先复用已创建账号；否则重试用户名。
    for retry_index in range(3):
        try:
            new_user = await user_repo.create({
                "username": username,
                "user_id": user_id,
                "phone_number": None,  # OIDC 用户没有手机号
                "avatar": None,
                "password_hash": password_hash,
                "role": oidc_config.default_role,
                "department_id": department_id,
                "last_login": utc_now_naive(),
            })
            logger.info(f"Created OIDC user: {new_user.username} ({user_id})")
            return new_user
        except IntegrityError:
            existing_user = await find_user_by_oidc_sub(db, sub)
            if existing_user:
                return existing_user
            username = await build_unique_oidc_username(db, f"{preferred_username}-{retry_index + 2}", sub)

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="创建 OIDC 用户失败，请重试",
    )


async def restore_deleted_oidc_user(db, deleted_user: User, user_info: dict) -> User:
    """恢复已注销的 OIDC 用户并返回可登录用户"""
    preferred_username = user_info["name"] or user_info["username"]

    deleted_user.is_deleted = 0
    deleted_user.deleted_at = None
    deleted_user.last_login = utc_now_naive()
    deleted_user.phone_number = None
    deleted_user.avatar = None

    # 删除流程会把用户名改成“已注销用户-xxxx”，恢复时重新分配可用用户名
    if deleted_user.username.startswith("已注销用户-"):
        deleted_user.username = await build_unique_oidc_username(db, preferred_username, user_info["sub"])

    if deleted_user.password_hash == "DELETED":
        import secrets
        random_password = secrets.token_urlsafe(32)
        deleted_user.password_hash = AuthUtils.hash_password(random_password)

    await db.commit()
    await db.refresh(deleted_user)
    logger.info(f"Restored deleted OIDC user: {deleted_user.username} ({deleted_user.user_id})")
    return deleted_user


async def update_oidc_user_login(db, user: User) -> None:
    """更新 OIDC 用户登录时间"""
    user.last_login = utc_now_naive()
    await db.commit()


def _redirect_to_callback(exchange_code: str) -> RedirectResponse:
    """成功后重定向到前端 OIDC 回调页面，仅携带一次性 code"""
    url = f"{FRONTEND_CALLBACK_PATH}?{urlencode({'code': exchange_code})}"
    return RedirectResponse(url=url, status_code=302)


def _redirect_to_login_with_error(error_message: str) -> RedirectResponse:
    """失败时重定向到登录页并携带错误信息"""
    url = f"{FRONTEND_LOGIN_PATH}?{urlencode({'oidc_error': error_message})}"
    return RedirectResponse(url=url, status_code=302)


# =============================================================================
# === OIDC 路由处理函数 ===
# =============================================================================

async def get_oidc_config_handler():
    """获取 OIDC 配置（供前端使用）"""
    if not oidc_config.enabled or not oidc_config.is_configured():
        return OIDCConfigResponse(enabled=False)

    provider_name = oidc_config.provider_name
    return OIDCConfigResponse(enabled=True, provider_name=provider_name)


async def oidc_callback_handler(code: str, state: str, db, request: Request | None = None):
    """处理 OIDC 回调 - 重定向到前端 Vue 路由"""

    # 验证 state
    if not OIDCUtils.verify_state(state):
        return _redirect_to_login_with_error("登录会话已过期，请返回登录页重试")

    # 用授权码交换令牌
    token_response = await OIDCUtils.exchange_code_for_token(code)
    if not token_response:
        return _redirect_to_login_with_error("无法获取访问令牌，请返回登录页重试")

    access_token = token_response.get("access_token")
    if not access_token:
        return _redirect_to_login_with_error("无法获取访问令牌，请返回登录页重试")

    # 获取用户信息
    userinfo = await OIDCUtils.get_userinfo(access_token)
    if not userinfo:
        return _redirect_to_login_with_error("无法获取用户信息，请返回登录页重试")

    # 提取用户信息
    extracted_info = OIDCUtils.extract_user_info(userinfo)
    sub = extracted_info["sub"]

    if not sub:
        return _redirect_to_login_with_error("无法获取用户标识，请返回登录页重试")

    # 查找或创建用户
    user = await find_user_by_oidc_sub(db, sub)

    if user:
        # 更新登录时间
        await update_oidc_user_login(db, user)
        logger.info(f"OIDC user logged in: {user.username}")
    elif oidc_config.auto_create_user:
        deleted_user = await find_deleted_oidc_user_by_sub(db, sub)
        if deleted_user:
            user = await restore_deleted_oidc_user(db, deleted_user, extracted_info)
            logger.info(f"OIDC deleted user restored and logged in: {user.username}")
        else:
            # 获取或创建 OIDC 部门
            dept = await get_or_create_oidc_department(db)
            department_id = dept.id if dept else None

            # 创建新用户
            user = await create_oidc_user(db, extracted_info, department_id)
    else:
        return _redirect_to_login_with_error("用户未注册，请联系管理员开通账号")

    # 检查用户是否被删除
    if user.is_deleted:
        return _redirect_to_login_with_error("该账户已注销")

    # 生成访问令牌
    token_data = {"sub": str(user.id)}
    jwt_token = AuthUtils.create_access_token(token_data)

    # 记录登录操作
    await log_operation(db, user.id, "OIDC 登录", request=request)

    # 获取部门名称
    department_name = None
    if user.department_id:
        result = await db.execute(select(Department.name).filter(Department.id == user.department_id))
        department_name = result.scalar_one_or_none()

    # 构建响应数据
    response_data = {
        "access_token": jwt_token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
        "user_id_login": user.user_id,
        "phone_number": user.phone_number,
        "avatar": user.avatar,
        "role": user.role,
        "department_id": user.department_id,
        "department_name": department_name,
    }

    exchange_code = OIDCUtils.generate_login_code(response_data)

    # 重定向到前端 OIDC 回调 Vue 页面
    return _redirect_to_callback(exchange_code)


async def oidc_exchange_code_handler(code: str) -> dict:
    """用一次性 code 交换登录响应数据"""
    token_data = OIDCUtils.consume_login_code(code)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="登录 code 无效或已过期，请重新登录",
        )
    return token_data


async def oidc_login_url_handler(redirect_path: str = "/"):
    """获取 OIDC 登录 URL"""
    if not oidc_config.enabled or not oidc_config.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC is not enabled or not configured"
        )

    login_url = await OIDCUtils.build_authorization_url(redirect_path)
    if not login_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build authorization URL"
        )

    return {"login_url": login_url}
