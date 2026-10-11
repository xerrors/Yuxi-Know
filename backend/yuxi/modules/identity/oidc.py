"""OIDC 服务模块。

统一封装 OIDC 配置、工具能力和认证业务处理逻辑
"""

import hashlib
import os
import secrets
import time
import urllib.parse
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from yuxi.infrastructure.observability.logging import logger
from yuxi.infrastructure.oidc.client import OIDCProviderMetadata, exchange_code_for_token, get_userinfo
from yuxi.modules.identity.models import Department, User
from yuxi.modules.identity.repositories.users import UserRepository
from yuxi.modules.identity.security import AuthUtils
from yuxi.shared.datetime import utc_now
from yuxi.shared.errors import OperationFailedError, PermissionDeniedError, StateConflictError

# 前端 OIDC 回调路由路径（与 frontend/src/router/index.js 中的路由保持一致）
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
    use_raw_username: bool = Field(default=False, description="是否使用原始用户名（不带oidc前缀）")
    fetch_department_info: bool = Field(default=False, description="是否从OIDC中获取部门信息")
    department_claim: str = Field(default="department", description="部门信息映射字段")
    force_prompt_login: bool = Field(default=False, description="是否强制用户重新登录（添加prompt=login参数）")

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
            use_raw_username=os.environ.get("OIDC_USE_RAW_USERNAME", "false").lower() == "true",
            fetch_department_info=os.environ.get("OIDC_FETCH_DEPARTMENT_INFO", "false").lower() == "true",
            department_claim=_env("OIDC_DEPARTMENT_CLAIM", "department"),
            force_prompt_login=os.environ.get("OIDC_FORCE_PROMPT_LOGIN", "true").lower() == "true",
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

        # 如果配置强制登录，添加 prompt=login 参数
        if oidc_config.force_prompt_login:
            params["prompt"] = "login"

        query_string = urllib.parse.urlencode(params)
        return f"{metadata.authorization_endpoint}?{query_string}"

    @classmethod
    async def exchange_code_for_token(cls, code: str) -> dict[str, Any] | None:
        """用授权码从 provider 换取令牌。"""
        metadata = await cls.get_metadata()
        return await exchange_code_for_token(metadata, oidc_config, code) if metadata else None

    @classmethod
    async def get_userinfo(cls, access_token: str) -> dict[str, Any] | None:
        """从 provider 读取用户声明。"""
        metadata = await cls.get_metadata()
        return await get_userinfo(metadata, access_token) if metadata else None

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

        department_name = None
        department_description = None
        if oidc_config.fetch_department_info:
            department_name = userinfo.get(oidc_config.department_claim)
            if not department_name:
                department_name = userinfo.get("department")

            # 获取部门描述
            department_description = userinfo.get("department_description")
            if not department_description:
                department_description = userinfo.get("department_desc")

        return {
            "sub": sub,
            "username": username,
            "email": email,
            "name": name,
            "department_name": department_name,
            "department_description": department_description,
            "raw": userinfo,
        }


