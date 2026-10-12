"""真实 PostgreSQL 验证统一 Session 的队列、树范围和并发领取。"""

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from agent_run_test_helpers import cleanup_agent_run_threads, create_agent_run
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.bootstrap.models import load_models
from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.modules.agents.models.cooperation import CooperationEvent
from yuxi.modules.agents.models.definitions import Agent
from yuxi.modules.agents.models.inputs import AgentInput
from yuxi.modules.agents.models.messages import Message
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.modules.agents.repositories.cooperation import CooperationRepository
from yuxi.modules.agents.repositories.definitions import DEFAULT_SHARE_CONFIG
from yuxi.modules.agents.repositories.runs import AgentRunRepository
from yuxi.modules.agents.repositories.sessions import SessionRepository
from yuxi.modules.agents.services.cooperation import SessionCooperationService, recover_cooperation_waits
from yuxi.modules.agents.services.runs import settle_checkpoint
from yuxi.modules.agents.scope import ActorScope
from yuxi.modules.identity.models import User
from yuxi.shared.datetime import utc_now
from yuxi.shared.errors import DomainError, StateConflictError

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


@pytest_asyncio.fixture()
async def tree(monkeypatch):
    """每个用例建立独立用户和树，输出与范围均从数据库重新读取。"""
    load_models()
    engine = create_async_engine(os.environ["POSTGRES_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def transaction():
        async with factory() as db:
            async with db.begin():
                yield db

    monkeypatch.setattr(pg_manager, "get_async_session_context", transaction)

    monkeypatch.setattr(
        "yuxi.modules.agents.services.input_config.model_cache.get_model_info",
        lambda spec: SimpleNamespace(model_type="chat"),
    )
    monkeypatch.setattr(
        "yuxi.modules.agents.services.input_config.system_options",
        SimpleNamespace(get=AsyncMock(return_value={"default_model": "test:mock"})),
    )
    monkeypatch.setattr("yuxi.modules.agents.services.cooperation.deliver", AsyncMock())
    monkeypatch.setattr("yuxi.modules.agents.services.scheduler.deliver", AsyncMock())
    run_id, thread_id, _message_id = await create_agent_run(
        factory,
        prefix="cooperation",
        message_content="PRIVATE_ROOT_HISTORY",
        input_payload={
            "context_snapshot": {
                "model": "test:mock",
                "tool_approval_mode": "always_trust",
                "tools": [],
                "system_prompt": "CONFIG",
            },
        },
        status="pending",
    )
    async with transaction() as db:
        root = await db.scalar(select(Session).where(Session.thread_id == thread_id))
        run = await db.get(AgentRun, run_id)
        root.config_snapshot = dict(run.input_payload["context_snapshot"])
        agent_slug = f"cooperation-{thread_id[-12:]}"
        root.agent_id = run.agent_slug = agent_slug
        db.add(
            Agent(
                slug=agent_slug,
                name="统一测试配置",
                backend_id="ChatbotAgent",
                visibility="private",
                created_by=root.uid,
                share_config=DEFAULT_SHARE_CONFIG,
                config_json={"context": {"tools": []}},
            )
        )
        _, acquired = await AgentRunRepository(db).mark_running(run_id, worker_id="root-worker", lease_seconds=120)
        assert acquired
        uid = root.uid
    try:
        yield factory, run_id, thread_id, uid
    finally:
        async with factory() as db:
            thread_ids = list((await db.scalars(select(Session.thread_id).where(Session.uid == uid))).all())
        try:
            await cleanup_agent_run_threads(factory, thread_ids)
            async with factory() as db:
                await db.execute(delete(Agent).where(Agent.slug.like(f"{agent_slug}-%")))
                await db.commit()
        finally:
            await engine.dispose()


async def child(tree, name="reviewer", call_id="create-reviewer"):
    """通过真实输入主链路创建成员。"""
    factory, run_id, _, uid = tree
    async with factory() as db:
        return await SessionCooperationService(db, run_id=run_id, uid=uid).create_session(
            name=name, description=f"EXPLICIT_{name}", call_id=call_id
        )


async def test_creation_is_idempotent_and_context_is_independent(tree):
    factory, _, root_id, _ = tree
    created = await child(tree)
    replay = await child(tree)
    assert created == replay
    async with factory() as db:
        member = await db.scalar(select(Session).where(Session.thread_id == created["session_id"]))
        root = await db.scalar(select(Session).where(Session.thread_id == root_id))
        assert member.tree_root_thread_id == root_id and member.parent_thread_id == root_id
        assert member.project_id == root.project_id and member.agent_id == root.agent_id
        run = await db.get(AgentRun, created["run_id"])
        assert run.run_type == "chat" and run.runtime_scope_id == root_id
        assert run.input_payload["context_snapshot"]["model"] == "test:mock"
        messages = list((await db.scalars(select(Message).where(Message.session_record_id == member.id))).all())
        assert [message.content for message in messages] == ["EXPLICIT_reviewer"]
        assert "PRIVATE_ROOT_HISTORY" not in str(run.input_payload)
        assert await db.scalar(select(func.count()).select_from(AgentInput).where(AgentInput.thread_id == member.thread_id)) == 1
    with pytest.raises(ValueError, match="名称"):
        await child(tree, name="other", call_id="create-reviewer")


async def test_agent_directory_returns_only_callable_role_metadata(tree):
    """目录和直接创建使用同一运行范围，隐藏其他私有及无授权共享角色。"""
    factory, run_id, root_id, uid = tree
    allowed = await _define_target_agent(tree)
    hidden_private = await _define_target_agent(tree, suffix="private", owner="another-user")
    hidden_shared = await _define_target_agent(tree, suffix="shared", visibility="shared", shared_uid="another-user")
    async with factory() as db:
        result = await SessionCooperationService(db, run_id=run_id, uid=uid).list_agents()
        root = await db.scalar(select(Session).where(Session.thread_id == root_id))
        roles = {agent["id"]: agent for agent in result["agents"]}
        assert allowed in roles and root.agent_id in roles
        assert hidden_private not in roles and hidden_shared not in roles
        assert roles[allowed] == {"id": allowed, "name": "独立核验角色", "description": "核验并交付证据"}
        assert all(set(role) == {"id", "name", "description"} for role in roles.values())


async def test_agent_directory_does_not_turn_private_governance_into_run_permission(tree):
    """超级管理员可管理别人的私有配置，但协作目录不能宣称可运行。"""
    factory, run_id, _, uid = tree
    hidden = await _define_target_agent(tree, owner="another-user")
    async with factory() as db:
        user = await db.scalar(select(User).where(User.uid == uid))
        user.role = "superadmin"
        await db.commit()
        result = await SessionCooperationService(db, run_id=run_id, uid=uid).list_agents()
        assert hidden not in {role["id"] for role in result["agents"]}


async def test_agent_directory_uses_app_key_owner_visibility_for_end_user(tree):
    """终端用户读取 Key 所有者授权的共享角色，不能使用所有者私有配置。"""
    factory, run_id, root_id, uid = tree
    owner_uid = f"owner-{uuid.uuid4().hex}"
    shared = await _define_target_agent(tree, suffix="app-shared", visibility="shared", shared_uid=owner_uid)
    private = await _define_target_agent(tree, suffix="app-private", owner=owner_uid)
    try:
        async with factory() as db:
            owner = User(uid=owner_uid, username=owner_uid, password_hash="test", role="admin")
            db.add(owner)
            await db.flush()
            user = await db.scalar(select(User).where(User.uid == uid))
            user.user_kind = "end_user"
            user.owner_user_id = owner.id
            user.app_id = "directory-app"
            user.end_user_id = "customer"
            root = await db.scalar(select(Session).where(Session.thread_id == root_id))
            root.app_id = "directory-app"
            run = await db.get(AgentRun, run_id)
            run.app_id = "directory-app"
            turn = await db.get(AgentTurn, run.turn_id)
            turn.app_id = "directory-app"
            root_agent = await db.scalar(select(Agent).where(Agent.slug == root.agent_id))
            root_agent.visibility = "shared"
            root_agent.share_config = DEFAULT_SHARE_CONFIG
            await db.commit()
            service = SessionCooperationService(db, run_id=run_id, uid=uid)
            result = await service.list_agents()
            assert shared in {role["id"] for role in result["agents"]}
            assert private not in {role["id"] for role in result["agents"]}
            created = await service.create_session(name="app-worker", description="共享核验", call_id="app", agent_id=shared)
        async with factory() as db:
            child = await db.scalar(select(Session).where(Session.thread_id == created["session_id"]))
            assert child.uid == uid and child.app_id == "directory-app"
            assert child.agent_id == shared and child.tree_root_thread_id == root_id
    finally:
        async with factory() as db:
            user = await db.scalar(select(User).where(User.uid == uid))
            user.user_kind = "human"
            user.owner_user_id = user.app_id = user.end_user_id = None
            await db.flush()
            await db.execute(delete(User).where(User.uid == owner_uid))
            await db.commit()


@pytest.mark.parametrize("operation", ["list_agents", "create_session"])
async def test_agent_selection_rejects_deleted_execution_user(tree, operation):
    """失效账号直接调用服务也不能发现或派发 Agent。"""
    factory, run_id, root_id, uid = tree
    async with factory() as db:
        user = await db.scalar(select(User).where(User.uid == uid))
        user.is_deleted = 1
        await db.commit()
        service = SessionCooperationService(db, run_id=run_id, uid=uid)
        with pytest.raises(ValueError, match="账号已失效"):
            if operation == "list_agents":
                await service.list_agents()
            else:
                await service.create_session(name="invalid", description="拒绝", call_id="invalid")
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(Session).where(Session.tree_root_thread_id == root_id)) == 1


async def test_selected_agent_freezes_target_config_model_and_parent_approval(tree):
    """回读持久会话与输入，证明角色配置、模型与审批各自来源。"""
    factory, run_id, root_id, uid = tree
    slug = await _define_target_agent(tree)
    async with factory() as db:
        service = SessionCooperationService(db, run_id=run_id, uid=uid, config_snapshot={"system_prompt": "PARENT_OVERRIDE"})
        created = await service.create_session(name="reviewer", description="独立核验", call_id="choose", agent_id=slug)
        replay = await service.create_session(name="reviewer", description="独立核验", call_id="choose", agent_id=slug)
        assert created == replay
    async with factory() as db:
        member = await db.scalar(select(Session).where(Session.thread_id == created["session_id"]))
        run = await db.get(AgentRun, created["run_id"])
        assert member.agent_id == run.agent_slug == slug
        assert member.parent_thread_id == member.tree_root_thread_id == root_id
        assert member.config_snapshot["system_prompt"] == "TARGET_CONFIG"
        assert member.config_snapshot["tools"] == ["ask_user_question"]
        assert run.input_payload["context_snapshot"] == member.config_snapshot
        assert run.input_payload["context_snapshot"]["model"] == member.config_snapshot["model"] == "test:target"
        assert run.input_payload["context_snapshot"]["tool_approval_mode"] == "always_trust"
        assert await db.scalar(select(func.count()).select_from(AgentInput).where(AgentInput.thread_id == member.thread_id)) == 1


@pytest.mark.parametrize("initial_context", [None, {}])
async def test_empty_selected_config_stays_frozen_when_target_changes(tree, monkeypatch, initial_context):
    """创建后修改目标配置，执行准备仍读取已持久化的空快照。"""
    from types import SimpleNamespace

    from yuxi.modules.agents.services.preparation import prepare_run_execution

    factory, run_id, _, uid = tree
    slug = await _define_target_agent(tree)
    async with factory() as db:
        target = await db.scalar(select(Agent).where(Agent.slug == slug))
        target.config_json = {"context": initial_context}
        await db.commit()
        created = await SessionCooperationService(db, run_id=run_id, uid=uid).create_session(
            name="empty", description="使用空配置", call_id="empty", agent_id=slug
        )
    async with factory() as db:
        target = await db.scalar(select(Agent).where(Agent.slug == slug))
        target.config_json = {"context": {"system_prompt": "CHANGED_AFTER_CREATION"}}
        await db.commit()

    async def prepare(context):
        """隔离工作区和 Skill 解析，保留真实执行配置装配。"""
        context._runtime_prepared = True
        context.skill_runtime_snapshot = {"preloaded_skills": [], "preloaded_skill_contents": {}, "skill_metadata": {}}
        return context

    monkeypatch.setattr("yuxi.modules.agents.services.preparation.prepare_agent_runtime_context", prepare)
    async with factory() as db:
        run = await db.get(AgentRun, created["run_id"])
        member = await db.scalar(select(Session).where(Session.thread_id == created["session_id"]))
        assert member.config_snapshot == run.input_payload["context_snapshot"]
        assert member.config_snapshot["system_prompt"] == "You are a helpful assistant."
        result = await prepare_run_execution(
            run=run,
            user=await db.scalar(select(User).where(User.uid == uid)),
            db=db,
            workdir_binding=SimpleNamespace(workdir_path="projects/fixture"),
            worker_id="snapshot-worker",
        )
        assert result.context.system_prompt == "You are a helpful assistant."
        assert result.context._cooperation_config_snapshot["system_prompt"] == "You are a helpful assistant."


@pytest.mark.parametrize("target_kind", ["missing", "private", "shared"])
async def test_selected_agent_rejects_inaccessible_target_before_persisting(tree, target_kind):
    """直接服务调用不能用已知 slug 绕过目录可见性并产生成员或输入。"""
    factory, run_id, root_id, uid = tree
    slug = "missing-agent"
    if target_kind != "missing":
        slug = await _define_target_agent(tree, visibility=target_kind, owner="another-user", shared_uid="another-user")
    async with factory() as db:
        service = SessionCooperationService(db, run_id=run_id, uid=uid)
        with pytest.raises(ValueError, match="无权限运行"):
            await service.create_session(name="forbidden", description="拒绝", call_id="forbidden", agent_id=slug)
    async with factory() as db:
        members = list((await db.scalars(select(Session).where(Session.tree_root_thread_id == root_id))).all())
        assert [member.thread_id for member in members] == [root_id]
        assert await db.scalar(select(func.count()).select_from(AgentInput).where(AgentInput.thread_id == root_id)) == 1


async def test_creation_replay_cannot_change_selected_agent(tree):
    """相同工具调用不能换 Agent 形成新的会话或重复输入。"""
    factory, run_id, root_id, uid = tree
    first = await _define_target_agent(tree, suffix="first")
    second = await _define_target_agent(tree, suffix="second")
    async with factory() as db:
        service = SessionCooperationService(db, run_id=run_id, uid=uid)
        created = await service.create_session(name="reviewer", description="核验", call_id="same", agent_id=first)
        with pytest.raises(ValueError, match="Agent 已变化"):
            await service.create_session(name="reviewer", description="核验", call_id="same", agent_id=second)
    async with factory() as db:
        members = list((await db.scalars(select(Session).where(Session.tree_root_thread_id == root_id))).all())
        assert len(members) == 2
        member = next(member for member in members if member.thread_id == created["session_id"])
        assert member.agent_id == first
        assert await db.scalar(select(func.count()).select_from(AgentInput).where(AgentInput.thread_id == member.thread_id)) == 1


@pytest.mark.parametrize("name", ["/root/aaa/bbb", "aaa/bbb", "/root/name", "../bbb", r"aaa\bbb", "aaa%2Fbbb"])
async def test_creation_rejects_paths_without_persisting_children(tree, name):
    """直接调用服务也不能用路径名称生成子会话或输入。"""
    factory, _, root_id, _ = tree
    async with factory() as db:
        before_inputs = await db.scalar(select(func.count()).select_from(AgentInput).where(AgentInput.thread_id == root_id))
    with pytest.raises(ValueError, match="name"):
        await child(tree, name=name)
    async with factory() as db:
        members = list((await db.scalars(select(Session).where(Session.tree_root_thread_id == root_id))).all())
        assert [member.thread_id for member in members] == [root_id]
        assert await db.scalar(select(func.count()).select_from(AgentInput).where(AgentInput.thread_id == root_id)) == before_inputs


async def test_creation_derives_direct_parent_and_path_from_calling_session(tree):
    """真实派发 Run 决定父节点，同名兄弟与后代互不混淆。"""
    factory, root_run_id, root_id, uid = tree
    parent = await child(tree, name="aaa", call_id="create-aaa")
    sibling = await child(tree, name="bbb", call_id="create-bbb")
    async with factory() as db:
        _, acquired = await AgentRunRepository(db).mark_running(parent["run_id"], worker_id="aaa-worker", lease_seconds=120)
        assert acquired
        await db.commit()
        nested = await SessionCooperationService(db, run_id=parent["run_id"], uid=uid).create_session(
            name="bbb", description="仅由 aaa 创建的直属工作", call_id="create-bbb"
        )
    async with factory() as db:
        members = list((await db.scalars(select(Session).where(Session.tree_root_thread_id == root_id))).all())
        assert {member.cooperation_path for member in members} == {"/root", "/root/aaa", "/root/bbb", "/root/aaa/bbb"}
        by_id = {member.thread_id: member for member in members}
        assert by_id[parent["session_id"]].parent_thread_id == root_id
        assert by_id[sibling["session_id"]].parent_thread_id == root_id
        assert by_id[sibling["session_id"]].created_by_run_id == root_run_id
        descendant = by_id[nested["session_id"]]
        assert descendant.parent_thread_id == parent["session_id"]
        assert descendant.cooperation_name == "bbb" and descendant.cooperation_path == "/root/aaa/bbb"
        assert descendant.created_by_run_id == parent["run_id"]


async def test_whole_tree_shares_four_slots_and_recursive_creation(tree):
    factory, _, _, uid = tree
    members = [await child(tree, name=f"worker{i}", call_id=f"create{i}") for i in range(4)]

    async def claim(member):
        async with factory() as db:
            async with db.begin():
                return (
                    await AgentRunRepository(db).mark_running(
                        member["run_id"], worker_id=f"worker-{member['session_id']}", lease_seconds=120
                    )
                )[1]

    acquired = await asyncio.gather(*(claim(member) for member in members))
    assert sum(acquired) == 3
    running = members[acquired.index(True)]
    async with factory() as db:
        grandchild = await SessionCooperationService(db, run_id=running["run_id"], uid=uid).create_session(
            name="nested", description="EXPLICIT_NESTED", call_id="nested"
        )
    assert grandchild["path"].endswith("/nested")
    assert not await claim(grandchild)
    async with factory() as db:
        assert (
            await db.scalar(
                select(func.count()).select_from(AgentRun).where(AgentRun.runtime_scope_id == tree[2], AgentRun.status == "running")
            )
            == 4
        )


async def test_message_is_durable_idempotent_and_does_not_create_work(tree):
    factory, run_id, _, uid = tree
    created = await child(tree)
    async with factory() as db:
        service = SessionCooperationService(db, run_id=run_id, uid=uid)
        first = await service.send_message(target=created["session_id"], content="information", call_id="message")
        await db.commit()
        replay = await service.send_message(target=created["path"], content="information", call_id="message")
        assert first == replay
        await db.commit()
    async with factory() as db:
        assert (
            await db.scalar(
                select(func.count()).select_from(CooperationEvent).where(CooperationEvent.recipient_thread_id == created["session_id"])
            )
            == 1
        )
        assert await db.scalar(select(func.count()).select_from(AgentInput).where(AgentInput.thread_id == created["session_id"])) == 1


async def test_cross_tree_and_cross_app_targets_are_rejected(tree):
    factory, run_id, root_id, uid = tree
    async with factory() as db:
        root = await db.scalar(select(Session).where(Session.thread_id == root_id))
        stranger = Session(thread_id=f"{root_id}-x", uid=uid, project_id=root.project_id, agent_id=root.agent_id, status="active")
        other_app = Session(
            thread_id=f"{root_id}-a",
            tree_root_thread_id=root_id,
            parent_thread_id=root_id,
            cooperation_path="/root/other-app",
            cooperation_name="other-app",
            uid=uid,
            app_id="another-app",
            project_id=root.project_id,
            agent_id=root.agent_id,
            status="active",
        )
        db.add_all([stranger, other_app])
        await db.commit()
        service = SessionCooperationService(db, run_id=run_id, uid=uid)
        for target in [stranger.thread_id, other_app.thread_id]:
            with pytest.raises(ValueError, match="授权树"):
                await service.send_message(target=target, content="forbidden", call_id=target)
        assert (
            await db.scalar(
                select(func.count())
                .select_from(CooperationEvent)
                .where(CooperationEvent.recipient_thread_id.in_([stranger.thread_id, other_app.thread_id]))
            )
            == 0
        )


async def test_busy_input_queues_but_human_wait_rejects(tree):
    factory, run_id, _, uid = tree
    member = await child(tree)
    async with factory() as db:
        service = SessionCooperationService(db, run_id=run_id, uid=uid)
        queued = await service.submit_input(target=member["session_id"], description="next", call_id="next")
        assert queued["status"] == "queued" and queued["turn_id"] is None
        turn = await db.get(AgentTurn, member["turn_id"])
        turn.status = "waiting"
        turn.waitpoint = {"kind": "approval", "run_id": member["run_id"]}
        await db.commit()
        with pytest.raises(DomainError) as error:
            await service.submit_input(target=member["session_id"], description="bypass", call_id="bypass")
        assert isinstance(error.value, StateConflictError)


async def test_cooperation_wait_releases_slot_and_recovers_same_turn(tree):
    factory, run_id, root_id, uid = tree
    member = await child(tree)
    async with factory() as db:
        service = SessionCooperationService(db, run_id=run_id, uid=uid)
        wait = await service.wait_updates(targets=[member["session_id"]], after_cursor=0, timeout_seconds=300)
        assert wait["kind"] == "cooperation"
        run = await db.get(AgentRun, run_id)
        await settle_checkpoint(
            db=db,
            run=run,
            worker_id="root-worker",
            status="interrupted",
            token_usage=None,
            waitpoint={**wait, "id": "wait-root", "run_id": run_id},
        )
        await db.commit()
        _, acquired = await AgentRunRepository(db).mark_running(member["run_id"], worker_id="child-worker", lease_seconds=120)
        assert acquired
        await db.commit()
        sender = await db.scalar(select(Session).where(Session.thread_id == member["session_id"]))
        recipient = await db.scalar(select(Session).where(Session.thread_id == root_id))
        await CooperationRepository(db).append(sender=sender, recipient=recipient, key="wake", kind="message", content="ready")
        await db.commit()
    await recover_cooperation_waits()
    await recover_cooperation_waits()
    async with factory() as db:
        old = await db.get(AgentRun, run_id)
        turn = await db.get(AgentTurn, old.turn_id)
        resumed = await db.get(AgentRun, turn.current_run_id)
        assert old.status == "interrupted" and old.worker_id is None
        assert resumed.id != old.id and resumed.run_type == "resume"
        assert resumed.turn_id == old.turn_id and resumed.resume_from_run_id == old.id
        assert resumed.runtime_scope_id == root_id and turn.status == "running"
        assert await db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.turn_id == old.turn_id)) == 2


