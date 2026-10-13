"""Public API 凭据验证与 App 终端用户身份解析。"""

import hashlib

from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.modules.identity.models import APIKey, User
from yuxi.modules.identity.repositories.api_keys import APIKeyRepository
from yuxi.modules.identity.repositories.users import UserRepository

DEFAULT_END_USER_ID = "__default__"


class PublicIdentityDenied(Exception):
    """凭据不允许声明该终端身份或身份已停用。"""


class InvalidEndUserId(ValueError):
    """调用方声明的终端用户标识不符合约束。"""


async def verify_api_key(key: str, db: AsyncSession) -> tuple[User | None, APIKey | None]:
    """校验凭据有效性及其绑定的产品用户。"""
    key_hash = hashlib.sha256(key.encode()).hexdigest()

    api_key = await APIKeyRepository(db).get_by_hash(key_hash)

    if api_key is None or not api_key.is_valid():
        return None, None

    user = await UserRepository(db).get_by_id(api_key.user_id)
    if user and not user.is_deleted and user.user_kind == "human":
        return user, api_key

    return None, None


async def resolve_public_user(*, owner: User, api_key: APIKey | None, end_user_id: str | None, db: AsyncSession) -> User:
    """按产品凭据或 App 凭据解析资源用户并提交终端身份。"""
    if api_key is None:
        if end_user_id is not None:
            raise PublicIdentityDenied("X-End-User-Id 仅适用于 API Key")
        return owner
    if not api_key.app_id:
        if api_key.access_level != "full":
            raise PublicIdentityDenied("Agents Public API 需要绑定 app_id 的 API Key")
        if end_user_id is not None:
            raise PublicIdentityDenied("无 APP 的 full Key 不接受 X-End-User-Id")
        return owner

    identity = DEFAULT_END_USER_ID if end_user_id is None else end_user_id
    if not identity or identity != identity.strip() or len(identity) > 128:
        raise InvalidEndUserId("X-End-User-Id 必须为 1 至 128 个无首尾空白的字符")

    user = await UserRepository(db).get_or_create_public_end_user(owner=owner, app_id=api_key.app_id, end_user_id=identity)
    if user.is_deleted:
        raise PublicIdentityDenied("终端用户已停用")
    await db.commit()
    return user
