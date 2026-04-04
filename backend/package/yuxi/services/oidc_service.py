"""OIDC 服务模块。

统一封装 OIDC 配置、工具能力和认证业务处理逻辑
"""

import hashlib
import os
import secrets
import time
import urllib.parse
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from yuxi.repositories.user_repository import UserRepository
from yuxi.storage.postgres.models_business import Department, User
from yuxi.utils.datetime_utils import utc_now_naive
from yuxi.utils.logging_config import logger

from server.utils.auth_utils import AuthUtils
from server.utils.common_utils import log_operation

# 前端 OIDC 回调路由路径（与 web/src/router/index.js 中的路由保持一致）
FRONTEND_CALLBACK_PATH = "/auth/oidc/callback"
# 登录页路径
FRONTEND_LOGIN_PATH = "/login"


class OIDCConfig(BaseModel):
    """OIDC 配置模型"""

    enabled: bool = Field(default=False, description="是否启用 OIDC 认证")
    issuer_url: str = Field(default="", description="OIDC Provider 的 issuer URL")
    client_id: str = Field(default="", description="OIDC Client ID")
    client_secret: str = Field(default="", description="OIDC Client Secret")
    redirect_uri: str = Field(default="", description="OIDC 回调 URL")
    authorization_endpoint: str = Field(default="", description="授权端点 URL")
    token_endpoint: str = Field(default="", description="Token 端点 URL")
    userinfo_endpoint: str = Field(default="", description="UserInfo 端点 URL")
    end_session_endpoint: str = Field(default="", description="登出端点 URL")
    provider_name: str = Field(default="OIDC登录", description="认证源名称，显示在登录按钮上的文字")
    scopes: str = Field(default="openid profile email", description="请求的 scope")
    auto_create_user: bool = Field(default=True, description="是否自动创建用户")
    default_role: str = Field(default="user", description="OIDC 用户的默认角色")
    default_department: str = Field(default="OIDC用户", description="OIDC 用户的默认部门")
    username_claim: str = Field(default="preferred_username", description="用户名映射字段")
    email_claim: str = Field(default="email", description="邮箱映射字段")
    name_claim: str = Field(default="name", description="姓名映射字段")

    @classmethod
    def from_env(cls) -> "OIDCConfig":
        """从环境变量加载配置"""

        def _env(name: str, default: str = "") -> str:
            return os.environ.get(name, default).strip()

        enabled = os.environ.get("OIDC_ENABLED", "false").lower() == "true"

        if not enabled:
            return cls(enabled=False)

        return cls(
            enabled=enabled,
            provider_name=_env("OIDC_PROVIDER_NAME", "OIDC登录"),
            issuer_url=_env("OIDC_ISSUER_URL"),
            client_id=_env("OIDC_CLIENT_ID"),
            client_secret=_env("OIDC_CLIENT_SECRET"),
            redirect_uri=_env("OIDC_REDIRECT_URI"),
            authorization_endpoint=_env("OIDC_AUTHORIZATION_ENDPOINT"),
            token_endpoint=_env("OIDC_TOKEN_ENDPOINT"),
            userinfo_endpoint=_env("OIDC_USERINFO_ENDPOINT"),
            end_session_endpoint=_env("OIDC_END_SESSION_ENDPOINT"),
            scopes=_env("OIDC_SCOPES", "openid profile email"),
            auto_create_user=os.environ.get("OIDC_AUTO_CREATE_USER", "true").lower() == "true",
            default_role=_env("OIDC_DEFAULT_ROLE", "user"),
            default_department=_env("OIDC_DEFAULT_DEPARTMENT", "OIDC用户"),
            username_claim=_env("OIDC_USERNAME_CLAIM", "preferred_username"),
            email_claim=_env("OIDC_EMAIL_CLAIM", "email"),
            name_claim=_env("OIDC_NAME_CLAIM", "name"),
        )

    def is_configured(self) -> bool:
        """检查登录链接生成所需配置是否完整"""
        if not self.enabled:
            return False
        # 生成登录链接只要求 client_id + (issuer_url 或 authorization_endpoint)
        return bool(self.client_id and (self.issuer_url or self.authorization_endpoint))

    def is_token_exchange_configured(self) -> bool:
        """检查授权码换 token 所需配置是否完整"""
        if not self.enabled:
            return False
        # 回调换 token 需要 client_id + client_secret + (issuer_url 或 token_endpoint)
        return bool(self.client_id and self.client_secret and (self.issuer_url or self.token_endpoint))


