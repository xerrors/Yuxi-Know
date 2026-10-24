"""Project 删除不能绕开 Thread 的归档条件。"""

import os
import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.modules.agents.models.inputs import AgentInput
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.modules.agents.input_messages import build_chat_input_message, serialize_input_message
from yuxi.modules.agents.scope import ActorScope
from yuxi.modules.agents.services.threads import archive_thread
from yuxi.modules.identity.models import User
from yuxi.modules.workspace.models import Project
from yuxi.modules.workspace.services.projects import delete_project_view
from yuxi.shared.datetime import utc_now
from yuxi.shared.errors import DomainError, StateConflictError

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


@pytest.mark.parametrize("pending_kind", ["input", "turn"])
async def test_project_delete_rejects_pending_work_then_archives_history(pending_kind):
    """持久输入或活跃 Turn 存在时拒绝级联，清空后保留归档历史。"""
    engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex
    uid = f"project-archive-{suffix}"
    project_id = f"project-{suffix}"
    thread_id = f"thread-{suffix}"
    work_id = f"work-{suffix}"
    try:
        async with sessions() as db:
            db.add(User(username=uid, uid=uid, password_hash="test", role="user"))
            await db.flush()
            db.add(
                Project(
                    id=project_id,
                    uid=uid,
                    name="Project",
                    selection_status="selectable",
                    workdir_path=f"projects/{project_id}",
                    directory_mode="managed",
                )
            )
            await db.flush()
            db.add(Session(thread_id=thread_id, uid=uid, agent_id="main", project_id=project_id))
            await db.flush()
            if pending_kind == "input":
                db.add(
                    AgentInput(
                        id=work_id,
                        thread_id=thread_id,
                        uid=uid,
                        agent_slug="main",
                        kind="follow_up",
                        status="pending",
                        messages=[serialize_input_message(build_chat_input_message("pending input"))],
                    )
                )
            else:
                db.add(AgentTurn(id=work_id, thread_id=thread_id, uid=uid, status="running"))
            await db.commit()

        async with sessions() as db:
            with pytest.raises(DomainError) as exc_info:
                await delete_project_view(uid=uid, project_id=project_id, db=db)
            assert isinstance(exc_info.value, StateConflictError)
            await db.rollback()

        async with sessions() as db:
            assert (await db.get(Project, project_id)).status == "active"
            assert (await db.scalar(select(Session).where(Session.thread_id == thread_id))).status == "active"
            if pending_kind == "input":
                await db.execute(delete(AgentInput).where(AgentInput.id == work_id))
            else:
                await db.execute(delete(AgentTurn).where(AgentTurn.id == work_id))
            await db.commit()

        async with sessions() as db:
            result = await delete_project_view(uid=uid, project_id=project_id, db=db)
            assert result["archived_threads"] == 1

        async with sessions() as db:
            assert (await db.get(Project, project_id)).status == "deleted"
            agent_session = await db.scalar(select(Session).where(Session.thread_id == thread_id))
            assert agent_session is not None and agent_session.status == "archived"
    finally:
        async with sessions() as db:
            await db.execute(delete(AgentInput).where(AgentInput.id == work_id))
            await db.execute(delete(AgentTurn).where(AgentTurn.id == work_id))
            await db.execute(delete(Session).where(Session.thread_id == thread_id))
            await db.execute(delete(Project).where(Project.id == project_id))
            await db.execute(delete(User).where(User.uid == uid))
            await db.commit()
        await engine.dispose()


