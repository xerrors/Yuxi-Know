"""凭据签发、管理和重放；提交属于完整入口用例。"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.modules.identity.models import APIKey, User
from yuxi.modules.identity.repositories.api_keys import APIKeyRepository
from yuxi.modules.identity.security import AuthUtils
from yuxi.shared.datetime import coerce_any_to_utc_datetime
from yuxi.shared.errors import InvalidInputError, PermissionDeniedError, ResourceNotFoundError


async def create_api_key(
    db: AsyncSession,
    *,
    actor: User,
    request_id: str,
    name: str,
    user_id: int | None = None,
    department_id: int | None = None,
    expires_at: str | None = None,
    access_level: str = "full",
    app_id: str | None = None,
) -> dict:
    """提交 Web 凭据创建，保留相同请求的确定性重放。"""
    try:
        if user_id and user_id != actor.id and actor.role != "superadmin":
            raise PermissionDeniedError("无权为其他用户创建 API Key")
        if access_level == "agents" and not app_id:
            raise InvalidInputError("Agents API Key 必须填写 app_id")
        key, secret = await issue_api_key(
            db,
            derivation_context=f"user-request:{request_id}",
            request_id=request_id,
            name=name,
            user_id=user_id or actor.id,
            department_id=department_id,
            expires_at=coerce_any_to_utc_datetime(expires_at) if expires_at else None,
            created_by=str(actor.id),
            access_level=access_level,
            app_id=app_id,
        )
        await db.commit()
        return {"api_key": key.to_dict(), "secret": secret}
    except BaseException:
        await db.rollback()
        raise


async def update_api_key(db: AsyncSession, *, actor: User, api_key_id: int, updates: dict) -> dict:
    """校验合并后的凭据能力并提交变更。"""
    try:
        key = await get_accessible_api_key(APIKeyRepository(db), api_key_id, actor)
        if (updates.get("access_level") or key.access_level) == "agents" and not updates.get("app_id", key.app_id):
            raise InvalidInputError("Agents API Key 必须填写 app_id")
        updates = {name: value for name, value in updates.items() if value is not None or name == "app_id"}
        if "expires_at" in updates:
            updates["expires_at"] = coerce_any_to_utc_datetime(updates["expires_at"])
        await APIKeyRepository(db).update(key, updates)
        await db.commit()
        return {"api_key": key.to_dict()}
    except BaseException:
        await db.rollback()
        raise


async def revoke_api_key(db: AsyncSession, *, actor: User, api_key_id: int) -> None:
    """撤销凭据并保留防止同一请求复活的 tombstone。"""
    try:
        repository = APIKeyRepository(db)
        key = await get_accessible_api_key(repository, api_key_id, actor)
        await repository.delete(key)
        await db.commit()
    except BaseException:
        await db.rollback()
        raise


async def issue_api_key(
    db: AsyncSession,
    *,
    derivation_context: str,
    request_id: str,
    name: str,
    user_id: int,
    department_id: int | None,
    expires_at: datetime | None,
    created_by: str,
    access_level: str = "full",
    app_id: str | None = None,
) -> tuple[APIKey, str]:
    """在调用方事务派生并保存凭据，CLI 会话消费和 Key 必须一起提交。"""
    secret, key_hash, key_prefix = AuthUtils.derive_api_key(derivation_context, user_id)
    key = await APIKeyRepository(db).create(
        key_hash=key_hash,
        key_prefix=key_prefix,
        request_id=request_id,
        name=name,
        user_id=user_id,
        department_id=department_id,
        expires_at=expires_at,
        created_by=created_by,
        access_level=access_level,
        app_id=app_id,
    )
    return key, secret


async def get_accessible_api_key(repository: APIKeyRepository, api_key_id: int, current_user: User) -> APIKey:
    """由仓储执行可见性查询并区分不存在与无权操作。"""
    access = await repository.get_accessible(
        api_key_id=api_key_id,
        requester_user_id=current_user.id,
        is_superadmin=current_user.role == "superadmin",
    )
    if access.api_key is not None:
        return access.api_key
    if not access.exists:
        raise ResourceNotFoundError("API Key 不存在")
    raise PermissionDeniedError("无权操作此 API Key")
