"""Public Thread 状态、已读与作用域的单元测试。"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker

from test.support.sqlite import create_utc_sqlite_engine
from yuxi.modules.agents.repositories.sessions import SessionRepository, UNVIEWED_RUN_MARKER
from yuxi.modules.agents.services.scope import ActorScope
from yuxi.modules.agents.services.threads import (
    archive_thread,
    get_session_resource,
    list_session_page,
    mark_thread_viewed,
)
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.infrastructure.postgres.base import Base
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.workspace.models import Project
import yuxi.modules.agents.services.threads as thread_service

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]
SCOPE = ActorScope(uid="user-1", app_id=None)


@pytest_asyncio.fixture()
async def session():
    """创建与生产 ORM 同形的独立内存数据库。"""
    engine = create_utc_sqlite_engine()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


async def _seed_thread(
    db, thread_id: str, *, uid: str = "user-1", app_id: str | None = None, last_viewed_run_id: str | None = None
) -> Session:
    """创建一个完整作用域的活动 Thread。"""
    project_id = f"project-{thread_id}"
    db.add(
        Project(
            id=project_id,
            uid=uid,
            selection_status="implicit",
            workdir_path=f"projects/{project_id}",
            directory_mode="managed",
        )
    )
    agent_session = Session(
        thread_id=thread_id,
        project_id=project_id,
        uid=uid,
        app_id=app_id,
        agent_id="main",
        title=thread_id,
        status="active",
        extra_metadata={},
        config_snapshot={"model": "test:chat", "tool_approval_mode": "default"},
        last_viewed_run_id=last_viewed_run_id,
    )
    db.add(agent_session)
    await db.flush()
    return agent_session


async def _seed_run(db, agent_session: Session, run_id: str, status: str, *, created_at: datetime | None = None) -> AgentRun:
    """建立显式 Turn→Run 关系供状态读取。"""
    turn = AgentTurn(
        id=f"turn-{run_id}",
        thread_id=agent_session.thread_id,
        uid=agent_session.uid,
        app_id=agent_session.app_id,
        status="running" if status in {"pending", "running", "cancel_requested"} else "completed",
        result_run_id=run_id if status == "completed" else None,
        current_run_id=run_id,
    )
    run = AgentRun(
        id=run_id,
        thread_id=agent_session.thread_id,
        runtime_scope_id=agent_session.thread_id,
        agent_slug="main",
        uid=agent_session.uid,
        app_id=agent_session.app_id,
        turn_id=turn.id,
        session_record_id=agent_session.id,
        run_type="chat",
        input_payload={},
        status=status,
        created_at=created_at,
    )
    db.add_all([turn, run])
    await db.flush()
    return run


async def test_public_list_maps_run_states_and_enforces_scope(session):
    """侧边栏仅使用可见 Thread 的最新顶层 Run 计算状态。"""
    running = await _seed_thread(session, "thread-running")
    await _seed_run(session, running, "run-running", "running")
    ready = await _seed_thread(session, "thread-ready")
    await _seed_run(session, ready, "run-ready", "completed")
    done = await _seed_thread(session, "thread-done", last_viewed_run_id="run-done")
    await _seed_run(session, done, "run-done", "completed")
    await _seed_thread(session, "thread-empty")
    await _seed_thread(session, "thread-other-app", app_id="app-2")
    await _seed_thread(session, "thread-other-user", uid="user-2")
    await session.commit()

    items = (await list_session_page(db=session, scope=SCOPE, agent_slug=None, after=None, limit=50, order="desc"))[0]
    status_by_id = {item["id"]: (item["status"], item["yuxi"]["unread"]) for item in items}
    assert status_by_id == {
        "thread-running": ("in_progress", False),
        "thread-ready": ("completed", True),
        "thread-done": ("completed", False),
        "thread-empty": ("idle", False),
    }


@pytest.mark.parametrize("kind", ["cooperation", "approval", "answer"])
async def test_sidebar_waiting_activity_survives_viewed_interrupted_run(session, kind):
    """等待状态由 Turn 决定，查看 interrupted Run 不得清除等待标签。"""
    thread = await _seed_thread(session, "thread-waiting", last_viewed_run_id="run-waiting")
    run = await _seed_run(session, thread, "run-waiting", "interrupted")
    turn = await session.get(AgentTurn, run.turn_id)
    turn.status = "waiting"
    turn.waitpoint = {"kind": kind, "run_id": run.id}
    await session.commit()
    listed = (await list_session_page(db=session, scope=SCOPE, agent_slug=None, after=None, limit=50, order="desc"))[0]
    expected = "in_progress" if kind == "cooperation" else "requires_action"
    assert listed[0]["status"] == expected
    await mark_thread_viewed(db=session, scope=SCOPE, thread_id=thread.thread_id)
    viewed = await get_session_resource(db=session, scope=SCOPE, thread_id=thread.thread_id)
    assert viewed["status"] == expected and viewed["yuxi"]["unread"] is False


async def test_latest_run_wins_and_viewed_mark_tracks_exact_run(session):
    """新 Run 产生后旧已读标记不掩盖未读结果。"""
    thread = await _seed_thread(session, "thread-latest", last_viewed_run_id="run-old")
    created_at = datetime(2026, 9, 29, 8, 0, 0)
    await _seed_run(session, thread, "run-old", "completed", created_at=created_at)
    await _seed_run(session, thread, "run-new", "completed", created_at=created_at + timedelta(seconds=1))
    await session.commit()

    before = (await list_session_page(db=session, scope=SCOPE, agent_slug=None, after=None, limit=50, order="desc"))[0]
    assert before[0]["yuxi"]["unread"] is True
    await mark_thread_viewed(db=session, thread_id=thread.thread_id, scope=SCOPE)
    after = (await list_session_page(db=session, scope=SCOPE, agent_slug=None, after=None, limit=50, order="desc"))[0]
    assert after[0]["yuxi"]["unread"] is False
    assert thread.last_viewed_run_id == "run-new"


async def test_viewed_mark_does_not_complete_active_run(session):
    """活动 Run 仍保持加载状态，不能被查看操作伪装为完成。"""
    thread = await _seed_thread(session, "thread-active")
    await _seed_run(session, thread, "run-active", "running")
    await session.commit()

    await mark_thread_viewed(db=session, thread_id=thread.thread_id, scope=SCOPE)
    snapshot = await get_session_resource(db=session, scope=SCOPE, thread_id=thread.thread_id)
    assert snapshot["status"] == "in_progress" and snapshot["yuxi"]["unread"] is False
    assert snapshot["yuxi"]["current_turn"] == {
        "id": "turn-run-active",
        "status": "in_progress",
        "current_run_id": "run-active",
        "waitpoint": None,
        "result_run_id": None,
    }


async def test_public_archive_refuses_active_turn(session):
    """归档不能绕过尚未结束的 Turn。"""
    thread = await _seed_thread(session, "thread-active")
    await _seed_run(session, thread, "run-active", "running")
    await session.commit()

    with pytest.raises(HTTPException) as failure:
        await archive_thread(db=session, scope=SCOPE, thread_id=thread.thread_id)
    assert failure.value.status_code == 409
    assert thread.status == "active"


async def test_public_archive_refuses_pending_runtime_cleanup(session):
    """Turn 已完成时仍须等待顶层 Run 释放运行时。"""
    thread = await _seed_thread(session, "thread-cleanup")
    run = await _seed_run(session, thread, "run-cleanup", "completed")
    run.runtime_cleanup_pending = True
    await session.commit()

    with pytest.raises(HTTPException) as failure:
        await archive_thread(db=session, scope=SCOPE, thread_id=thread.thread_id)
    assert failure.value.status_code == 409
    assert thread.status == "active"


async def test_new_thread_creation_uses_unviewed_marker(session):
    """新建 Session 有专门的未读标记。"""
    agent_session = await SessionRepository(session).add_session(
        uid="user-1",
        agent_id="main",
        title="new-thread",
        thread_id="thread-new",
        project_id="11111111-1111-4111-8111-111111111111",
    )
    assert agent_session.last_viewed_run_id == UNVIEWED_RUN_MARKER


async def test_new_thread_cannot_seed_attachment_records(session):
    """客户端 metadata 不能伪造已经确认的附件。"""
    agent_session = await SessionRepository(session).add_session(
        uid="user-1",
        agent_id="main",
        thread_id="thread-reserved-metadata",
        metadata={"attachments": [{"bucket_name": "private", "object_name": "secret"}]},
        project_id="22222222-2222-4222-8222-222222222222",
    )
    assert "attachments" not in agent_session.extra_metadata


async def test_read_side_effect_rejects_same_user_other_app(monkeypatch):
    """直接调用 service 也不能跨 APP 使用相同 UID 的 Thread。"""

    class Repository:
        def __init__(self, _db):
            pass

        async def lock_session_by_thread_id(self, _thread_id):
            return SimpleNamespace(uid="user-1", app_id="app-a", status="active")

    monkeypatch.setattr(thread_service, "SessionRepository", Repository)
    with pytest.raises(HTTPException) as exc:
        await thread_service.mark_thread_viewed(
            db=object(),
            scope=ActorScope(uid="user-1", app_id="app-b"),
            thread_id="thread-1",
        )
    assert exc.value.status_code == 404
