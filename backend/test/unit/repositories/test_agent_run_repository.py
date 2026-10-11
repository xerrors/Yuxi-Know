from __future__ import annotations

from datetime import timedelta

import pytest

from test.support.sqlite import create_utc_sqlite_engine
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from yuxi.modules.agents.repositories.runs import AgentRunRepository
from yuxi.modules.agents.models.runs import AgentRun, AgentRunAttempt
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.infrastructure.postgres.base import Base
from yuxi.bootstrap.models import load_models
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.agents.models.messages import Message
from yuxi.shared.datetime import utc_now

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


@pytest_asyncio.fixture()
async def session(monkeypatch):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        "yuxi.modules.agents.repositories.cooperation.CooperationRepository.claim_execution_slot",
        AsyncMock(return_value=True),
    )
    load_models()
    engine = create_utc_sqlite_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


async def _create_run(repository: AgentRunRepository, *, turn_id: str, thread_id: str, uid: str, **values):
    """为仓储单测先建立调度器负责的 Turn。"""
    turn = await repository.db.get(AgentTurn, turn_id)
    if turn is None:
        repository.db.add(
            AgentTurn(
                id=turn_id,
                thread_id=thread_id,
                uid=uid,
                app_id=values.get("app_id"),
                status="running",
            )
        )
        await repository.db.flush()
    return await repository.create_run(
        turn_id=turn_id,
        thread_id=thread_id,
        uid=uid,
        **values,
    )


async def _bind_valid_output(
    db,
    repository: AgentRunRepository,
    run: AgentRun,
    *,
    worker_id: str,
    now,
) -> Message:
    """为运行中的 Run 创建并绑定满足因果约束的输出消息。"""

    if run.session_record_id is None:
        agent_session = Session(
            thread_id=run.thread_id,
            project_id=f"project-{run.thread_id}",
            uid=run.uid,
            agent_id=run.agent_slug,
            status="active",
        )
        db.add(agent_session)
        await db.flush()
        run.session_record_id = agent_session.id

    message = Message(
        session_record_id=run.session_record_id,
        run_id=run.id,
        turn_id=run.turn_id,
        role="assistant",
        content="done",
    )
    db.add(message)
    await db.flush()
    await repository.set_output_message(run.id, message.id, worker_id=worker_id, now=now)
    return message


async def _read_attempts(db, run_id: str) -> list[AgentRunAttempt]:
    """直接读取 RunAttempt 事实表，作为独立测试 oracle。"""
    attempts = list((await db.scalars(select(AgentRunAttempt).where(AgentRunAttempt.run_id == run_id))).all())
    return sorted(attempts, key=lambda attempt: attempt.attempt_no)


async def test_create_run_persists_origin_snapshot(session):
    run = await _create_run(
        AgentRunRepository(session),
        run_id="origin-run",
        thread_id="thread-1",
        agent_slug="main",
        uid="user-1",
        turn_id="origin-turn",
        input_payload={"model_spec": "provider:model"},
        source="agent_call",
        channel="api",
        external_id="external-1",
        origin_metadata={"agent_invocation_meta": {"trace_id": "trace-1"}},
    )
    await session.commit()

    assert run.source == "agent_call"
    assert run.channel == "api"
    assert run.external_id == "external-1"
    assert run.origin_metadata == {"agent_invocation_meta": {"trace_id": "trace-1"}}
    assert run.runtime_scope_id == "thread-1"


async def test_lock_run_refreshes_stale_same_session_owner(session):
    """锁定查询应覆盖同一 Session 先前读取的旧 owner。"""
    repository = AgentRunRepository(session)
    run = await _create_run(
        repository,
        run_id="refreshed-run",
        thread_id="thread-1",
        agent_slug="main",
        uid="user-1",
        turn_id="refreshed-turn",
        input_payload={},
    )
    await session.flush()
    assert run.status == "pending" and run.worker_id is None
    await session.execute(
        text("UPDATE agent_runs SET status = 'running', worker_id = 'new-owner' WHERE id = :run_id"),
        {"run_id": run.id},
    )

    locked = await repository._lock_run(run.id)
    assert locked.status == "running"
    assert locked.worker_id == "new-owner"


