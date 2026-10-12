"""Agent 定义和环境用例以真实持久结果验证事务归属。"""

import pytest
from sqlalchemy import select

from test.integration.support.module_audit import isolated_audit_store
from yuxi.modules.agents.models.definitions import Agent
from yuxi.modules.agents.repositories.definitions import AgentRepository
from yuxi.modules.agents.services.definitions import ensure_default_agent_definition, update_agent_definition
from yuxi.modules.agents.services.environment import write_agent_env
from yuxi.modules.agents.repositories.environment import AgentEnvRepository
from yuxi.modules.identity.models import User

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


async def test_repository_create_is_not_published_until_use_case_commit(monkeypatch):
    """仓储 flush 不可见，回滚后另一事务没有创建事实。"""
    async with isolated_audit_store(monkeypatch) as (_, sessions):
        async with sessions() as db:
            owner = User(uid="owner", username="owner", role="user", password_hash="fixture")
            db.add(owner)
            await db.commit()
            await AgentRepository(db).create(
                name="Uncommitted", backend_id="ChatbotAgent", slug="uncommitted", creator=owner, created_by=owner.uid
            )
            async with sessions() as oracle:
                assert await AgentRepository(oracle).get_by_slug("uncommitted") is None
            await db.rollback()
        async with sessions() as oracle:
            assert await AgentRepository(oracle).get_by_slug("uncommitted") is None


async def test_update_failure_rolls_back_before_caller_can_commit_other_work(monkeypatch):
    """绑定后半流程失败后，即使调用者继续提交也不能泄漏定义补丁。"""
    async with isolated_audit_store(monkeypatch) as (_, sessions):
        async with sessions() as db:
            owner = User(uid="owner", username="owner", role="user", password_hash="fixture")
            db.add(owner)
            db.add(
                Agent(
                    slug="owned",
                    name="Original",
                    backend_id="ChatbotAgent",
                    created_by="owner",
                    visibility="private",
                    share_config={"version": 2, "read_scope": None, "manage_scope": None},
                    config_json={"context": {"skills": []}},
                )
            )
            await db.commit()
            agent = await AgentRepository(db).get_by_slug("owned")

            async def fail_binding(*args, **kwargs):
                """失败发生于实际定义补丁 flush 之后。"""
                raise RuntimeError("binding rejected")

            monkeypatch.setattr("yuxi.modules.agents.services.definitions.commit_agent_definition", fail_binding)
            with pytest.raises(RuntimeError, match="binding rejected"):
                await update_agent_definition(db, agent, name="Must rollback", updater=owner)
            await db.commit()
        async with sessions() as oracle:
            persisted = await AgentRepository(oracle).get_by_slug("owned")
            assert persisted.name == "Original"
            assert persisted.config_json == {"context": {"skills": []}}


async def test_default_and_environment_repeated_writes_keep_persisted_identity_and_time(monkeypatch):
    """默认与用户环境重复读取保持同一记录和修订时间。"""
    async with isolated_audit_store(monkeypatch) as (_, sessions):
        async with sessions() as db:
            db.add(User(uid="owner", username="owner", role="user", password_hash="fixture"))
            await db.commit()
            default = await ensure_default_agent_definition(db)
            original_id, original_time = default.id, default.updated_at
            second = await ensure_default_agent_definition(db)
            assert (second.id, second.updated_at) == (original_id, original_time)
            first_env = await write_agent_env(db, uid="owner", env={" AUDIT_VALUE ": "fixture"})
            second_env = await write_agent_env(db, uid="owner", env={"AUDIT_VALUE": "fixture"})
            assert first_env.changed is True and second_env.changed is False
            assert first_env.updated_at == second_env.updated_at
        async with sessions() as oracle:
            defaults = list(await oracle.scalars(select(Agent).where(Agent.is_default.is_(True))))
            assert [(row.id, row.updated_at) for row in defaults] == [(original_id, original_time)]
            env = await AgentEnvRepository(oracle).get_by_uid("owner")
            assert env.env == {"AUDIT_VALUE": "fixture"}
            assert env.updated_at == first_env.updated_at


async def test_deleted_human_cannot_read_agent_visibility_or_freeze_new_input(monkeypatch):
    """失效超级管理员不能借宽角色可见性读取或冻结新 Input。"""
    from sqlalchemy import func

    from yuxi.modules.agents.models.inputs import AgentInput, AgentInputReceipt
    from yuxi.modules.agents.scope import ActorScope
    from yuxi.modules.agents.services.inputs import create_thread
    from yuxi.shared.errors import ResourceNotFoundError

    async with isolated_audit_store(monkeypatch) as (_, sessions):
        async with sessions() as db:
            inactive = User(uid="inactive", username="inactive", role="superadmin", password_hash="fixture", is_deleted=1)
            db.add(inactive)
            await db.commit()
            await ensure_default_agent_definition(db)
            assert await AgentRepository(db).get_visible_by_slug(slug="assistant", user=inactive) is None
            assert await AgentRepository(db).list_visible(user=inactive) == []
            with pytest.raises(ResourceNotFoundError, match="用户不存在"):
                await create_thread(
                    db=db,
                    scope=ActorScope(uid=inactive.uid, app_id=None),
                    agent_slug="assistant",
                    thread_id="inactive-thread",
                    idempotency_key="inactive-create",
                )
            await db.rollback()
        async with sessions() as oracle:
            assert await oracle.scalar(select(func.count()).select_from(AgentInput)) == 0
            assert await oracle.scalar(select(func.count()).select_from(AgentInputReceipt)) == 0