oidc_config = OIDCConfig.from_env()


class OIDCProviderMetadata:
    """OIDC Provider 元数据"""

    def __init__(self):
        self.authorization_endpoint: str | None = None
        self.token_endpoint: str | None = None
        self.userinfo_endpoint: str | None = None
        self.end_session_endpoint: str | None = None
        self.last_error: str | None = None
        self._loaded = False

    async def load(self, issuer_url: str) -> bool:
        """从 discovery 端点加载元数据"""
        if self._loaded:
            return True

        discovery_url = f"{issuer_url.rstrip('/')}/.well-known/openid-configuration"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(discovery_url, timeout=30.0)
                response.raise_for_status()
                metadata = response.json()

            self.authorization_endpoint = metadata.get("authorization_endpoint")
            self.token_endpoint = metadata.get("token_endpoint")
            self.userinfo_endpoint = metadata.get("userinfo_endpoint")
            self.end_session_endpoint = metadata.get("end_session_endpoint")

            # 登录 URL 生成至少需要 authorization_endpoint。
            if not self.authorization_endpoint:
                self.last_error = "discovery 响应缺少 authorization_endpoint"
                logger.error(f"Failed to load OIDC discovery: {self.last_error}, url={discovery_url}")
                return False

            self._loaded = True
            self.last_error = None
            logger.info(f"OIDC discovery loaded from {discovery_url}")
            return True

        except Exception as e:
            self.last_error = f"{type(e).__name__}: {repr(e)}"
            logger.error(f"Failed to load OIDC discovery: {self.last_error}, url={discovery_url}")
            return False