async def get_or_create_oidc_department(
    db,
    dept_name_from_oidc: str | None = None,
    dept_desc_from_oidc: str | None = None,
) -> Department | None:
    """获取或创建 OIDC 用户的部门"""
    # 清理并验证从 OIDC 获取的部门名称
    processed_dept_name = None
    processed_dept_desc = None

    if dept_name_from_oidc:
        # 去除首尾空格
        processed_dept_name = dept_name_from_oidc.strip()
        # 截断到 50 字符（匹配数据库限制）
        if len(processed_dept_name) > 50:
            processed_dept_name = processed_dept_name[:50]
        # 如果处理后为空，放弃使用
        if not processed_dept_name:
            processed_dept_name = None

    # 清理并验证从 OIDC 获取的部门描述
    if dept_desc_from_oidc:
        processed_dept_desc = dept_desc_from_oidc.strip()
        # 截断到 255 字符（匹配数据库限制）
        if len(processed_dept_desc) > 255:
            processed_dept_desc = processed_dept_desc[:255]
        if not processed_dept_desc:
            processed_dept_desc = None

    # 最终确定部门名称：优先使用处理后的OIDC部门名称，否则使用默认部门名称
    final_dept_name = processed_dept_name or oidc_config.default_department
    # 最终确定部门描述：优先使用处理后的OIDC部门描述，否则使用默认描述
    final_dept_desc = processed_dept_desc or f"{final_dept_name}部门"

    result = await db.execute(select(Department).filter(Department.name == final_dept_name))
    dept = result.scalar_one_or_none()

    if dept:
        # 部门已存在，直接返回
        logger.info(f"Using existing department: {final_dept_name}")
        return dept

    # 部门不存在，创建新部门
    dept = Department(
        name=final_dept_name,
        description=final_dept_desc,
    )
    try:
        async with db.begin_nested():
            db.add(dept)
            await db.flush()
        logger.info(f"Created OIDC department: {final_dept_name}")
    except IntegrityError:
        # 并发创建时部门可能已存在，再次查询
        result = await db.execute(select(Department).filter(Department.name == final_dept_name))
        dept = result.scalar_one_or_none()
        if dept is None:
            raise

    return dept


async def find_user_by_oidc_sub(db, sub: str) -> User | None:
    """通过 OIDC sub 查找用户"""
    # 方法1: 检查是否有用户的 uid 直接等于 "oidc:{sub}"（标准 OIDC 用户）
    standard_oidc_uid = f"oidc:{sub}"
    # 占位绑定记录会被标记为 is_deleted=1，但我们仍需要查询它们来获取绑定关系
    result = await db.execute(select(User).filter(User.uid == standard_oidc_uid, User.is_deleted == 0, User.user_kind == "human"))
    user = result.scalar_one_or_none()
    if user:
        return user

    # 绑定占位用户被标记为 is_deleted=1，需要包括deleted来查询
    binding_result = await db.execute(
        select(User).filter(User.uid.like(f"{standard_oidc_uid}:%"), User.is_deleted.in_([0, 1])).order_by(User.id.asc())
    )
    binding_users = list(binding_result.scalars().all())
    if binding_users:
        for placeholder in binding_users:
            target_user_id = _extract_oidc_placeholder_target_user_id(placeholder.uid)
            if target_user_id is None:
                continue
            result = await db.execute(select(User).filter(User.id == target_user_id, User.is_deleted == 0, User.user_kind == "human"))
            target_user = result.scalar_one_or_none()
            if target_user:
                logger.debug(f"Resolved OIDC binding placeholder {placeholder.uid} to user {target_user_id}")
                return target_user

    return None


async def find_deleted_oidc_user_by_sub(db, sub: str) -> User | None:
    """查找已注销的 OIDC 账户（直接 uid 记录或绑定占位记录）"""
    oidc_uid = f"oidc:{sub}"

    result = await db.execute(select(User).filter(User.uid == oidc_uid, User.is_deleted == 1, User.user_kind == "human"))
    deleted_user = result.scalar_one_or_none()
    if deleted_user:
        return deleted_user

    binding_result = await db.execute(select(User).filter(User.uid.like(f"{oidc_uid}:%"), User.is_deleted == 1).order_by(User.id.asc()))
    binding_users = list(binding_result.scalars().all())
    if binding_users:
        for placeholder in binding_users:
            target_user_id = _extract_oidc_placeholder_target_user_id(placeholder.uid)
            if target_user_id is None:
                continue
            result = await db.execute(select(User).filter(User.id == target_user_id, User.is_deleted == 1, User.user_kind == "human"))
            target_user = result.scalar_one_or_none()
            if target_user:
                return target_user
    return None


