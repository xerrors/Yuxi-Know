"""Agent 环境变量数据访问层。"""

import json
import os
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.infrastructure.postgres.connection import postgres_conninfo
from yuxi.modules.agents.models.definitions import AgentEnv


@dataclass(frozen=True)
class AgentEnvWriteResult:
    """Agent 环境变量写入结果。"""

    env: dict[str, str]
    updated_at: datetime | None
    changed: bool = False


class AgentEnvRepository:
    """封装用户级 Agent 环境变量的读取与幂等 upsert。"""

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    @staticmethod
    def load_for_sync_runtime(uid: str) -> dict[str, str]:
        """同步沙盒消费者从同一用户配置记录读取环境变量。"""
        import psycopg

        conninfo = postgres_conninfo(os.getenv("POSTGRES_URL", ""))
        if not conninfo:
            raise RuntimeError("POSTGRES_URL is required for Agent environment")
        try:
            with psycopg.connect(conninfo, connect_timeout=3) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT env FROM agent_envs WHERE uid = %s", (uid,))
                    row = cursor.fetchone()
        except Exception as exc:
            raise RuntimeError("failed to load Agent environment") from exc
        if not row:
            return {}
        value = row[0]
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict):
            raise ValueError("stored Agent environment must be an object")
        return {str(key): "" if item is None else str(item) for key, item in value.items() if str(key)}

    async def get_by_uid(self, uid: str) -> AgentEnv | None:
        """读取指定用户的 Agent 环境变量。"""
        result = await self.db_session.execute(select(AgentEnv).where(AgentEnv.uid == uid).execution_options(populate_existing=True))
        return result.scalar_one_or_none()

    async def upsert(self, *, uid: str, env: dict[str, str], updated_at: datetime) -> AgentEnvWriteResult:
        """内容未变时复用旧时间，否则原子写入完整环境变量集合。"""
        current = await self.get_by_uid(uid)
        if current is not None and (current.env or {}) == env:
            return AgentEnvWriteResult(env=current.env or {}, updated_at=current.updated_at)

        statement = (
            pg_insert(AgentEnv)
            .values(uid=uid, env=env, updated_at=updated_at)
            .on_conflict_do_update(
                index_elements=[AgentEnv.uid],
                set_={"env": env, "updated_at": updated_at},
            )
        )
        await self.db_session.execute(statement)
        return AgentEnvWriteResult(env=env, updated_at=updated_at, changed=True)