async def test_langfuse_observation_is_written_once_by_current_run_owner(session):
    """只有当前租约 Owner 能固定 Run 的观察身份。"""
    repository = AgentRunRepository(session)
    run = await _create_run(
        repository,
        run_id="observation-run",
        thread_id="thread-1",
        agent_slug="main",
        uid="user-1",
        turn_id="observation-turn",
        input_payload={},
    )
    now = utc_now()
    run.status = "running"
    run.worker_id = "owner-1"
    run.lease_expires_at = now + timedelta(minutes=1)
    await session.flush()

    with pytest.raises(ValueError, match="Owner|owner|租约"):
        await repository.set_langfuse_observation_id(run.id, "0123456789abcdef", worker_id="owner-2", now=now)
    await repository.set_langfuse_observation_id(run.id, "0123456789abcdef", worker_id="owner-1", now=now)
    await repository.set_langfuse_observation_id(run.id, "0123456789abcdef", worker_id="owner-1", now=now)
    with pytest.raises(ValueError, match="不同"):
        await repository.set_langfuse_observation_id(run.id, "fedcba9876543210", worker_id="owner-1", now=now)
    assert run.langfuse_observation_id == "0123456789abcdef"


async def test_set_output_message_rejects_wrong_causal_owner_and_accepts_exact_message(session):
    repository = AgentRunRepository(session)
    agent_session = Session(
        thread_id="output-thread",
        project_id="project-output-thread",
        uid="user-1",
        agent_id="main",
        status="active",
    )
    other_session = Session(
        thread_id="other-output-thread",
        project_id="project-other-output-thread",
        uid="user-1",
        agent_id="main",
        status="active",
    )
    session.add_all([agent_session, other_session])
    await session.flush()
    run = await _create_run(
        repository,
        run_id="output-run",
        thread_id=agent_session.thread_id,
        agent_slug="main",
        uid="user-1",
        turn_id="output-turn",
        input_payload={},
        session_record_id=agent_session.id,
    )
    now = utc_now()
    await repository.mark_running(
        run.id,
        worker_id="output-worker:attempt-1",
        lease_seconds=60,
        now=now,
    )
    candidates = [
        Message(
            session_record_id=other_session.id,
            run_id=run.id,
            turn_id=run.turn_id,
            role="assistant",
            content="other agent_session",
        ),
        Message(
            session_record_id=agent_session.id,
            run_id="other-run",
            turn_id=run.turn_id,
            role="assistant",
            content="other run",
        ),
        Message(
            session_record_id=agent_session.id,
            run_id=run.id,
            turn_id=run.turn_id,
            role="user",
            content="wrong role",
        ),
        Message(
            session_record_id=agent_session.id,
            run_id=None,
            turn_id=None,
            role="assistant",
            content="missing run",
        ),
        Message(
            session_record_id=agent_session.id,
            run_id=run.id,
            turn_id="other-turn",
            role="assistant",
            content="other turn",
        ),
    ]
    session.add_all(candidates)
    await session.flush()

    for candidate in candidates:
        with pytest.raises(ValueError, match="同一 agent_session"):
            await repository.set_output_message(
                run.id,
                candidate.id,
                worker_id="output-worker:attempt-1",
                now=now + timedelta(seconds=1),
            )
        assert run.output_message_id is None

    with pytest.raises(ValueError, match="同一 agent_session"):
        await repository.set_output_message(
            run.id,
            999_999,
            worker_id="output-worker:attempt-1",
            now=now + timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="lease owner"):
        await repository.set_output_message(
            run.id,
            candidates[0].id,
            worker_id="output-worker:attempt-2",
            now=now + timedelta(seconds=1),
        )

    exact = await _bind_valid_output(
        session,
        repository,
        run,
        worker_id="output-worker:attempt-1",
        now=now + timedelta(seconds=1),
    )
    rebound = await repository.set_output_message(
        run.id,
        exact.id,
        worker_id="output-worker:attempt-1",
        now=now + timedelta(seconds=2),
    )

    assert rebound is run
    assert run.output_message_id == exact.id


