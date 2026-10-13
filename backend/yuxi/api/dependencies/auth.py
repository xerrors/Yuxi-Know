from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.modules.identity.models import User
from yuxi.modules.identity.security import AuthUtils
from yuxi.modules.identity.services.public_auth import verify_api_key
from yuxi.shared.datetime import utc_now

# 定义OAuth2密码承载器，指定token URL
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

KNOWLEDGE_TOOL_PATHS = frozenset(
    f"/api/v1/knowledge/tools/{name}"
    for name in (
        "list_kbs",
        "query_kb",
        "open_kb_document",
        "find_kb_document",
        "search_file",
    )
)


# 获取数据库会话（异步版本）
async def get_db():
    async with pg_manager.get_async_session_context() as db:
        yield db


# 获取当前用户（异步版本）
async def get_current_user(
    request: Request,
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if authorization is None:
        return None

    if not authorization.startswith("Bearer "):
        return None

    token = authorization.split("Bearer ")[1]
    if not token:
        return None

    # 根据 token 前缀判断认证方式
    if token.startswith("yxkey_"):
        # API Key 认证
        user, api_key_obj = await verify_api_key(token, db)
        if user is not None and api_key_obj is not None:
            request.state.api_key = api_key_obj
            request.state.app_id = api_key_obj.app_id
            route_path = request.scope.get("path", "")
            permitted_root = "/api/v1/agents" if api_key_obj.access_level == "agents" else None
            if api_key_obj.access_level != "full" and not (
                (permitted_root and (route_path == permitted_root or route_path.startswith(f"{permitted_root}/")))
                or (api_key_obj.access_level == "knowledge" and route_path in KNOWLEDGE_TOOL_PATHS)
            ):
                raise HTTPException(status_code=403, detail="该 API Key 无权访问此 API 面")
            api_key_obj.last_used_at = utc_now()
            await db.commit()
        return user

    # JWT Token 认证
    try:
        payload = AuthUtils.verify_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).filter(User.id == int(user_id), User.is_deleted == 0))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    if user.user_kind == "end_user":
        raise HTTPException(status_code=403, detail="终端用户只能通过 Public API 使用")
    if user.is_login_locked():
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="登录被锁定，请稍后重试",
            headers={"X-Lock-Remaining": str(user.get_remaining_lock_time())},
        )

    if payload.get("oidc_sid"):
        from yuxi.modules.identity.oidc import oidc_config
        from yuxi.modules.identity.repositories.oidc import OIDCRepository
        from yuxi.shared.errors import PermissionDeniedError

        try:
            if not oidc_config.enabled:
                raise PermissionDeniedError("OIDC 未启用")
            await OIDCRepository(db).active_session(payload["oidc_sid"], user.id, oidc_config.issuer_url)
        except PermissionDeniedError as exc:
            raise credentials_exception from exc
    else:
        from yuxi.modules.identity.repositories.login_sessions import LoginSessionRepository

        if await LoginSessionRepository(db).is_revoked(token):
            raise credentials_exception
    if not payload.get("oidc_sid") and payload.get("auth_method") != "password":
        from yuxi.modules.identity.models import OIDCIdentity

        # 旧标准账号及同名绑定账号的 JWT 无法证明登录来源，升级后必须重新认证。
        bound = await db.scalar(select(OIDCIdentity.id).where(OIDCIdentity.user_id == user.id).limit(1))
        if bound or (user.uid and user.uid.startswith("oidc:")):
            raise credentials_exception
    request.state.jwt_token = token
    request.state.jwt_payload = payload
    return user


# 获取已登录用户（抛出401如果未登录）
async def get_required_user(user: User | None = Depends(get_current_user)):
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请登录后再访问",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.department_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前用户未绑定部门",
        )
    return user


# 获取管理员用户
async def get_admin_user(current_user: User = Depends(get_required_user)):
    if current_user.role not in ["admin", "superadmin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user


# 获取超级管理员用户
async def get_superadmin_user(current_user: User = Depends(get_required_user)):
    if current_user.role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要超级管理员权限",
        )
    return current_user
