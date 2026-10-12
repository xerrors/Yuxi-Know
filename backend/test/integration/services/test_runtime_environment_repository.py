"""同步沙盒读取与异步仓储使用同一 PostgreSQL 配置记录。"""

import asyncio
import os

import pytest
from sqlalchemy import delete, text
from sqlalchemy.engine import make_url

from test.integration.support.module_audit import isolated_audit_store
from yuxi.modules.agents.models.definitions import AgentEnv
from yuxi.modules.agents.repositories.environment import AgentEnvRepository
from yuxi.modules.agents.runtime.sandbox.provider import load_user_agent_env
from yuxi.modules.identity.models import User
from yuxi.shared.datetime import utc_now

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


@pytest.mark.parametrize("driver", ["postgresql", "postgresql+asyncpg", "postgresql+psycopg"])
async def test_sync_provider_matches_repository_after_replace_and_delete(monkeypatch, driver):
    """真实 PG 对照缺失、替换与删除，不复用异步连接池执行同步读取。"""
    original_url = make_url(os.environ["POSTGRES_URL"])
    async with isolated_audit_store(monkeypatch) as (_, sessions):
        async with sessions() as db:
            schema = await db.scalar(text("SELECT current_schema()"))
            db.add(User(uid="env-owner", username="env-owner", password_hash="fixture", role="user"))
            await db.commit()
            scoped_url = original_url.set(drivername=driver).update_query_dict({"options": f"-csearch_path={schema}"})
            with monkeypatch.context() as scoped:
                scoped.setenv("POSTGRES_URL", scoped_url.render_as_string(hide_password=False))
                assert await asyncio.to_thread(load_user_agent_env, "env-owner") == {}
                repo = AgentEnvRepository(db)
                for value in ({"AUDIT_VALUE": "first", "EMPTY": ""}, {"AUDIT_VALUE": "replaced"}):
                    await repo.upsert(uid="env-owner", env=value, updated_at=utc_now())
                    await db.commit()
                    async with sessions() as oracle:
                        persisted = await AgentEnvRepository(oracle).get_by_uid("env-owner")
                        assert await asyncio.to_thread(load_user_agent_env, "env-owner") == persisted.env == value
                await db.execute(delete(AgentEnv).where(AgentEnv.uid == "env-owner"))
                await db.commit()
                assert await asyncio.to_thread(load_user_agent_env, "env-owner") == {}
                db.add(AgentEnv(uid="env-owner", env=["invalid-object"]))
                await db.commit()
                with pytest.raises(ValueError, match="must be an object"):
                    await asyncio.to_thread(load_user_agent_env, "env-owner")
                scoped.setenv(
                    "POSTGRES_URL",
                    scoped_url.update_query_dict({"options": "-csearch_path=missing_audit_schema"}).render_as_string(hide_password=False),
                )
                with pytest.raises(RuntimeError, match="failed to load Agent environment"):
                    await asyncio.to_thread(load_user_agent_env, "env-owner")