async def test_completed_transition_rejects_missing_output_binding(session):
    repository = AgentRunRepository(session)
    run = await _create_run(
        repository,
        run_id="missing-output-run",
        thread_id="missing-output-thread",
        agent_slug="main",
        uid="user-1",
        turn_id="missing-output-turn",
        input_payload={},
    )
    now = utc_now()
    await repository.mark_running(
        run.id,
        worker_id="missing-output-worker:attempt-1",
        lease_seconds=60,
        now=now,
    )

    with pytest.raises(ValueError, match="完成前必须绑定"):
        await repository.set_terminal_status(
            run.id,
            status="completed",
            worker_id="missing-output-worker:attempt-1",
            now=now + timedelta(seconds=1),
        )

    assert run.status == "running"
    assert run.worker_id == "missing-output-worker:attempt-1"


async def _seed_thread_run(db, *, thread_id: str, run_id: str, status: str, run_type: str = "chat"):
    turn_id = f"turn-{run_id}"
    db.add(
        AgentTurn(
            id=turn_id,
            thread_id=thread_id,
            uid="user-1",
            status="running" if status == "running" else "completed",
        )
    )
    await db.flush()
    run = AgentRun(
        id=run_id,
        thread_id=thread_id,
        runtime_scope_id=thread_id,
        agent_slug="main",
        uid="user-1",
        status=status,
        turn_id=turn_id,
        run_type=run_type,
        created_by_run_id=None,
        input_payload={},
    )
    db.add(run)
    await db.flush()
    return run


async def test_get_latest_top_level_runs_for_threads_picks_latest_chat_resume(session):
    await _seed_thread_run(session, thread_id="t1", run_id="t1-old", status="completed")
    await _seed_thread_run(session, thread_id="t1", run_id="t1-running", status="running")
    await _seed_thread_run(session, thread_id="t2", run_id="t2-sub", status="running", run_type="chat")
    await _seed_thread_run(session, thread_id="t2", run_id="t2-done", status="completed")
    await session.commit()

    result = await AgentRunRepository(session).get_latest_top_level_runs_for_threads("user-1", ["t1", "t2"])

    assert result["t1"] == ("t1-running", "running")
    assert result["t2"] == ("t2-done", "completed")


async def test_get_latest_top_level_runs_for_threads_scopes_by_user(session):
    await _seed_thread_run(session, thread_id="t1", run_id="t1-done", status="completed")
    session.add(AgentTurn(id="turn-other", thread_id="t1", uid="user-2", status="running"))
    session.add(
        AgentRun(
            id="t1-other",
            thread_id="t1",
            runtime_scope_id="t1",
            agent_slug="main",
            uid="user-2",
            status="running",
            turn_id="turn-other",
            run_type="chat",
            input_payload={},
        )
    )
    await session.commit()

    result = await AgentRunRepository(session).get_latest_top_level_runs_for_threads("user-1", ["t1"])

    assert result["t1"] == ("t1-done", "completed")


async def test_get_latest_top_level_runs_for_threads_empty_input(session):
    result = await AgentRunRepository(session).get_latest_top_level_runs_for_threads("user-1", [])
    assert result == {}