def _extract_oidc_placeholder_target_user_id(uid: str) -> int | None:
    """从占位 uid 中解析真实用户 ID，允许 sub 中包含冒号。"""
    value = str(uid or "").strip()
    if not value.startswith("oidc:"):
        return None

    # 占位格式始终以 `:{target_user_id}` 结尾，因此从右侧拆分即可避免 sub 中的冒号干扰。
    try:
        _prefix, target_user_id = value.rsplit(":", 1)
        return int(target_user_id)
    except ValueError:
        return None


async def create_oidc_binding_placeholder(db, sub: str, target_user: User) -> None:
    """创建 OIDC sub 绑定占位用户（仅用于记录绑定关系，不用于登录）

    在 use_raw_username 模式下，我们创建一个占位用户格式: oidc:{sub}:{target_user_id},
    占位用户标记为 is_deleted=1（不参与实际登录），仅用于存储绑定关系，
    find_user_by_oidc_sub 查询时会读取该占位记录并解析出绑定的真实用户，
    这样就能在不修改User表结构的前提下，保持绑定关系可验证，防止账号冒用。

    使用传入的同一个 db session，避免跨session一致性问题。
    """
    # 占位用户格式: oidc:{sub}:{target_user_id}，这样find_user_by_oidc_sub可以解析出目标用户ID
    oidc_placeholder_id = f"oidc:{sub}:{target_user.id}"
    # 占位用户标记为 deleted，查询时需要特别包括deleted才能找到
    result = await db.execute(select(User).filter(User.uid == oidc_placeholder_id, User.is_deleted.in_([0, 1])))
    if result.scalar_one_or_none():
        # 占位用户已存在，无需重复创建
        return

    # 创建占位用户：使用随机密码，标记为deleted，不用于实际登录，仅存储绑定关系
    random_password = secrets.token_urlsafe(32)
    password_hash = AuthUtils.hash_password(random_password)

    # username 使用 oidc-binding-{sub_hash} 避免冲突，sub_hash 基于完整 sub 生成
    sub_hash = hashlib.sha256(sub.encode()).hexdigest()[:8]
    username = f"oidc-binding-{sub_hash}"

    placeholder_user = User(
        username=username,
        uid=oidc_placeholder_id,
        phone_number=None,
        avatar=None,
        password_hash=password_hash,
        role=target_user.role,
        department_id=target_user.department_id,
        is_deleted=1,  # 标记为deleted，不参与实际登录
        last_login=utc_now(),
    )

    try:
        async with db.begin_nested():
            db.add(placeholder_user)
            await db.flush()
        logger.info(f"Created OIDC binding placeholder (deleted) for sub {sub} -> user {target_user.id} ({target_user.uid})")
    except IntegrityError:
        # 只接受同一目标的并发绑定，其他唯一约束冲突不能伪装成功。
        bound_user = await find_user_by_oidc_sub(db, sub)
        if bound_user is None or bound_user.id != target_user.id:
            raise
        logger.info(f"OIDC binding placeholder already exists for sub {sub}")


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

    raise OperationFailedError("无法生成可用用户名，请联系管理员")