async def test_tool_side_effects_replay_across_resume_runs(tree):
    """同 Turn 的恢复 Run 不重复副作用，冲突重放仍拒绝且保留首次来源。"""
    factory, run_id, root_id, uid = tree
    member = await child(tree)
    async with factory() as db:
        service = SessionCooperationService(db, run_id=run_id, uid=uid)
        message = await service.send_message(target=member["session_id"], content="information", call_id="message")
        await db.commit()
        submitted = await service.submit_input(target=member["session_id"], description="FOLLOWUP", call_id="followup")
        wait = await service.wait_updates(targets=[member["session_id"]], after_cursor=0, timeout_seconds=300)
        await settle_checkpoint(
            db=db,
            run=await db.get(AgentRun, run_id),
            worker_id="root-worker",
            status="interrupted",
            token_usage=None,
            waitpoint={**wait, "id": "replay-wait", "run_id": run_id},
        )
        await db.commit()
        await CooperationRepository(db).append(
            sender=await db.scalar(select(Session).where(Session.thread_id == member["session_id"])),
            recipient=await db.scalar(select(Session).where(Session.thread_id == root_id)),
            key="replay-wake",
            kind="message",
            content="ready",
        )
        await db.commit()
    await recover_cooperation_waits()
    async with factory() as db:
        old = await db.get(AgentRun, run_id)
        turn = await db.get(AgentTurn, old.turn_id)
        resumed_id = turn.current_run_id
        assert resumed_id != run_id
        _, acquired = await AgentRunRepository(db).mark_running(resumed_id, worker_id="resume-worker", lease_seconds=120)
        assert acquired
        await db.commit()
        service = SessionCooperationService(db, run_id=resumed_id, uid=uid)
        assert await service.create_session(name="reviewer", description="EXPLICIT_reviewer", call_id="create-reviewer") == member
        assert await service.send_message(target=member["session_id"], content="information", call_id="message") == message
        await db.commit()
        assert await service.submit_input(target=member["session_id"], description="FOLLOWUP", call_id="followup") == submitted
        for operation, match in (
            (
                lambda: service.create_session(name="changed", description="EXPLICIT_reviewer", call_id="create-reviewer"),
                "名称",
            ),
            (
                lambda: service.submit_input(target=member["session_id"], description="CHANGED", call_id="followup"),
                "Idempotency-Key",
            ),
            (lambda: service.send_message(target=member["session_id"], content="CHANGED", call_id="message"), "幂等"),
        ):
            with pytest.raises((ValueError, DomainError), match=match):
                await operation()
            await db.rollback()
    async with factory() as db:
        created = await db.scalar(select(Session).where(Session.thread_id == member["session_id"]))
        assert created.created_by_run_id == run_id
        event = await db.get(CooperationEvent, message["message_id"])
        assert event.source_run_id == run_id
        assert await db.scalar(select(func.count()).select_from(AgentInput).where(AgentInput.thread_id == created.thread_id)) == 2
        assert (
            await db.scalar(
                select(func.count()).select_from(CooperationEvent).where(CooperationEvent.recipient_thread_id == created.thread_id)
            )
            == 1
        )


