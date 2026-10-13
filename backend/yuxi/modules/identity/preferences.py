"""用户级配置模块。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.modules.identity.models import UserConfig as UserConfigRecord
from yuxi.shared.datetime import format_utc_datetime


class UserConfigSchema(BaseModel):
    """用户专属配置 schema。"""

    enable_memory: bool = Field(default=True, description="是否启用 Memory")

    model_config = ConfigDict(extra="forbid")


class UserConfig:
    """用户级配置访问器。每次加载都从 PostgreSQL 查询，不做进程缓存。"""

    def __init__(self, uid: str, schema: UserConfigSchema | None = None, updated_at: datetime | None = None):
        self.uid = uid
        self.schema = schema or UserConfigSchema()
        self.updated_at = updated_at

    @classmethod
    async def load(cls, db: AsyncSession, uid: str) -> UserConfig:
        result = await db.execute(select(UserConfigRecord).filter(UserConfigRecord.uid == uid))
        record = result.scalar_one_or_none()
        if record is None:
            return cls(uid=uid)
        return cls(
            uid=uid,
            schema=UserConfigSchema(enable_memory=bool(record.enable_memory)),
            updated_at=record.updated_at,
        )

    def dump_config(self) -> dict[str, str | bool | None]:
        return {
            "uid": self.uid,
            "enable_memory": self.schema.enable_memory,
            "updated_at": format_utc_datetime(self.updated_at),
        }