async def test_set_terminal_status_persists_token_usage_only_for_winner(session):
    repo = AgentRunRepository(session)
    run = await _create_run(
        repo,
        run_id="usage-run",
        thread_id="thread-1",
        agent_slug="main",
        uid="user-1",
        turn_id="usage-turn",
        input_payload={},
    )
    usage = {
        "schema_version": 2,
        "models": {"provider:model": {}},
        "total": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
    }
    now = utc_now()
    _, acquired = await repo.mark_running(
        run.id,
        worker_id="worker-usage:attempt-1",
        lease_seconds=60,
        now=now,
    )
    await _bind_valid_output(
        session,
        repo,
        run,
        worker_id="worker-usage:attempt-1",
        now=now + timedelta(milliseconds=500),
    )

    persisted, changed = await repo.set_terminal_status(
        run.id,
        status="completed",
        token_usage=usage,
        worker_id="worker-usage:attempt-1",
        now=now + timedelta(seconds=1),
    )
    loser, loser_changed = await repo.set_terminal_status(
        run.id,
        status="failed",
        token_usage={"total": {"input_tokens": 999}},
    )

    assert acquired is True
    assert changed is True
    assert persisted.token_usage == usage
    assert loser_changed is False
    assert loser.token_usage == usage


async def test_owned_run_requires_exact_owner_for_terminal_transition(session):
    repo = AgentRunRepository(session)
    run = await _create_run(
        repo,
        run_id="owned-run",
        thread_id="owned-thread",
        agent_slug="main",
        uid="user-1",
        turn_id="owned-turn",
        input_payload={},
    )
    now = utc_now()
    _, acquired = await repo.mark_running(
        run.id,
        worker_id="worker-1:attempt-1",
        lease_seconds=60,
        now=now,
    )
    acquired_lease_expires_at = run.lease_expires_at
    await _bind_valid_output(
        session,
        repo,
        run,
        worker_id="worker-1:attempt-1",
        now=now + timedelta(milliseconds=500),
    )

    _, missing_owner_changed = await repo.set_terminal_status(run.id, status="failed")
    _, other_owner_changed = await repo.set_terminal_status(
        run.id,
        status="failed",
        worker_id="worker-1:attempt-2",
    )
    persisted, owner_changed = await repo.set_terminal_status(
        run.id,
        status="completed",
        worker_id="worker-1:attempt-1",
    )

    assert acquired is True
    assert acquired_lease_expires_at == now + timedelta(seconds=60)
    assert missing_owner_changed is False
    assert other_owner_changed is False
    assert owner_changed is True
    assert persisted.status == "completed"
    assert persisted.worker_id is None
    assert persisted.heartbeat_at is None
    assert persisted.lease_expires_at is None


async def test_attempt_owner_blocks_duplicate_until_retry_release(session):
    repo = AgentRunRepository(session)
    run = await _create_run(
        repo,
        run_id="retry-run",
        thread_id="retry-thread",
        agent_slug="main",
        uid="user-1",
        turn_id="retry-turn",
        input_payload={},
    )
    now = utc_now()

    _, first_acquired = await repo.mark_running(
        run.id,
        worker_id="worker-1:attempt-1",
        lease_seconds=60,
        now=now,
    )
    _, duplicate_acquired = await repo.mark_running(
        run.id,
        worker_id="worker-1:attempt-2",
        lease_seconds=60,
        now=now + timedelta(seconds=1),
    )
    released = await repo.release_lease_for_retry(
        run.id,
        worker_id="worker-1:attempt-1",
        now=now + timedelta(seconds=1),
    )
    _, blocked_before_cleanup = await repo.mark_running(
        run.id,
        worker_id="worker-1:attempt-2",
        lease_seconds=60,
        now=now + timedelta(seconds=2),
    )
    run.runtime_cleanup_pending = False
    await session.flush()
    _, retry_acquired = await repo.mark_running(
        run.id,
        worker_id="worker-1:attempt-2",
        lease_seconds=60,
        now=now + timedelta(seconds=3),
    )

    assert first_acquired is True
    assert duplicate_acquired is False
    assert released is True
    assert blocked_before_cleanup is False
    assert retry_acquired is True
    assert run.status == "running"
    assert run.worker_id == "worker-1:attempt-2"