async def test_same_call_id_in_new_turn_creates_new_work(tree):
    """幂等只跨同 Turn 恢复，新轮次可以复用模型工具调用 ID。"""
    from yuxi.modules.agents.repositories.turn import AgentTurnRepository

    factory, run_id, root_id, uid = tree
    member = await child(tree)
    async with factory() as db:
        service = SessionCooperationService(db, run_id=run_id, uid=uid)
        first = await service.submit_input(target=member["session_id"], description="FOLLOWUP", call_id="same-call")
        old = await db.get(AgentRun, run_id)
        _, changed = await AgentRunRepository(db).set_terminal_status(run_id, status="failed", worker_id="root-worker")
        assert changed
        await AgentTurnRepository(db).set_terminal(await db.get(AgentTurn, old.turn_id), status="failed")
        await db.flush()
        turn = AgentTurn(id=str(uuid.uuid4()), thread_id=root_id, uid=uid, app_id=None, status="running")
        db.add(turn)
        await db.flush()
        new_run = await AgentRunRepository(db).create_run(
            run_id=str(uuid.uuid4()),
            thread_id=root_id,
            agent_slug=old.agent_slug,
            uid=uid,
            turn_id=turn.id,
            input_payload=old.input_payload,
            session_record_id=old.session_record_id,
        )
        turn.current_run_id = new_run.id
        _, acquired = await AgentRunRepository(db).mark_running(new_run.id, worker_id="new-turn-worker", lease_seconds=120)
        assert acquired
        await db.commit()
        second = await SessionCooperationService(db, run_id=new_run.id, uid=uid).submit_input(
            target=member["session_id"], description="FOLLOWUP", call_id="same-call"
        )
        assert second["input_id"] != first["input_id"]
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(AgentInput).where(AgentInput.thread_id == member["session_id"])) == 3