async def create_oidc_user(db, user_info: dict, department_id: int | None = None) -> User:
    """创建 OIDC 用户"""
    user_repo = UserRepository(db)

    sub = user_info["sub"]
    preferred_username = user_info["name"] or user_info["username"]

    # 根据配置决定 uid 是否带 oidc 前缀
    if oidc_config.use_raw_username:
        uid = user_info["username"]
        result = await db.execute(select(User).filter(User.uid == uid))
        existing_user = result.scalar_one_or_none()
        if existing_user and existing_user.user_kind == "end_user":
            raise PermissionDeniedError("终端用户不能用于 OIDC 登录")
        if existing_user and existing_user.is_deleted:
            existing_user = None
        if existing_user:
            # 用户已存在，必须验证当前sub是否已经绑定到这个用户
            # 如果sub未绑定该用户，不能直接复用，存在账号冒用风险
            user_by_sub = await find_user_by_oidc_sub(db, sub)
            if user_by_sub and user_by_sub.id == existing_user.id:
                # sub 已经正确绑定到该用户，允许返回
                logger.info(f"User with raw uid {uid} already exists and bound to sub {sub}, returning existing user")
                return existing_user
            elif user_by_sub is None:
                # sub 尚未绑定任何用户，可以将sub绑定到这个现有用户
                logger.info(f"Binding new OIDC sub {sub} to existing user with raw uid {uid}")
                await create_oidc_binding_placeholder(db, sub, existing_user)
                return existing_user
            else:
                # sub 已经绑定到另一个用户，冲突，拒绝创建
                logger.warning(
                    f"Cannot create OIDC user with raw uid {uid}: sub {sub} is already bound to another user {user_by_sub.id}, conflict"
                )
                raise StateConflictError(f"UID {uid} 已存在且OIDC标识 {sub} 已绑定到其他账号，请联系管理员处理冲突")
    else:
        uid = f"oidc:{sub}"

    random_password = secrets.token_urlsafe(32)
    password_hash = AuthUtils.hash_password(random_password)

    username = await build_unique_oidc_username(db, preferred_username, sub)

    for retry_index in range(3):
        try:
            async with db.begin_nested():
                new_user = await user_repo.create(
                    {
                        "username": username,
                        "uid": uid,
                        "phone_number": None,
                        "avatar": None,
                        "password_hash": password_hash,
                        "role": oidc_config.default_role,
                        "department_id": department_id,
                        "last_login": utc_now(),
                    }
                )
                logger.info(f"Created OIDC user: {new_user.username} ({uid})")

                # use_raw_username 模式下，创建占位用户记录绑定关系
                if oidc_config.use_raw_username:
                    await create_oidc_binding_placeholder(db, sub, new_user)

            return new_user
        except IntegrityError:
            existing_user = await find_user_by_oidc_sub(db, sub)
            if existing_user:
                if oidc_config.use_raw_username and existing_user.uid != uid:
                    raise StateConflictError("OIDC标识已绑定到其他账号")
                return existing_user
            username = await build_unique_oidc_username(db, f"{preferred_username}-{retry_index + 2}", sub)

    raise OperationFailedError("创建 OIDC 用户失败，请重试")


async def restore_deleted_oidc_user(db, deleted_user: User, user_info: dict) -> User:
    """恢复已注销的 OIDC 用户并返回可登录用户"""
    if deleted_user.user_kind == "end_user":
        raise PermissionDeniedError("终端用户不能用于 OIDC 登录")
    preferred_username = user_info["name"] or user_info["username"]

    deleted_user.is_deleted = 0
    deleted_user.deleted_at = None
    deleted_user.last_login = utc_now()
    deleted_user.phone_number = None
    deleted_user.avatar = None

    if deleted_user.username.startswith("已注销用户-"):
        deleted_user.username = await build_unique_oidc_username(db, preferred_username, user_info["sub"])

    if deleted_user.password_hash == "DELETED":
        random_password = secrets.token_urlsafe(32)
        deleted_user.password_hash = AuthUtils.hash_password(random_password)

    await db.flush()
    logger.info(f"Restored deleted OIDC user: {deleted_user.username} ({deleted_user.uid})")
    return deleted_user


async def update_oidc_user_login(db, user: User) -> None:
    """更新 OIDC 用户登录时间"""
    user.last_login = utc_now()
    await db.flush()


async def find_oidc_user_by_raw_username(db, username: str) -> User | None:
    """按原始用户名查找 OIDC 候选用户。"""
    result = await db.execute(select(User).filter(User.uid == username))
    return result.scalar_one_or_none()


async def get_oidc_department_name(db, department_id: int) -> str | None:
    """读取 OIDC 登录用户的部门名称。"""
    result = await db.execute(select(Department.name).filter(Department.id == department_id))
    return result.scalar_one_or_none()