async def test_expired_owner_cannot_finish_or_release_before_reconciliation(session):
    """过期 attempt 不能抢在 reconciler 前伪装成功或触发自动重试。"""
    repo = AgentRunRepository(session)
    run = await _create_run(
        repo,
        run_id="expired-owner-run",
        thread_id="expired-owner-thread",
        agent_slug="main",
        uid="user-1",
        turn_id="expired-owner-turn",
        input_payload={},
    )
    now = utc_now()
    _, acquired = await repo.mark_running(
        run.id,
        worker_id="worker-expired:attempt-1",
        lease_seconds=10,
        now=now,
    )

    released = await repo.release_lease_for_retry(
        run.id,
        worker_id="worker-expired:attempt-1",
        now=now + timedelta(seconds=11),
    )
    _, completed = await repo.set_terminal_status(
        run.id,
        status="completed",
        worker_id="worker-expired:attempt-1",
        now=now + timedelta(seconds=11),
    )
    reconciled = await repo.reconcile_expired_lease(run.id, now=now + timedelta(seconds=11))

    assert acquired is True
    assert released is False
    assert completed is False
    assert reconciled is run
    assert run.status == "failed"
    assert run.error_type == "worker_lease_expired"


async def test_pending_cancel_is_terminal_without_fake_worker_expiry(session):
    """从未执行的 pending Run 由用户取消后直接形成 cancelled 事实。"""
    agent_session = Session(
        thread_id="cancel-pending-thread",
        project_id="project-cancel-pending-thread",
        uid="user-1",
        agent_id="main",
        status="active",
    )
    session.add(agent_session)
    await session.flush()
    message = Message(
        session_record_id=agent_session.id,
        role="user",
        content="cancel before worker",
        delivery_status="dispatched",
    )
    session.add(message)
    await session.flush()
    repo = AgentRunRepository(session)
    run = await _create_run(
        repo,
        run_id="cancel-pending-run",
        thread_id=agent_session.thread_id,
        agent_slug="main",
        uid="user-1",
        turn_id="cancel-pending-turn",
        input_payload={},
        session_record_id=agent_session.id,
        input_message_id=message.id,
    )

    message.run_id = run.id
    message.turn_id = run.turn_id
    await session.flush()
    cancelled, cancelled_ids = await repo.request_cancel_run(
        run_id=run.id,
        uid="user-1",
    )
    reconciled = await repo.reconcile_expired_lease(run.id, now=utc_now() + timedelta(minutes=5))
    await session.refresh(message)

    assert cancelled is run
    assert cancelled_ids == [run.id]
    assert run.status == "cancelled"
    assert run.error_type == "cancelled"
    assert run.worker_id is None
    assert run.lease_expires_at is None
    assert message.delivery_status == "cancelled"
    assert reconciled is None


async def test_durable_cancel_wins_terminal_race_for_live_owner(session):
    """cancel_requested 提交后，同一 owner 也只能确认 cancelled。"""
    repo = AgentRunRepository(session)
    run = await _create_run(
        repo,
        run_id="cancel-race-run",
        thread_id="cancel-race-thread",
        agent_slug="main",
        uid="user-1",
        turn_id="cancel-race-turn",
        input_payload={},
    )
    now = utc_now()
    _, acquired = await repo.mark_running(
        run.id,
        worker_id="worker-cancel:attempt-1",
        lease_seconds=60,
        now=now,
    )
    target, cancelled_ids = await repo.request_cancel_run(
        run_id=run.id,
        uid="user-1",
    )

    _, completed = await repo.set_terminal_status(
        run.id,
        status="completed",
        worker_id="worker-cancel:attempt-1",
        now=now + timedelta(seconds=1),
    )
    persisted, cancelled = await repo.set_terminal_status(
        run.id,
        status="cancelled",
        error_type="cancelled",
        worker_id="worker-cancel:attempt-1",
        now=now + timedelta(seconds=1),
    )

    assert acquired is True
    assert cancelled_ids == [run.id]
    assert target is run
    assert completed is False
    assert cancelled is True
    assert persisted.status == "cancelled"