async def test_cancel_parent_preserves_descendants(tree, monkeypatch):
    """取消父轮次只取消指定 Run，后代的独立队列继续保留。"""
    from yuxi.modules.agents.scope import ActorScope
    from yuxi.modules.agents.services.turns import cancel_turn

    monkeypatch.setattr("yuxi.modules.agents.services.turns.publish_cancel_signals", AsyncMock())
    factory, run_id, root_id, uid = tree
    member = await child(tree)
    async with factory() as db:
        root_run = await db.get(AgentRun, run_id)
        await cancel_turn(
            db=db,
            scope=ActorScope(uid=uid, app_id=None),
            thread_id=root_id,
            turn_id=root_run.turn_id,
            idempotency_key="cancel-root",
        )
    async with factory() as db:
        assert (await db.get(AgentRun, run_id)).status == "cancel_requested"
        assert (await db.get(AgentRun, member["run_id"])).status == "pending"
        assert (await db.get(AgentTurn, member["turn_id"])).status == "running"
        root = await db.scalar(select(Session).where(Session.thread_id == root_id))
        descendant = await db.scalar(select(Session).where(Session.thread_id == member["session_id"]))
        assert root.queue_paused and not descendant.queue_paused


async def test_old_stop_scan_cannot_repause_continued_tree(tree, monkeypatch):
    """让旧停止扫描晚于继续事务取得成员锁，验证不会重新暂停队列。"""
    from yuxi.modules.agents.models.cooperation import CooperationRuntime
    from yuxi.modules.agents.repositories.sessions import SessionRepository
    from yuxi.modules.agents.services.cooperation import control_tree, reconcile_stopped_trees
    from yuxi.modules.agents.scope import ActorScope

    factory, run_id, root_id, uid = tree
    async with factory() as db:
        run = await db.get(AgentRun, run_id)
        run.status = "completed"
        run.worker_id = None
        turn = await db.get(AgentTurn, run.turn_id)
        turn.status = "completed"
        turn.result_run_id = run.id
        runtime = await db.get(CooperationRuntime, root_id)
        runtime.stopped = True
        root = await db.scalar(select(Session).where(Session.thread_id == root_id))
        root.queue_paused = True
        await db.commit()
    scanned, continue_committed = asyncio.Event(), asyncio.Event()
    original_lock = SessionRepository.lock_session_by_thread_id

    async def delayed_lock(repo, thread_id):
        scanned.set()
        await continue_committed.wait()
        return await original_lock(repo, thread_id)

    monkeypatch.setattr(SessionRepository, "lock_session_by_thread_id", delayed_lock)
    monkeypatch.setattr("yuxi.modules.agents.services.scheduler.dispatch_next_input", AsyncMock())
    old_stop = asyncio.create_task(reconcile_stopped_trees())
    await asyncio.wait_for(scanned.wait(), 5)
    try:
        async with factory() as db:
            await control_tree(
                db=db,
                scope=ActorScope(uid=uid, app_id=None),
                thread_id=root_id,
                idempotency_key="continue-tree",
                stopped=False,
            )
    finally:
        continue_committed.set()
    # 扫描同时处理槽位中已有的停止树，截止时间覆盖整批事务而非单个成员。
    await asyncio.wait_for(old_stop, 30)
    async with factory() as db:
        assert not (await db.get(CooperationRuntime, root_id)).stopped
        assert not (await db.scalar(select(Session).where(Session.thread_id == root_id))).queue_paused


async def test_lost_worker_publishes_failure_to_waiting_member(tree, monkeypatch):
    """失联子 Run 的终态必须进入持久 mailbox，使协作等待可恢复。"""
    from datetime import timedelta

    from yuxi.modules.agents.services.leases import reconcile_expired_run_leases

    factory, run_id, root_id, uid = tree
    member = await child(tree)
    monkeypatch.setattr("yuxi.modules.agents.services.leases.reconcile_pending_runtime_cleanups", AsyncMock())
    async with factory() as db:
        _, acquired = await AgentRunRepository(db).mark_running(member["run_id"], worker_id="lost-worker", lease_seconds=120)
        assert acquired
        run = await db.get(AgentRun, member["run_id"])
        run.lease_expires_at = utc_now() - timedelta(seconds=1)
        await db.commit()
    assert member["run_id"] in await reconcile_expired_run_leases()
    async with factory() as db:
        updates = await SessionCooperationService(db, run_id=run_id, uid=uid).wait_updates(
            targets=[member["session_id"]], after_cursor=0, timeout_seconds=300
        )
        assert any(update.get("status") == "failed" for update in updates["updates"]), updates
        assert (await db.get(AgentTurn, member["turn_id"])).status == "failed"


