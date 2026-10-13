"""认证服务。"""

import hashlib
import secrets
import string
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.modules.identity.models import APIKey, CLIAuthSession, Department, User
from yuxi.modules.identity.repositories.api_keys import (
    APIKeyDepartmentConflict,
    APIKeyIdempotencyConflict,
    APIKeySubjectUnavailable,
)
from yuxi.modules.identity.security import AuthUtils
from yuxi.modules.identity.services.api_keys import issue_api_key
from yuxi.shared.datetime import utc_now

CLI_AUTH_SESSION_TTL_SECONDS = 10 * 60
CLI_AUTH_POLL_INTERVAL_SECONDS = 2
CLI_AUTH_DEFAULT_KEY_NAME = "Yuxi CLI"
CLI_AUTH_USER_CODE_ALPHABET = "".join(ch for ch in string.ascii_uppercase + string.digits if ch not in "0O1I")

CLI_AUTH_STATUS_PENDING = "pending"
CLI_AUTH_STATUS_APPROVED = "approved"
CLI_AUTH_STATUS_CONSUMED = "consumed"
CLI_AUTH_STATUS_EXPIRED = "expired"


@dataclass
class CLIAuthError(Exception):
    code: str
    message: str
    status_code: int = 400


async def create_cli_auth_session(db: AsyncSession, key_name: str | None = None) -> tuple[CLIAuthSession, str]:
    device_code = _generate_device_code()
    now = utc_now()
    session = CLIAuthSession(
        device_code_hash=_hash_secret(device_code),
        user_code=await _generate_unique_user_code(db),
        status=CLI_AUTH_STATUS_PENDING,
        key_name=(key_name or CLI_AUTH_DEFAULT_KEY_NAME).strip() or CLI_AUTH_DEFAULT_KEY_NAME,
        created_at=now,
        expires_at=now + timedelta(seconds=CLI_AUTH_SESSION_TTL_SECONDS),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session, device_code


async def get_cli_auth_session_for_user(db: AsyncSession, user_code: str, *, for_update: bool = False) -> CLIAuthSession:
    stmt = select(CLIAuthSession).filter(CLIAuthSession.user_code == user_code.strip().upper())
    if for_update:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None:
        raise CLIAuthError("not_found", "授权会话不存在", status_code=404)
    if _expire_if_needed(session):
        await db.commit()
        raise CLIAuthError("expired_token", "授权会话已过期", status_code=410)
    return session


async def approve_cli_auth_session(db: AsyncSession, user_code: str, user: User) -> CLIAuthSession:
    session = await get_cli_auth_session_for_user(db, user_code, for_update=True)
    if session.status == CLI_AUTH_STATUS_CONSUMED:
        raise CLIAuthError("already_consumed", "授权会话已完成", status_code=409)
    if session.status == CLI_AUTH_STATUS_APPROVED:
        raise CLIAuthError("already_approved", "授权会话已批准", status_code=409)
    if session.status != CLI_AUTH_STATUS_PENDING:
        raise CLIAuthError("invalid_state", "授权会话状态无效", status_code=409)

    session.status = CLI_AUTH_STATUS_APPROVED
    session.approved_user_id = user.id
    session.approved_at = utc_now()
    await db.commit()
    await db.refresh(session)
    return session


async def exchange_cli_auth_token(db: AsyncSession, device_code: str) -> dict:
    result = await db.execute(select(CLIAuthSession).filter(CLIAuthSession.device_code_hash == _hash_secret(device_code)).with_for_update())
    session = result.scalar_one_or_none()
    if session is None:
        raise CLIAuthError("invalid_request", "授权会话不存在", status_code=404)
    if _expire_if_needed(session):
        await db.commit()
        raise CLIAuthError("expired_token", "授权会话已过期", status_code=410)
    if session.status == CLI_AUTH_STATUS_PENDING:
        raise CLIAuthError("authorization_pending", "等待浏览器授权", status_code=400)
    if session.status == CLI_AUTH_STATUS_CONSUMED:
        if session.expires_at <= utc_now():
            raise CLIAuthError("expired_token", "授权结果重放窗口已过期", status_code=410)
        return await _build_cli_exchange_result(db, session)
    if session.status != CLI_AUTH_STATUS_APPROVED or not session.approved_user_id:
        raise CLIAuthError("invalid_state", "授权会话状态无效", status_code=409)

    try:
        try:
            api_key, _ = await issue_api_key(
                db,
                derivation_context=f"cli-session:{session.device_code_hash}",
                request_id=f"c:{session.device_code_hash[:62]}",
                name=session.key_name,
                user_id=session.approved_user_id,
                department_id=None,
                expires_at=None,
                created_by=str(session.approved_user_id),
            )
        except APIKeySubjectUnavailable as exc:
            raise CLIAuthError("invalid_user", "授权用户不存在", status_code=409) from exc
        except (APIKeyIdempotencyConflict, APIKeyDepartmentConflict) as exc:
            raise CLIAuthError("invalid_state", "授权会话无法创建 API Key", status_code=409) from exc

        session.status = CLI_AUTH_STATUS_CONSUMED
        session.api_key_id = api_key.id
        session.consumed_at = utc_now()
        await db.commit()
        await db.refresh(api_key)
        return await _build_cli_exchange_result(db, session)
    except BaseException:
        await db.rollback()
        raise


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _generate_device_code() -> str:
    return f"yxcli_{secrets.token_urlsafe(32)}"


def _generate_user_code() -> str:
    raw = "".join(secrets.choice(CLI_AUTH_USER_CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


async def _generate_unique_user_code(db: AsyncSession) -> str:
    for _ in range(10):
        user_code = _generate_user_code()
        result = await db.execute(select(CLIAuthSession.id).filter(CLIAuthSession.user_code == user_code))
        if result.scalar_one_or_none() is None:
            return user_code
    raise RuntimeError("无法生成唯一 CLI 授权码")


def _expire_if_needed(session: CLIAuthSession, now=None) -> bool:
    now = now or utc_now()
    if session.status in {CLI_AUTH_STATUS_PENDING, CLI_AUTH_STATUS_APPROVED} and session.expires_at <= now:
        session.status = CLI_AUTH_STATUS_EXPIRED
        return True
    return False


async def _build_cli_exchange_result(db: AsyncSession, session: CLIAuthSession) -> dict:
    """从 consumed 会话确定性重放同一密钥响应，不读取或保存明文。"""

    if not session.approved_user_id or not session.api_key_id:
        raise CLIAuthError("invalid_state", "授权会话缺少已提交的密钥事实", status_code=409)
    result = await db.execute(
        select(User, Department.name, APIKey)
        .outerjoin(Department, User.department_id == Department.id)
        .join(APIKey, APIKey.id == session.api_key_id)
        .filter(User.id == session.approved_user_id, User.is_deleted == 0)
    )
    row = result.one_or_none()
    if row is None:
        raise CLIAuthError("invalid_user", "授权用户或 API Key 不存在", status_code=409)
    user, department_name, api_key = row
    if not api_key.is_valid():
        raise CLIAuthError("api_key_revoked", "授权会话对应的 API Key 已失效", status_code=409)
    full_key, key_hash, _ = AuthUtils.derive_api_key(
        f"cli-session:{session.device_code_hash}",
        user.id,
    )
    if key_hash != api_key.key_hash:
        raise CLIAuthError("secret_replay_unavailable", "历史授权密钥无法安全重放", status_code=409)

    user_data = user.to_dict()
    user_data["department_name"] = department_name
    return {
        "api_key": api_key.to_dict(),
        "secret": full_key,
        "user": user_data,
    }