async def test_parent_cancel_does_not_cancel_other_session(session):
    repo = AgentRunRepository(session)
    now = utc_now()
    parent = await _create_run(
        repo,
        run_id="tree-parent-run",
        thread_id="tree-runtime",
        runtime_scope_id="tree-runtime",
        agent_slug="main",
        uid="user-1",
        turn_id="tree-parent-turn",
        input_payload={},
    )
    child = await _create_run(
        repo,
        run_id="tree-child-run",
        thread_id="tree-child-thread",
        runtime_scope_id="tree-child-thread",
        agent_slug="worker",
        uid="user-1",
        turn_id="tree-child-turn",
        input_payload={},
        created_by_run_id=parent.id,
        run_type="chat",
    )
    await repo.mark_running(parent.id, worker_id="parent-worker", lease_seconds=60, now=now)
    await repo.mark_running(child.id, worker_id="child-worker", lease_seconds=60, now=now)

    for run in (parent, child):
        session.add(
            Session(
                thread_id=run.thread_id,
                project_id="project-tree",
                uid="user-1",
                agent_id=run.agent_slug,
                status="active",
            )
        )
        turn = await session.get(AgentTurn, run.turn_id)
        turn.current_run_id = run.id
    await session.flush()
    _, cancelled = await repo.request_cancel_run(run_id=parent.id, uid="user-1")
    await session.refresh(child)
    assert cancelled == [parent.id]
    assert child.status == "running"
    assert child.error_type is None
    assert child.worker_id == "child-worker"
    assert child.heartbeat_at is not None
    assert child.lease_expires_at is not None


async def _seed_running_run(db, *, run_id: str = "attempt-run", turn_id: str = "attempt-turn") -> AgentRun:
    run = await _create_run(
        AgentRunRepository(db),
        run_id=run_id,
        thread_id="attempt-thread",
        agent_slug="main",
        uid="user-1",
        turn_id=turn_id,
        input_payload={},
    )
    await db.flush()
    return run


async def test_mark_running_creates_single_attempt_for_initial_claim_and_live_owner(session):
    repository = AgentRunRepository(session)
    run = await _seed_running_run(session)
    now = utc_now()

    _, first_acquired = await repository.mark_running(run.id, worker_id="worker-a:token-1", lease_seconds=60, now=now)
    _, second_acquired = await repository.mark_running(
        run.id, worker_id="worker-a:token-1", lease_seconds=60, now=now + timedelta(seconds=1)
    )
    attempts = await _read_attempts(session, run.id)

    assert first_acquired is True
    assert second_acquired is True
    assert [attempt.attempt_no for attempt in attempts] == [1]
    assert attempts[0].worker_id == "worker-a:token-1"
    assert attempts[0].finished_at is None


async def test_retry_release_then_reclaim_uses_new_attempt_no_and_keeps_old_fact(session):
    repository = AgentRunRepository(session)
    run = await _seed_running_run(session)
    now = utc_now()

    await repository.mark_running(run.id, worker_id="worker-a:token-1", lease_seconds=60, now=now)
    released = await repository.release_lease_for_retry(run.id, worker_id="worker-a:token-1", now=now + timedelta(seconds=1))
    _, blocked_before_cleanup = await repository.mark_running(
        run.id, worker_id="worker-b:token-2", lease_seconds=60, now=now + timedelta(seconds=2)
    )
    run.runtime_cleanup_pending = False
    await session.flush()
    await repository.mark_running(run.id, worker_id="worker-b:token-2", lease_seconds=60, now=now + timedelta(seconds=3))
    attempts = await _read_attempts(session, run.id)

    assert released is True
    assert blocked_before_cleanup is False
    assert [attempt.attempt_no for attempt in attempts] == [1, 2]
    assert attempts[0].outcome == "retry_released"
    assert attempts[0].finished_at is not None
    assert attempts[1].worker_id == "worker-b:token-2"
    assert attempts[1].outcome is None