async def test_idle_reaper_preserves_active_tree(tree, monkeypatch):
    """恢复过期空闲标记时，真实活跃 Run 仍阻止释放共享环境。"""
    from datetime import timedelta

    from yuxi.modules.agents.models.cooperation import CooperationRuntime
    from yuxi.modules.agents.services.leases import release_idle_sandboxes

    factory, _, root_id, _ = tree
    async with factory() as db:
        runtime = await db.get(CooperationRuntime, root_id)
        runtime.idle_since = utc_now() - timedelta(minutes=6)
        await db.commit()

    from types import SimpleNamespace

    def release_other_tree(candidate, **kwargs):
        assert candidate != root_id, "活跃树不应调用沙盒释放器"

    monkeypatch.setattr("yuxi.modules.agents.services.leases.get_sandbox_provider", lambda: SimpleNamespace(release=release_other_tree))
    await release_idle_sandboxes()
    async with factory() as db:
        assert not (await db.get(CooperationRuntime, root_id)).released


async def test_durable_tree_and_run_binding_reject_wrong_owner(tree):
    """绕过服务直接写入错误树归属和 runtime，数据库必须拒绝。"""
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    factory, run_id, root_id, _ = tree
    member = await child(tree)
    async with factory() as db:
        with pytest.raises(IntegrityError, match="fk_agent_runs_session_runtime_scope"):
            async with db.begin_nested():
                await db.execute(
                    text("UPDATE agent_runs SET runtime_scope_id=:child WHERE id=:run"),
                    {"child": member["session_id"], "run": run_id},
                )
        with pytest.raises(IntegrityError, match="fk_sessions_tree_owner|fk_sessions_project_uid"):
            async with db.begin_nested():
                await db.execute(
                    text("UPDATE sessions SET uid='other-owner' WHERE thread_id=:thread"),
                    {"thread": member["session_id"]},
                )
        root = await db.scalar(select(Session).where(Session.thread_id == root_id))
        assert root.thread_id == root.tree_root_thread_id


async def test_wait_rejects_empty_and_self_targets(tree):
    """自身 waiting 通知不能制造无工作自唤醒循环。"""
    factory, run_id, root_id, uid = tree
    async with factory() as db:
        service = SessionCooperationService(db, run_id=run_id, uid=uid)
        for targets in [[], [root_id], ["/root"]]:
            with pytest.raises(ValueError, match="目标不能为空|自身"):
                await service.wait_updates(targets=targets, after_cursor=0, timeout_seconds=1)
        assert (
            await db.scalar(select(func.count()).select_from(CooperationEvent).where(CooperationEvent.tree_root_thread_id == root_id)) == 0
        )


async def test_stopped_member_at_model_boundary_requests_cancellation(tree, monkeypatch):
    """停止意图与逐成员取消之间的执行边界不能落为普通失败。"""
    from yuxi.modules.agents.models.cooperation import CooperationRuntime

    factory, run_id, root_id, uid = tree
    monkeypatch.setattr("yuxi.modules.agents.services.turns.publish_cancel_signals", AsyncMock())
    async with factory() as db:
        (await db.get(CooperationRuntime, root_id)).stopped = True
        await db.commit()
        with pytest.raises(asyncio.CancelledError, match="协作树已停止"):
            await SessionCooperationService(db, run_id=run_id, uid=uid).list_sessions()
    async with factory() as db:
        run = await db.get(AgentRun, run_id)
        turn = await db.get(AgentTurn, run.turn_id)
        member = await db.scalar(select(Session).where(Session.thread_id == root_id))
        assert run.status == "cancel_requested" and run.worker_id == "root-worker"
        assert turn.status == "cancelling" and member.queue_paused


async def test_tree_stop_cancels_released_retry_without_lease_failure(tree, monkeypatch):
    """合法释放的重试 Run 应按取消收敛，并且继续队列不能复活它。"""
    from yuxi.modules.agents.services.cooperation import control_tree
    from yuxi.modules.agents.services.leases import reconcile_pending_runtime_cleanups
    from yuxi.modules.agents.services.scheduler import Dispatch

    monkeypatch.setattr("yuxi.modules.agents.services.turns.publish_cancel_signals", AsyncMock())
    delivery = AsyncMock()
    monkeypatch.setattr("yuxi.modules.agents.services.scheduler.deliver", delivery)
    factory, run_id, root_id, uid = tree
    async with factory() as db:
        queued = await SessionCooperationService(db, run_id=run_id, uid=uid).submit_input(
            target=root_id, description="queued after retry", call_id="queue-before-retry"
        )
        old_turn_id = (await db.get(AgentRun, run_id)).turn_id
        assert queued["status"] == "queued"
        assert await AgentRunRepository(db).release_lease_for_retry(run_id, worker_id="root-worker")
        await db.commit()
    async with factory() as db:
        await control_tree(
            db=db,
            scope=ActorScope(uid=uid, app_id=None),
            thread_id=root_id,
            idempotency_key="stop-released-retry",
            stopped=True,
        )
    await reconcile_pending_runtime_cleanups()
    async with factory() as db:
        cancelled = await db.get(AgentRun, run_id)
        assert cancelled.status == "cancelled"
        assert cancelled.error_type == "cancelled"
        assert cancelled.worker_id is None and cancelled.lease_expires_at is None
        assert not cancelled.runtime_cleanup_pending
        assert (await db.get(AgentTurn, old_turn_id)).status == "cancelled"
        assert (await db.get(AgentInput, queued["input_id"])).status == "pending"
        await control_tree(
            db=db,
            scope=ActorScope(uid=uid, app_id=None),
            thread_id=root_id,
            idempotency_key="continue-released-retry",
            stopped=False,
        )
    async with factory() as db:
        assert (await db.get(AgentRun, run_id)).status == "cancelled"
        assert (await db.get(AgentTurn, old_turn_id)).status == "cancelled"
        following = await db.get(AgentInput, queued["input_id"])
        assert following.status == "consumed"
        await db.refresh(following)
        next_run = await db.get(AgentRun, following.consumed_run_id)
        assert next_run is not None and next_run.turn_id != old_turn_id
        delivery.assert_awaited_once()
        assert isinstance(delivery.await_args.args[0], Dispatch)


@pytest.mark.parametrize("operation", ["message", "input", "cancel"])
async def test_resume_call_cannot_change_target_session(tree, monkeypatch, operation):
    """恢复 Run 重放同一工具调用时，换目标不能产生第二份消息、输入或取消。"""
    from datetime import timedelta

    from yuxi.shared.datetime import format_utc_datetime

    monkeypatch.setattr("yuxi.modules.agents.services.turns.publish_cancel_signals", AsyncMock())
    factory, run_id, root_id, uid = tree
    first = await child(tree)
    second = await child(tree, name="second", call_id="create-second")

    async def invoke(service, target):
        """各操作使用同一来源调用身份及相同正文。"""
        if operation == "message":
            return await service.send_message(target=target["session_id"], content="same", call_id="replayed-call")
        if operation == "input":
            return await service.submit_input(target=target["session_id"], description="same", call_id="replayed-call")
        return await service.cancel_turn(target=target["session_id"], turn_id=target["turn_id"], call_id="replayed-call")

    async with factory() as db:
        service = SessionCooperationService(db, run_id=run_id, uid=uid)
        original = await invoke(service, first)
        await db.commit()
        await settle_checkpoint(
            db=db,
            run=await db.get(AgentRun, run_id),
            worker_id="root-worker",
            status="interrupted",
            token_usage=None,
            waitpoint={
                "id": "replay-target-wait",
                "run_id": run_id,
                "kind": "cooperation",
                "target_sessions": [first["session_id"]],
                "after_cursor": 0,
                "deadline": format_utc_datetime(utc_now() - timedelta(seconds=1)),
            },
        )
        old_turn_id = (await db.get(AgentRun, run_id)).turn_id
        await db.commit()
    await recover_cooperation_waits()
    async with factory() as db:
        turn = await db.get(AgentTurn, old_turn_id)
        assert turn.current_run_id != run_id
        resumed_id = turn.current_run_id
        _, acquired = await AgentRunRepository(db).mark_running(resumed_id, worker_id="resume-worker", lease_seconds=120)
        assert acquired
        await db.commit()
        service = SessionCooperationService(db, run_id=resumed_id, uid=uid)
        assert await invoke(service, first) == original
        await db.commit()
        inputs_before = await db.scalar(select(func.count()).select_from(AgentInput).where(AgentInput.uid == uid))
        events_before = await db.scalar(
            select(func.count()).select_from(CooperationEvent).where(CooperationEvent.tree_root_thread_id == root_id)
        )
        with pytest.raises(ValueError, match="目标|幂等"):
            await invoke(service, second)
        await db.rollback()
        assert await db.scalar(select(func.count()).select_from(AgentInput).where(AgentInput.uid == uid)) == inputs_before
        assert (
            await db.scalar(select(func.count()).select_from(CooperationEvent).where(CooperationEvent.tree_root_thread_id == root_id))
            == events_before
        )
        assert (await db.get(AgentTurn, second["turn_id"])).status == "running"
        assert (await db.get(AgentRun, second["run_id"])).status == "pending"