@pytest.mark.parametrize(
    ("remaining_work", "archive_target"),
    [
        (work, target)
        for work in ("child_run", "child_waiting", "child_pending", "child_cleanup", "runtime_cleanup")
        for target in ("root", "child")
        if target == "root" or work != "runtime_cleanup"
    ],
)
async def test_archive_preserves_entry_for_unfinished_work(remaining_work, archive_target):
    """根与成员使用相同结束条件，成员空闲后可在根仍有工作时归档。"""
    engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex
    uid = f"archive-tree-{suffix}"
    project_id = f"project-{suffix}"
    thread_id = f"thread-{suffix}"
    child_thread_id = f"child-{suffix}"
    turn_id = f"turn-{suffix}"
    child_turn_id = f"child-turn-{suffix}"
    root_run_id = f"root-{suffix}"
    child_run_id = f"run-child-{suffix}"
    archive_id = thread_id if archive_target == "root" else child_thread_id
    scope = ActorScope(uid=uid, app_id=None)
    try:
        async with sessions() as db:
            db.add(User(username=uid, uid=uid, password_hash="test", role="user"))
            await db.flush()
            db.add(
                Project(
                    id=project_id,
                    uid=uid,
                    selection_status="selectable",
                    workdir_path=f"projects/{project_id}",
                    directory_mode="managed",
                )
            )
            await db.flush()
            parent = Session(thread_id=thread_id, uid=uid, agent_id="main", project_id=project_id)
            db.add(parent)
            await db.flush()
            if remaining_work != "runtime_cleanup":
                child = Session(
                    thread_id=child_thread_id,
                    uid=uid,
                    tree_root_thread_id=thread_id,
                    parent_thread_id=thread_id,
                    cooperation_name="helper",
                    cooperation_path="/root/helper",
                    agent_id="helper",
                    project_id=project_id,
                    status="active",
                )
                db.add(child)
                await db.flush()
            db.add(AgentTurn(id=turn_id, thread_id=thread_id, uid=uid, status="completed"))
            await db.flush()
            db.add(
                AgentRun(
                    id=root_run_id,
                    thread_id=thread_id,
                    runtime_scope_id=thread_id,
                    agent_slug="main",
                    uid=uid,
                    turn_id=turn_id,
                    session_record_id=parent.id,
                    run_type="chat",
                    status="completed",
                    input_payload={},
                    runtime_cleanup_pending=remaining_work == "runtime_cleanup",
                )
            )
            await db.flush()
            if remaining_work == "child_pending":
                child.queue_paused = True
                db.add(
                    AgentInput(
                        id=child_turn_id,
                        thread_id=child_thread_id,
                        uid=uid,
                        agent_slug="helper",
                        kind="follow_up",
                        status="pending",
                        messages=[serialize_input_message(build_chat_input_message("queued child work"))],
                    )
                )
            elif remaining_work != "runtime_cleanup":
                child_status = {"child_run": "cancelling", "child_waiting": "waiting", "child_cleanup": "completed"}[remaining_work]
                db.add(
                    AgentTurn(
                        id=child_turn_id,
                        thread_id=child_thread_id,
                        uid=uid,
                        status=child_status,
                        waitpoint={"kind": "answer"} if remaining_work == "child_waiting" else None,
                    )
                )
                await db.flush()
                db.add(
                    AgentRun(
                        id=child_run_id,
                        thread_id=child_thread_id,
                        runtime_scope_id=thread_id,
                        agent_slug="helper",
                        uid=uid,
                        turn_id=child_turn_id,
                        session_record_id=child.id,
                        run_type="chat",
                        created_by_run_id=root_run_id,
                        status={"child_run": "cancel_requested", "child_waiting": "interrupted", "child_cleanup": "completed"}[
                            remaining_work
                        ],
                        runtime_cleanup_pending=remaining_work == "child_cleanup",
                        input_payload={},
                    )
                )
            await db.commit()

        async with sessions() as db:
            with pytest.raises(StateConflictError):
                await archive_thread(db=db, scope=scope, thread_id=archive_id)
            await db.rollback()
            with pytest.raises(DomainError) as project_error:
                await delete_project_view(uid=uid, project_id=project_id, db=db)
            assert isinstance(project_error.value, StateConflictError)
            await db.rollback()

        async with sessions() as db:
            assert (await db.get(Project, project_id)).status == "active"
            assert (await db.scalar(select(Session).where(Session.thread_id == thread_id))).status == "active"
            if remaining_work == "child_pending":
                queued = await db.get(AgentInput, child_turn_id)
                queued.status = "cancelled"
                queued.cancelled_at = utc_now()
            elif remaining_work != "runtime_cleanup":
                (await db.get(AgentRun, child_run_id)).status = "cancelled"
                (await db.get(AgentRun, child_run_id)).runtime_cleanup_pending = False
                (await db.get(AgentTurn, child_turn_id)).status = "cancelled"
            else:
                (await db.get(AgentRun, root_run_id)).runtime_cleanup_pending = False
            if archive_target == "child":
                (await db.get(AgentRun, root_run_id)).status = "pending"
                (await db.get(AgentTurn, turn_id)).status = "running"
            await db.commit()

        async with sessions() as db:
            await archive_thread(db=db, scope=scope, thread_id=archive_id)

        async with sessions() as db:
            agent_session = await db.scalar(select(Session).where(Session.thread_id == archive_id))
            assert agent_session is not None and agent_session.status == "archived"
            if archive_target == "child":
                root = await db.scalar(select(Session).where(Session.thread_id == thread_id))
                assert root.status == "active"
                assert (await db.get(AgentRun, root_run_id)).status == "pending"
                assert (await db.get(AgentTurn, turn_id)).status == "running"
                with pytest.raises(StateConflictError):
                    await delete_project_view(uid=uid, project_id=project_id, db=db)
                await db.rollback()
                (await db.get(AgentRun, root_run_id)).status = "completed"
                (await db.get(AgentTurn, turn_id)).status = "completed"
                await db.commit()

        async with sessions() as db:
            result = await delete_project_view(uid=uid, project_id=project_id, db=db)
            assert result["archived_threads"] == (0 if remaining_work == "runtime_cleanup" else 1)
    finally:
        async with sessions() as db:
            await db.execute(delete(AgentInput).where(AgentInput.thread_id == child_thread_id))
            await db.execute(delete(AgentRun).where(AgentRun.turn_id.in_([turn_id, child_turn_id])))

            await db.execute(delete(AgentTurn).where(AgentTurn.id.in_([turn_id, child_turn_id])))
            await db.execute(delete(Session).where(Session.uid == uid))
            await db.execute(delete(Project).where(Project.id == project_id))
            await db.execute(delete(User).where(User.uid == uid))
            await db.commit()
        await engine.dispose()
