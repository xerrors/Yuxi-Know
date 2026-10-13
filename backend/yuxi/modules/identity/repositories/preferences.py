"""用户偏好写入边界。"""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.modules.identity.models import UserConfig
from yuxi.shared.datetime import utc_now


async def upsert_user_config(db: AsyncSession, *, uid: str, enable_memory: bool):
    """唯一 UID 上原子覆盖偏好，不回滚调用方其他写入。"""
    now = utc_now()
    statement = insert(UserConfig).values(uid=uid, enable_memory=enable_memory, created_at=now, updated_at=now)
    await db.execute(
        statement.on_conflict_do_update(
            index_elements=[UserConfig.uid],
            set_={"enable_memory": enable_memory, "updated_at": now},
        )
    )
    return now