async def test_child_status_notification_preserves_self_and_parent_recipients(tree):
    """同一次子轮次状态分别进入自身和父收件箱，重复通知仍各只有一条。"""
    from yuxi.modules.agents.services.cooperation_notifications import notify_turn_state

    factory, _, root_id, _ = tree
    member = await child(tree)
    async with factory() as db:
        run = await db.get(AgentRun, member["run_id"])
        turn = await db.get(AgentTurn, member["turn_id"])
        turn.status = "waiting"
        turn.waitpoint = {"kind": "approval"}
        await db.flush()
        await notify_turn_state(db, run)
        await notify_turn_state(db, run)
        await db.commit()
    async with factory() as db:
        events = list(
            (
                await db.scalars(
                    select(CooperationEvent).where(
                        CooperationEvent.source_run_id == member["run_id"], CooperationEvent.kind == "turn_status"
                    )
                )
            ).all()
        )
        assert len(events) == 2
        assert {event.recipient_thread_id for event in events} == {root_id, member["session_id"]}
        assert all(event.payload["waiting_for"] == "approval" and event.turn_id == member["turn_id"] for event in events)


async def test_cancelling_last_pending_run_starts_tree_idle_timeout(tree, monkeypatch):
    """最后一个 pending Run 取消后，已使用的共享沙盒仍进入空闲回收。"""
    from datetime import timedelta
    from types import SimpleNamespace

    from yuxi.modules.agents.models.cooperation import CooperationRuntime
    from yuxi.modules.agents.services.leases import release_idle_sandboxes, release_runtime_if_idle
    from yuxi.modules.agents.services.turns import cancel_turn

    factory, run_id, root_id, uid = tree
    member = await child(tree)
    async with factory() as db:
        root_run = await db.get(AgentRun, run_id)
        await settle_checkpoint(
            db=db,
            run=root_run,
            worker_id="root-worker",
            status="failed",
            token_usage=None,
        )
        await db.commit()
    await release_runtime_if_idle(root_run)
    async with factory() as db:
        assert (await db.get(CooperationRuntime, root_id)).idle_since is None
        await cancel_turn(
            db=db,
            scope=ActorScope(uid=uid, app_id=None),
            thread_id=member["session_id"],
            turn_id=member["turn_id"],
            idempotency_key="cancel-last-pending",
        )
    released = []
    monkeypatch.setattr(
        "yuxi.modules.agents.services.leases.get_sandbox_provider",
        lambda: SimpleNamespace(release=lambda scope, **kwargs: released.append(scope)),
    )
    await release_idle_sandboxes()
    async with factory() as db:
        runtime = await db.get(CooperationRuntime, root_id)
        assert runtime.idle_since is not None, "最后一个 pending Run 取消后必须登记树空闲"
        assert root_id not in released
        runtime.idle_since = utc_now() - timedelta(minutes=6)
        await db.commit()
    await release_idle_sandboxes()
    async with factory() as db:
        assert (await db.get(CooperationRuntime, root_id)).released
        assert root_id in released


async def complete_member(factory, member, content):
    """持久化精确输出，供跨轮任务观察断言使用。"""
    from yuxi.modules.agents.repositories.turn import AgentTurnRepository

    async with factory() as db:
        repo = AgentRunRepository(db)
        run, acquired = await repo.mark_running(member["run_id"], worker_id="result-worker", lease_seconds=120)
        assert acquired
        output = Message(
            session_record_id=run.session_record_id,
            role="assistant",
            content=content,
            message_type="text",
            turn_id=run.turn_id,
            run_id=run.id,
        )
        db.add(output)
        await db.flush()
        run.output_message_id = output.id
        await repo.set_terminal_status(run.id, status="completed", worker_id="result-worker")
        await AgentTurnRepository(db).set_terminal(await db.get(AgentTurn, run.turn_id), status="completed", result_run_id=run.id)
        await db.commit()


async def test_exact_result_survives_next_turn_and_queued_input_keeps_identity(tree):
    """A 完成且 B 已派发时，按 A 身份仍能读取 A 的输出。"""
    from yuxi.modules.agents.services.scheduler import claim_next_input

    factory, run_id, _, uid = tree
    member = await child(tree)
    async with factory() as db:
        queued = await SessionCooperationService(db, run_id=run_id, uid=uid).submit_input(
            target=member["session_id"], description="B", call_id="submit-B"
        )
        assert queued["turn_id"] is None
    await complete_member(factory, member, "EXACT_A")
    async with factory() as db:
        session = await SessionRepository(db).lock_session_by_thread_id(member["session_id"])
        dispatch = await claim_next_input(db=db, agent_session=session)
        await db.commit()
        assert dispatch is not None
    async with factory() as db:
        service = SessionCooperationService(db, run_id=run_id, uid=uid)
        a = await service.get_result(input_id=member["input_id"])
        assert a == await service.get_result(turn_id=member["turn_id"])
        assert a["output"] == "EXACT_A" and a["terminal"] and a["result_run_id"] == member["run_id"]
        b = await service.get_result(input_id=queued["input_id"])
        assert b["turn_id"] != a["turn_id"] and not b["terminal"] and b["output"] is None
        wait = await service.wait_inputs(input_ids=[member["input_id"]], timeout_seconds=30)
        assert wait["results"] == [a] and not wait["wait_timed_out"]


async def test_input_wait_recovers_after_queued_input_cancelled(tree):
    """无 Turn 的排队 Input 取消后也能唤醒原有持久等待。"""
    from yuxi.modules.agents.services import execution

    factory, run_id, _, uid = tree
    member = await child(tree)
    async with factory() as db:
        service = SessionCooperationService(db, run_id=run_id, uid=uid)
        queued = await service.submit_input(target=member["session_id"], description="queued", call_id="queued")
        wait = await service.wait_inputs(input_ids=[queued["input_id"]], timeout_seconds=300)
        run = await db.get(AgentRun, run_id)
        turn_id = run.turn_id
        await settle_checkpoint(
            db=db,
            run=run,
            worker_id="root-worker",
            status="interrupted",
            token_usage=None,
            waitpoint=execution._waitpoint_from_interrupt({"status": "cooperation_waiting", **wait}, run_id),
        )
        await db.commit()
    await recover_cooperation_waits()
    async with factory() as db:
        assert (await db.get(AgentTurn, turn_id)).current_run_id == run_id
        queued_input = await db.get(AgentInput, queued["input_id"])
        queued_input.status = "cancelled"
        queued_input.cancelled_at = utc_now()
        await db.commit()
    await recover_cooperation_waits()
    async with factory() as db:
        resumed = await db.get(AgentRun, (await db.get(AgentTurn, turn_id)).current_run_id)
        assert resumed.id != run_id and resumed.resume_from_run_id == run_id
        message = await db.get(Message, resumed.input_message_id)
        result = message.extra_metadata["resume"]["results"][0]
        assert result["input_id"] == queued["input_id"] and result["terminal"]
        assert result["status"] == "cancelled" and result["turn_id"] is None