async def test_terminal_status_finishes_owner_attempt_with_matching_outcome(session):
    repository = AgentRunRepository(session)
    run = await _seed_running_run(session, run_id="terminal-attempt-run", turn_id="terminal-attempt-turn")
    now = utc_now()

    await repository.mark_running(run.id, worker_id="worker-a:token-1", lease_seconds=60, now=now)
    await _bind_valid_output(
        session,
        repository,
        run,
        worker_id="worker-a:token-1",
        now=now + timedelta(seconds=1),
    )
    _, changed = await repository.set_terminal_status(
        run.id, status="completed", worker_id="worker-a:token-1", now=now + timedelta(seconds=2)
    )
    attempts = await _read_attempts(session, run.id)

    assert changed is True
    assert len(attempts) == 1
    assert attempts[0].outcome == "completed"
    assert attempts[0].finished_at is not None


async def test_reconcile_closes_open_attempt_as_lease_expired(session):
    repository = AgentRunRepository(session)
    run = await _seed_running_run(session, run_id="reconcile-run", turn_id="reconcile-turn")
    now = utc_now()

    await repository.mark_running(run.id, worker_id="worker-dead:token-1", lease_seconds=10, now=now)
    reconciled = await repository.reconcile_expired_lease(run.id, now=now + timedelta(seconds=11))
    attempts = await _read_attempts(session, run.id)

    assert reconciled is run
    assert len(attempts) == 1
    assert attempts[0].outcome == "lease_expired"
    assert attempts[0].error_type == "worker_lease_expired"


async def test_record_run_manifest_is_write_once_and_requires_live_owner(session):
    repository = AgentRunRepository(session)
    run = await _seed_running_run(session, run_id="manifest-run", turn_id="manifest-turn")
    now = utc_now()

    await repository.mark_running(run.id, worker_id="worker-a:token-1", lease_seconds=60, now=now)

    with pytest.raises(ValueError, match="lease owner"):
        await repository.record_run_manifest(
            run.id,
            manifest={"version": 1},
            fingerprint="a" * 64,
            worker_id="worker-b:token-2",
            now=now + timedelta(seconds=1),
        )

    _, recorded = await repository.record_run_manifest(
        run.id,
        manifest={"version": 1, "agent": {"slug": "main"}},
        fingerprint="b" * 64,
        worker_id="worker-a:token-1",
        now=now + timedelta(seconds=2),
    )
    _, rewritten = await repository.record_run_manifest(
        run.id,
        manifest={"version": 1, "agent": {"slug": "changed"}},
        fingerprint="c" * 64,
        worker_id="worker-a:token-1",
        now=now + timedelta(seconds=3),
    )
    attempts = await _read_attempts(session, run.id)

    assert recorded is True
    assert rewritten is False
    assert run.manifest == {"version": 1, "agent": {"slug": "main"}}
    assert run.manifest_fingerprint == "b" * 64
    assert run.manifest_recorded_at == now + timedelta(seconds=2)
    # manifest 固化不得额外制造执行占有事实。
    assert len(attempts) == 1

    with pytest.raises(ValueError, match="lease owner"):
        await repository.record_run_manifest(
            run.id,
            manifest={"version": 1},
            fingerprint="d" * 64,
            worker_id="worker-a:token-1",
            now=now + timedelta(seconds=61),
        )


