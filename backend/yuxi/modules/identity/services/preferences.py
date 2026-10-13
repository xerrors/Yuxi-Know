"""用户偏好保存用例。"""

from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.modules.identity.preferences import UserConfig, UserConfigSchema
from yuxi.modules.identity.repositories.preferences import upsert_user_config


async def save_user_config(db: AsyncSession, *, uid: str, schema: UserConfigSchema) -> UserConfig:
    """提交用户配置，失败时不保留部分写入。"""
    try:
        updated_at = await upsert_user_config(db, uid=uid, enable_memory=schema.enable_memory)
        await db.commit()
        return UserConfig(uid=uid, schema=schema, updated_at=updated_at)
    except BaseException:
        await db.rollback()
        raise