async def test_task_lookup_and_wait_reject_unknown_scope_and_self(tree):
    """模型不能通过任务 ID 绕过树边界或等待自身。"""
    factory, run_id, _, uid = tree
    member = await child(tree)
    async with factory() as db:
        service = SessionCooperationService(db, run_id=run_id, uid=uid)
        for arguments in ({}, {"input_id": member["input_id"], "turn_id": member["turn_id"]}):
            with pytest.raises(ValueError, match="只能"):
                await service.get_result(**arguments)
        with pytest.raises(ValueError, match="授权树"):
            await service.wait_inputs(input_ids=[member["input_id"], "missing"], timeout_seconds=30)
        _, acquired = await AgentRunRepository(db).mark_running(member["run_id"], worker_id="self", lease_seconds=120)
        assert acquired
        with pytest.raises(ValueError, match="自身"):
            await SessionCooperationService(db, run_id=member["run_id"], uid=uid).wait_inputs(
                input_ids=[member["input_id"]], timeout_seconds=30
            )
        target = await db.scalar(select(Session).where(Session.thread_id == member["session_id"]))
        target.app_id = "another-app"
        await db.flush()
        with pytest.raises(ValueError, match="授权树"):
            await service.get_result(input_id=member["input_id"])
        await db.rollback()


async def test_summary_reads_whole_tree_with_constant_queries_and_omits_results(tree):
    """超过原分页上限的成员一次完整返回，批量查询不包含正文。"""
    from sqlalchemy import event

    from yuxi.modules.agents.services.cooperation import tree_snapshot

    factory, _, root_id, _ = tree
    members = [await child(tree, name=f"summary{i}", call_id=f"summary{i}") for i in range(6)]
    await complete_member(factory, members[0], "PRIVATE_LONG_RESULT")
    async with factory() as db:
        root = await db.scalar(select(Session).where(Session.thread_id == root_id))
        queries = []

        def record(_conn, _cursor, statement, _parameters, _context, _many):
            """记录真实 SQL 往返，独立于 repository 实现。"""
            queries.append(statement)

        engine = factory.kw["bind"].sync_engine
        event.listen(engine, "before_cursor_execute", record)
        try:
            first = await tree_snapshot(db, root)
            assert len(first["sessions"]) == 7 and len(queries) == 4
            db.add_all(
                Session(
                    thread_id=str(uuid.uuid4()),
                    tree_root_thread_id=root_id,
                    parent_thread_id=root_id,
                    uid=root.uid,
                    app_id=root.app_id,
                    project_id=root.project_id,
                    agent_id=root.agent_id,
                    cooperation_name=f"extra{i}",
                    cooperation_path=f"/root/extra{i}",
                )
                for i in range(100)
            )
            await db.commit()
            expected = list(
                (
                    await db.scalars(
                        select(Session.thread_id).where(Session.tree_root_thread_id == root_id).order_by(Session.cooperation_path)
                    )
                ).all()
            )
            queries.clear()
            whole = await tree_snapshot(db, root)
            assert len(queries) == 4
            ids = [item["session_id"] for item in whole["sessions"]]
            assert ids == expected
            assert len(ids) == len(set(ids)) == 107
            assert "next_cursor" not in whole
            assert all("output" not in item for item in whole["sessions"])
        finally:
            event.remove(engine, "before_cursor_execute", record)


@pytest.mark.parametrize("lock_owner", ["dispatch", "configuration", "continue", "run_owner", "run_terminal", "turn"])
async def test_message_foreign_keys_do_not_deadlock_session_writers(tree, monkeypatch, lock_owner):
    """树通知与会话写入并发时，外键键共享锁不得形成反向等待。"""
    from sqlalchemy import text

    from yuxi.modules.agents.repositories.turn import AgentTurnRepository
    from yuxi.modules.agents.services.cooperation import control_tree

    factory, run_id, root_id, uid = tree
    async with factory() as db:
        run = await db.get(AgentRun, run_id)
        await AgentRunRepository(db).set_terminal_status(run_id, status="failed", worker_id="root-worker")
        await AgentTurnRepository(db).set_terminal(await db.get(AgentTurn, run.turn_id), status="failed")
        await db.commit()
    monkeypatch.setattr("yuxi.modules.agents.services.scheduler.dispatch_next_input", AsyncMock())
    locked = asyncio.Event()
    tree_lock = text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))")
    key = {"key": f"cooperation:{root_id}"}

    async def writer():
        """在真实行锁已领取后申请树锁，固定竞争顺序。"""
        async with factory() as db:
            repo = SessionRepository(db)
            if lock_owner == "continue":
                original = db.scalars

                async def scalars(statement, *args, **kwargs):
                    """只观察整树控制实际完成的行锁查询。"""
                    result = await original(statement, *args, **kwargs)
                    if statement._for_update_arg is not None:
                        locked.set()
                    return result

                monkeypatch.setattr(db, "scalars", scalars)
                await control_tree(
                    db=db,
                    scope=ActorScope(uid=uid, app_id=None),
                    thread_id=root_id,
                    idempotency_key=str(uuid.uuid4()),
                    stopped=False,
                )
            else:
                if lock_owner == "dispatch":
                    await repo.lock_session_by_thread_id(root_id)
                elif lock_owner == "configuration":
                    root = await repo.lock_session_by_thread_id(root_id)
                    root.config_snapshot = {**root.config_snapshot, "system_prompt": "UPDATED"}
                    await db.flush()
                elif lock_owner == "run_owner":
                    await AgentRunRepository(db).lock_run_for_user(run_id, uid)
                elif lock_owner == "run_terminal":
                    await AgentRunRepository(db)._lock_run(run_id)
                else:
                    run = await db.get(AgentRun, run_id)
                    await AgentTurnRepository(db).get_for_scope(
                        turn_id=run.turn_id, thread_id=root_id, uid=uid, app_id=None, for_update=True
                    )
                locked.set()
                await db.execute(tree_lock, key)
                await db.commit()

    async with factory() as db:
        root = await db.scalar(select(Session).where(Session.thread_id == root_id))
        await db.execute(tree_lock, key)
        task = asyncio.create_task(writer())
        try:
            await asyncio.wait_for(locked.wait(), 3)
            await CooperationRepository(db).append(
                sender=root,
                recipient=root,
                key=f"lock-{lock_owner}",
                kind="message",
                content="available",
                run_id=run_id,
                turn_id=run.turn_id,
            )
            await db.commit()
            await asyncio.wait_for(task, 3)
        finally:
            await db.rollback()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    async with factory() as db:
        assert await db.scalar(select(CooperationEvent.id).where(CooperationEvent.idempotency_key == f"lock-{lock_owner}"))


async def test_bad_wait_does_not_block_other_wait_recovery(tree):
    """首个等待点损坏时，后续等待仍提交下一 Run，整轮仍报告失败。"""
    factory, root_run_id, _, _ = tree
    member = await child(tree)
    async with factory() as db:
        await AgentRunRepository(db).mark_running(member["run_id"], worker_id="child-wait", lease_seconds=120)
        runs = [await db.get(AgentRun, root_run_id), await db.get(AgentRun, member["run_id"])]
        runs.sort(key=lambda run: run.turn_id)
        for index, run in enumerate(runs):
            await settle_checkpoint(
                db=db,
                run=run,
                worker_id="root-worker" if run.id == root_run_id else "child-wait",
                status="interrupted",
                token_usage=None,
                waitpoint={
                    "id": f"wait-{index}",
                    "run_id": run.id,
                    "kind": "cooperation",
                    "target_sessions": ["unused"],
                    "after_cursor": 0,
                    "deadline": "invalid" if index == 0 else "2000-01-01T00:00:00+00:00",
                },
            )
        bad_turn, good_turn = runs[0].turn_id, runs[1].turn_id
        bad_run, good_run = runs[0].id, runs[1].id
        await db.commit()
    with pytest.raises(RuntimeError, match="恢复失败：1"):
        await recover_cooperation_waits()
    async with factory() as db:
        assert (await db.get(AgentTurn, bad_turn)).current_run_id == bad_run
        recovered = await db.get(AgentTurn, good_turn)
        assert recovered.current_run_id != good_run and recovered.status == "running"
        new_run = await db.get(AgentRun, recovered.current_run_id)
        message = await db.get(Message, new_run.input_message_id)
        assert message.extra_metadata["resume"]["wait_timed_out"] is True


