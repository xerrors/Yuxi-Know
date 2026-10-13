"""密码登录用例及账号状态转换。"""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.modules.identity.repositories.departments import DepartmentRepository
from yuxi.modules.identity.repositories.users import UserRepository
from yuxi.modules.identity.security import AuthUtils
from yuxi.modules.identity.services.login_limits import check_login_rate_limit, clear_login_failures, record_login_failure
from yuxi.shared.datetime import utc_now
from yuxi.modules.identity.services.login import login_result


@dataclass
class PasswordLoginRejected(Exception):
    """业务拒绝原因，由入口适配为协议错误。"""

    reason: Literal["rate_limited", "unknown_account", "deleted", "locked", "newly_locked", "wrong_password"]
    remaining_seconds: int | None = None


async def login_with_password(db: AsyncSession, identifier: str, password: str, client_ip: str) -> dict:
    """执行密码登录，提交失败计数或成功状态后才返回结果。"""
    allowed, retry_after = await check_login_rate_limit(client_ip, identifier)
    if not allowed:
        raise PasswordLoginRejected("rate_limited", retry_after)

    repository = UserRepository(db)
    user = await repository.get_by_login_identifier(identifier)
    if not user or user.user_kind == "end_user":
        await record_login_failure(client_ip, identifier)
        raise PasswordLoginRejected("unknown_account")
    if user.is_deleted:
        raise PasswordLoginRejected("deleted")
    if user.is_login_locked():
        raise PasswordLoginRejected("locked", user.get_remaining_lock_time())

    # 过期锁定先清零，避免解锁后的首次失败立即再次锁定。
    if user.login_locked_until is not None:
        user.reset_failed_login()
        await repository.save(user)

    if not AuthUtils.verify_password(user.password_hash, password):
        await record_login_failure(client_ip, identifier)
        user.increment_failed_login()
        await repository.save(user)
        await db.commit()
        if user.is_login_locked():
            raise PasswordLoginRejected("newly_locked", user.get_remaining_lock_time())
        raise PasswordLoginRejected("wrong_password")

    user.reset_failed_login()
    user.last_login = utc_now()
    await repository.save(user)
    await clear_login_failures(client_ip, identifier)
    access_token = AuthUtils.create_access_token({"sub": str(user.id), "auth_method": "password"})
    department_name = await DepartmentRepository(db).get_name_by_id(user.department_id) if user.department_id else None
    await db.commit()
    return login_result(user, access_token, department_name)