class OIDCUtils:
    """OIDC 工具类"""

    _metadata: OIDCProviderMetadata | None = None
    _state_store: dict[str, dict[str, Any]] = {}
    _login_code_store: dict[str, dict[str, Any]] = {}
    _state_ttl_seconds = 300
    _login_code_ttl_seconds = 60
    _last_metadata_error: str | None = None

    @classmethod
    def _cleanup_expired_state(cls) -> None:
        now = time.time()
        expired = [k for k, v in cls._state_store.items() if v["expires_at"] <= now]
        for key in expired:
            cls._state_store.pop(key, None)

    @classmethod
    def _cleanup_expired_login_code(cls) -> None:
        now = time.time()
        expired = [k for k, v in cls._login_code_store.items() if v["expires_at"] <= now]
        for key in expired:
            cls._login_code_store.pop(key, None)

    @classmethod
    async def get_metadata(cls) -> OIDCProviderMetadata | None:
        """获取 OIDC Provider 元数据"""
        if not oidc_config.enabled or not oidc_config.is_configured():
            cls._last_metadata_error = "OIDC 未启用或基础配置不完整"
            return None

        if cls._metadata is None:
            cls._metadata = OIDCProviderMetadata()

            if oidc_config.authorization_endpoint:
                cls._metadata.authorization_endpoint = oidc_config.authorization_endpoint
                cls._metadata.token_endpoint = oidc_config.token_endpoint
                cls._metadata.userinfo_endpoint = oidc_config.userinfo_endpoint
                cls._metadata.end_session_endpoint = oidc_config.end_session_endpoint
                cls._metadata._loaded = True
                cls._last_metadata_error = None
            else:
                success = await cls._metadata.load(oidc_config.issuer_url)
                if not success:
                    cls._last_metadata_error = cls._metadata.last_error or "OIDC discovery 加载失败"
                    return None

        if not cls._metadata.authorization_endpoint:
            cls._last_metadata_error = "OIDC 授权端点不可用"
            return None

        cls._last_metadata_error = None

        return cls._metadata

    @classmethod
    def get_last_metadata_error(cls) -> str | None:
        """获取最近一次 OIDC 元数据加载错误"""
        return cls._last_metadata_error

    @classmethod
    def generate_state(cls, redirect_path: str = "/") -> str:
        """生成 state 参数并存储"""
        cls._cleanup_expired_state()
        state = secrets.token_urlsafe(32)
        cls._state_store[state] = {
            "redirect_path": redirect_path,
            "expires_at": time.time() + cls._state_ttl_seconds,
        }
        return state

    @classmethod
    def verify_state(cls, state: str) -> dict[str, Any] | None:
        """验证 state 参数"""
        state_data = cls._state_store.pop(state, None)
        if not state_data:
            return None
        if state_data["expires_at"] <= time.time():
            return None
        return {"redirect_path": state_data["redirect_path"]}

    @classmethod
    def generate_login_code(cls, payload: dict[str, Any]) -> str:
        """生成一次性短期登录 code"""
        cls._cleanup_expired_login_code()
        code = secrets.token_urlsafe(32)
        cls._login_code_store[code] = {
            "payload": payload,
            "expires_at": time.time() + cls._login_code_ttl_seconds,
        }
        return code

    @classmethod
    def consume_login_code(cls, code: str) -> dict[str, Any] | None:
        """消费一次性短期登录 code"""
        data = cls._login_code_store.pop(code, None)
        if not data:
            return None
        if data["expires_at"] <= time.time():
            return None
        return data["payload"]

    @classmethod
    def generate_nonce(cls) -> str:
        """生成 nonce 参数"""
        return secrets.token_urlsafe(32)

    @classmethod
    async def build_authorization_url(cls, redirect_path: str = "/") -> str | None:
        """构建授权 URL"""
        metadata = await cls.get_metadata()
        if not metadata or not metadata.authorization_endpoint:
            return None

        state = cls.generate_state(redirect_path)
        nonce = cls.generate_nonce()

        redirect_uri = oidc_config.redirect_uri
        if not redirect_uri:
            redirect_uri = "/api/auth/oidc/callback"

        params = {
            "client_id": oidc_config.client_id,
            "response_type": "code",
            "scope": oidc_config.scopes,
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": nonce,
        }

        query_string = urllib.parse.urlencode(params)
        return f"{metadata.authorization_endpoint}?{query_string}"

    @classmethod
    async def exchange_code_for_token(cls, code: str) -> dict[str, Any] | None:
        """用授权码交换令牌"""
        metadata = await cls.get_metadata()
        if not metadata or not metadata.token_endpoint:
            return None

        redirect_uri = oidc_config.redirect_uri or "/api/auth/oidc/callback"

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": oidc_config.client_id,
            "client_secret": oidc_config.client_secret,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    metadata.token_endpoint,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=30.0,
                )
                response.raise_for_status()
                return response.json()

        except Exception as e:
            logger.error(f"Failed to exchange code for token: {e}")
            return None

    @classmethod
    async def get_userinfo(cls, access_token: str) -> dict[str, Any] | None:
        """获取用户信息"""
        metadata = await cls.get_metadata()
        if not metadata or not metadata.userinfo_endpoint:
            return None

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    metadata.userinfo_endpoint,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0,
                )
                response.raise_for_status()
                return response.json()

        except Exception as e:
            logger.error(f"Failed to get userinfo: {e}")
            return None

    @classmethod
    async def build_logout_url(cls, id_token: str | None = None) -> str | None:
        """构建登出 URL"""
        metadata = await cls.get_metadata()
        if not metadata or not metadata.end_session_endpoint:
            return None

        params = {"client_id": oidc_config.client_id}

        if id_token:
            params["id_token_hint"] = id_token

        if oidc_config.redirect_uri:
            params["post_logout_redirect_uri"] = oidc_config.redirect_uri

        query_string = urllib.parse.urlencode(params)
        return f"{metadata.end_session_endpoint}?{query_string}"

    @classmethod
    def extract_user_info(cls, userinfo: dict[str, Any]) -> dict[str, Any]:
        """从 userinfo 中提取用户信息"""
        sub = userinfo.get("sub", "")

        username = userinfo.get(oidc_config.username_claim, "")
        if not username:
            username = userinfo.get("preferred_username", "")
        if not username:
            username = userinfo.get("email", "").split("@")[0]
        if not username:
            username = sub[:20]

        email = userinfo.get(oidc_config.email_claim, "")
        if not email:
            email = userinfo.get("email", "")

        name = userinfo.get(oidc_config.name_claim, "")
        if not name:
            name = userinfo.get("name", "")
        if not name:
            name = username

        return {
            "sub": sub,
            "username": username,
            "email": email,
            "name": name,
            "raw": userinfo,
        }


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

    result = await db.execute(select(User).filter(User.user_id == oidc_user_id, User.is_deleted == 0))
    user = result.scalar_one_or_none()
    if user:
        return user

    legacy_result = await db.execute(
        select(User).filter(User.user_id.like(f"{oidc_user_id}:%"), User.is_deleted == 0).order_by(User.id.asc())
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
        select(User).filter(User.user_id.like(f"{oidc_user_id}:%"), User.is_deleted == 1).order_by(User.id.asc())
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

    random_password = secrets.token_urlsafe(32)
    password_hash = AuthUtils.hash_password(random_password)

    username = await build_unique_oidc_username(db, preferred_username, sub)

    for retry_index in range(3):
        try:
            new_user = await user_repo.create(
                {
                    "username": username,
                    "user_id": user_id,
                    "phone_number": None,
                    "avatar": None,
                    "password_hash": password_hash,
                    "role": oidc_config.default_role,
                    "department_id": department_id,
                    "last_login": utc_now_naive(),
                }
            )
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

    if deleted_user.username.startswith("已注销用户-"):
        deleted_user.username = await build_unique_oidc_username(db, preferred_username, user_info["sub"])

    if deleted_user.password_hash == "DELETED":
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


async def get_oidc_config_handler():
    """获取 OIDC 配置（供前端使用）"""
    if not oidc_config.enabled or not oidc_config.is_configured():
        return {"enabled": False}

    provider_name = oidc_config.provider_name
    return {"enabled": True, "provider_name": provider_name}


async def oidc_callback_handler(code: str, state: str, db, request: Request | None = None):
    """处理 OIDC 回调 - 重定向到前端 Vue 路由"""

    if not oidc_config.is_token_exchange_configured():
        return _redirect_to_login_with_error("OIDC 配置不完整，请联系管理员")

    if not OIDCUtils.verify_state(state):
        return _redirect_to_login_with_error("登录会话已过期，请返回登录页重试")

    token_response = await OIDCUtils.exchange_code_for_token(code)
    if not token_response:
        return _redirect_to_login_with_error("无法获取访问令牌，请返回登录页重试")

    access_token = token_response.get("access_token")
    if not access_token:
        return _redirect_to_login_with_error("无法获取访问令牌，请返回登录页重试")

    userinfo = await OIDCUtils.get_userinfo(access_token)
    if not userinfo:
        return _redirect_to_login_with_error("无法获取用户信息，请返回登录页重试")

    extracted_info = OIDCUtils.extract_user_info(userinfo)
    sub = extracted_info["sub"]

    if not sub:
        return _redirect_to_login_with_error("无法获取用户标识，请返回登录页重试")

    user = await find_user_by_oidc_sub(db, sub)

    if user:
        await update_oidc_user_login(db, user)
        logger.info(f"OIDC user logged in: {user.username}")
    elif oidc_config.auto_create_user:
        deleted_user = await find_deleted_oidc_user_by_sub(db, sub)
        if deleted_user:
            user = await restore_deleted_oidc_user(db, deleted_user, extracted_info)
            logger.info(f"OIDC deleted user restored and logged in: {user.username}")
        else:
            dept = await get_or_create_oidc_department(db)
            department_id = dept.id if dept else None
            user = await create_oidc_user(db, extracted_info, department_id)
    else:
        return _redirect_to_login_with_error("用户未注册，请联系管理员开通账号")

    if user.is_deleted:
        return _redirect_to_login_with_error("该账户已注销")

    token_data = {"sub": str(user.id)}
    jwt_token = AuthUtils.create_access_token(token_data)

    await log_operation(db, user.id, "OIDC 登录", request=request)

    department_name = None
    if user.department_id:
        result = await db.execute(select(Department.name).filter(Department.id == user.department_id))
        department_name = result.scalar_one_or_none()

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
            detail="OIDC 登录暂不可用，请联系管理员",
        )

    login_url = await OIDCUtils.build_authorization_url(redirect_path)
    if not login_url:
        metadata_error = OIDCUtils.get_last_metadata_error()
        if metadata_error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"生成登录链接失败：{metadata_error}",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="生成登录链接失败，请稍后重试或联系管理员",
        )

    return {"login_url": login_url}