async def test_run_timing_is_write_once_and_requires_live_owner(session):
    repository = AgentRunRepository(session)
    run = await _seed_running_run(session, run_id="timing-run", turn_id="timing-turn")
    now = utc_now()
    owner = "worker-a:token-1"

    await repository.mark_running(run.id, worker_id=owner, lease_seconds=60, now=now)

    with pytest.raises(ValueError, match="lease owner"):
        await repository.record_prepared(
            run.id,
            worker_id="worker-stale:token-2",
            observed_at=now + timedelta(seconds=1),
            checked_at=now + timedelta(seconds=1),
        )

    with pytest.raises(ValueError, match="lease owner"):
        await repository.record_prepared(
            run.id,
            worker_id=owner,
            observed_at=now + timedelta(seconds=1),
            checked_at=now + timedelta(seconds=61),
        )

    with pytest.raises(ValueError, match="不能早于创建时间"):
        await repository.record_first_model_request(
            run.id,
            worker_id=owner,
            observed_at=run.created_at - timedelta(seconds=1),
            checked_at=now + timedelta(seconds=1),
        )

    _, prepared = await repository.record_prepared(
        run.id,
        worker_id=owner,
        observed_at=now + timedelta(seconds=2),
        checked_at=now + timedelta(seconds=2),
    )
    _, prepared_again = await repository.record_prepared(
        run.id,
        worker_id=owner,
        observed_at=now + timedelta(seconds=3),
        checked_at=now + timedelta(seconds=3),
    )
    _, first_output = await repository.record_first_output(
        run.id,
        worker_id=owner,
        observed_at=now + timedelta(seconds=7),
        checked_at=now + timedelta(seconds=7),
    )
    _, first_output_again = await repository.record_first_output(
        run.id,
        worker_id=owner,
        observed_at=now + timedelta(seconds=8),
        checked_at=now + timedelta(seconds=8),
    )
    _, first_model_request = await repository.record_first_model_request(
        run.id,
        worker_id=owner,
        observed_at=now + timedelta(seconds=3),
        checked_at=now + timedelta(seconds=3),
    )
    _, first_model_request_again = await repository.record_first_model_request(
        run.id,
        worker_id=owner,
        observed_at=now + timedelta(seconds=4),
        checked_at=now + timedelta(seconds=4),
    )

    assert prepared is True
    assert prepared_again is False
    assert first_output is True
    assert first_output_again is False
    assert first_model_request is True
    assert first_model_request_again is False
    assert run.prepared_at == now + timedelta(seconds=2)
    assert run.first_model_request_at == now + timedelta(seconds=3)
    assert run.first_output_at == now + timedelta(seconds=7)


async def test_run_first_output_requires_prepared_timestamp(session):
    repository = AgentRunRepository(session)
    run = await _seed_running_run(session, run_id="unprepared-run", turn_id="unprepared-turn")
    now = utc_now()
    owner = "worker-a:token-1"
    await repository.mark_running(run.id, worker_id=owner, lease_seconds=60, now=now)

    with pytest.raises(ValueError, match="不能早于准备完成时间"):
        await repository.record_first_output(
            run.id,
            worker_id=owner,
            observed_at=now + timedelta(seconds=1),
            checked_at=now + timedelta(seconds=1),
        )

    assert run.first_output_at is None


async def test_lock_memory_write_requires_current_top_level_lease_owner(session):
    repository = AgentRunRepository(session)
    run = await _seed_running_run(session, run_id="memory-run", turn_id="memory-turn")
    now = utc_now()
    await repository.mark_running(run.id, worker_id="worker-a:token-1", lease_seconds=60, now=now)

    locked = await repository.lock_memory_write(
        run.id,
        uid="user-1",
        worker_id="worker-a:token-1",
        thread_id="attempt-thread",
        now=now + timedelta(seconds=1),
    )

    assert locked is run
    with pytest.raises(ValueError, match="lease owner"):
        await repository.lock_memory_write(
            run.id,
            uid="user-1",
            worker_id="worker-b:token-2",
            thread_id="attempt-thread",
            now=now + timedelta(seconds=2),
        )
    with pytest.raises(ValueError, match="同一顶层 Run"):
        await repository.lock_memory_write(
            run.id,
            uid="other-user",
            worker_id="worker-a:token-1",
            thread_id="attempt-thread",
            now=now + timedelta(seconds=2),
        )