async def test_sandbox_release_allows_messages_but_defers_execution(tree, monkeypatch):
    """外部释放停顿时，消息提交不等树锁，新执行在专用锁释放后才能领取。"""
    import threading
    from datetime import timedelta
    from types import SimpleNamespace

    from yuxi.modules.agents.models.cooperation import CooperationRuntime
    from yuxi.modules.agents.repositories.turn import AgentTurnRepository
    from yuxi.modules.agents.services.leases import release_idle_sandboxes

    factory, run_id, root_id, uid = tree
    started, finish = threading.Event(), threading.Event()

    def release(*_args, **_kwargs):
        """暂停外部释放，构造真实 PostgreSQL 锁竞争窗口。"""
        started.set()
        assert finish.wait(10), "test release was not unblocked"

    monkeypatch.setattr("yuxi.modules.agents.services.leases.get_sandbox_provider", lambda: SimpleNamespace(release=release))
    async with factory() as db:
        run = await db.get(AgentRun, run_id)
        await AgentRunRepository(db).set_terminal_status(run_id, status="failed", worker_id="root-worker")
        await AgentTurnRepository(db).set_terminal(await db.get(AgentTurn, run.turn_id), status="failed")
        runtime = await db.get(CooperationRuntime, root_id)
        runtime.idle_since = utc_now() - timedelta(minutes=6)
        await db.commit()
    cleanup = asyncio.create_task(release_idle_sandboxes())
    try:
        assert await asyncio.to_thread(started.wait, 3)
        async with asyncio.timeout(3):
            async with factory() as db:
                root = await db.scalar(select(Session).where(Session.thread_id == root_id))
                await CooperationRepository(db).append(
                    sender=root, recipient=root, key="during-release", kind="message", content="available"
                )
                turn = AgentTurn(id=str(uuid.uuid4()), thread_id=root_id, uid=uid, status="running")
                db.add(turn)
                await db.flush()
                pending = await AgentRunRepository(db).create_run(
                    run_id=str(uuid.uuid4()),
                    thread_id=root_id,
                    runtime_scope_id=root_id,
                    agent_slug=root.agent_id,
                    uid=uid,
                    turn_id=turn.id,
                    session_record_id=root.id,
                    input_payload={},
                )
                turn.current_run_id = pending.id
                pending_id = pending.id
                await db.commit()
                _, acquired = await AgentRunRepository(db).mark_running(pending_id, worker_id="after-release", lease_seconds=120)
                assert not acquired
                await db.commit()
    finally:
        finish.set()
        await cleanup
    async with factory() as db:
        assert await db.scalar(select(CooperationEvent.id).where(CooperationEvent.idempotency_key == "during-release"))
        _, acquired = await AgentRunRepository(db).mark_running(pending_id, worker_id="after-release", lease_seconds=120)
        assert acquired
        await db.commit()
        assert (await db.get(CooperationRuntime, root_id)).released is False


async def test_sandbox_release_keeps_lock_through_repeated_cancellation(tree, monkeypatch):
    """重复取消不能在外部释放结束前交出真实生命周期锁。"""
    import threading
    from datetime import timedelta
    from types import SimpleNamespace

    from sqlalchemy import text

    from yuxi.modules.agents.models.cooperation import CooperationRuntime
    from yuxi.modules.agents.repositories.turn import AgentTurnRepository
    from yuxi.modules.agents.services.leases import _release_idle_sandbox

    factory, run_id, root_id, _ = tree
    started, finish = threading.Event(), threading.Event()

    def release(*_args, **_kwargs):
        """保持外部副作用未完成，独立检查数据库锁。"""
        started.set()
        assert finish.wait(10), "test release was not unblocked"

    monkeypatch.setattr("yuxi.modules.agents.services.leases.get_sandbox_provider", lambda: SimpleNamespace(release=release))
    async with factory() as db:
        run = await db.get(AgentRun, run_id)
        await AgentRunRepository(db).set_terminal_status(run_id, status="failed", worker_id="root-worker")
        await AgentTurnRepository(db).set_terminal(await db.get(AgentTurn, run.turn_id), status="failed")
        (await db.get(CooperationRuntime, root_id)).idle_since = utc_now() - timedelta(minutes=6)
        await db.commit()
    cleanup = asyncio.create_task(_release_idle_sandbox(root_id, utc_now() - timedelta(minutes=5)))
    try:
        assert await asyncio.to_thread(started.wait, 3)
        cleanup.cancel()
        await asyncio.sleep(0)
        cleanup.cancel()
        await asyncio.sleep(0.1)
        async with factory() as db:
            acquired = await db.scalar(
                text("SELECT pg_try_advisory_xact_lock_shared(hashtextextended(:key, 0))"),
                {"key": f"sandbox-release:{root_id}"},
            )
            assert not acquired, "external release still running after lifecycle lock was lost"
        assert not cleanup.done()
    finally:
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await cleanup
    async with factory() as db:
        assert await db.scalar(
            text("SELECT pg_try_advisory_xact_lock_shared(hashtextextended(:key, 0))"),
            {"key": f"sandbox-release:{root_id}"},
        )


async def test_expired_lease_failure_does_not_block_other_runs(tree, monkeypatch):
    """单条失联收敛失败后，另一条 Run 的失败终态仍持久化。"""
    from datetime import timedelta

    from yuxi.modules.agents.services.leases import reconcile_expired_run_leases

    factory, _, _, _ = tree
    bad = await child(tree, name="bad-lease", call_id="bad-lease")
    good = await child(tree, name="good-lease", call_id="good-lease")
    async with factory() as db:
        for member in (bad, good):
            run, acquired = await AgentRunRepository(db).mark_running(member["run_id"], worker_id="expired", lease_seconds=120)
            assert acquired
            run.lease_expires_at = utc_now() - timedelta(seconds=2)
        await db.commit()
    original = AgentRunRepository.reconcile_expired_lease

    async def reconcile(repo, run_id, **kwargs):
        """只注入一个记录的恢复故障。"""
        if run_id == bad["run_id"]:
            raise RuntimeError("single record failure")
        return await original(repo, run_id, **kwargs)

    monkeypatch.setattr(AgentRunRepository, "reconcile_expired_lease", reconcile)
    with pytest.raises(RuntimeError, match="失联执行恢复失败：1"):
        await reconcile_expired_run_leases()
    async with factory() as db:
        assert (await db.get(AgentRun, bad["run_id"])).status == "running"
        assert (await db.get(AgentRun, good["run_id"])).status == "failed"
        assert (await db.get(AgentTurn, good["turn_id"])).status == "failed"


async def test_stopped_member_failure_does_not_block_other_members(tree, monkeypatch):
    """停止某个成员失败时，其他成员仍按已持久停止意图取消。"""
    from yuxi.modules.agents.models.cooperation import CooperationRuntime
    from yuxi.modules.agents.services.cooperation import reconcile_stopped_trees

    factory, _, root_id, _ = tree
    member = await child(tree)
    async with factory() as db:
        (await db.get(CooperationRuntime, root_id)).stopped = True
        await db.commit()
    original = SessionRepository.lock_session_by_thread_id

    async def lock(repo, thread_id):
        """注入根成员的锁定故障。"""
        if thread_id == root_id:
            raise RuntimeError("root unavailable")
        return await original(repo, thread_id)

    monkeypatch.setattr(SessionRepository, "lock_session_by_thread_id", lock)
    with pytest.raises(RuntimeError, match="停止会话恢复失败：1"):
        await reconcile_stopped_trees()
    async with factory() as db:
        assert (await db.get(AgentTurn, member["turn_id"])).status == "cancelled"
        assert (await db.get(AgentRun, member["run_id"])).status == "cancelled"


async def _define_target_agent(tree, *, suffix="target", visibility="private", owner=None, shared_uid=None):
    """建立提示词、工具与模型均不同的独立配置，由树 fixture 清理。"""
    factory, run_id, _, uid = tree
    async with factory() as db:
        run = await db.get(AgentRun, run_id)
        slug = f"{run.agent_slug}-{suffix}"
        db.add(
            Agent(
                slug=slug,
                name="独立核验角色",
                description="核验并交付证据",
                backend_id="ChatbotAgent",
                visibility=visibility,
                created_by=owner or uid,
                share_config={
                    "version": 2,
                    "read_scope": {"access_level": "user", "department_ids": [], "user_uids": [shared_uid or uid]},
                    "manage_scope": None,
                },
                config_json={
                    "context": {
                        "system_prompt": "TARGET_CONFIG",
                        "tools": ["ask_user_question"],
                        "model": "test:target",
                    }
                },
            )
        )
        await db.commit()
    return slug
