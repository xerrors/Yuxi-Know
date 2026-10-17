"""AgentRun worker 职责。"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

from sqlalchemy import select

from yuxi.infrastructure.filesystem import await_io
from yuxi.infrastructure.observability.logging import logger
from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.repositories.input import AgentInputRepository
from yuxi.modules.agents.repositories.runs import TERMINAL_RUN_STATUSES, AgentRunRepository
from yuxi.modules.agents.repositories.sessions import SessionRepository
from yuxi.modules.agents.repositories.turn import AgentTurnRepository
from yuxi.modules.agents.runtime.sandbox.provider import get_sandbox_provider
from yuxi.modules.agents.services.cooperation_notifications import notify_turn_state
from yuxi.modules.agents.services.event_writer import publish_run_settlement
from yuxi.modules.agents.services.scheduler import dispatch_next_input
from yuxi.modules.agents.services.tracing import finish_turn_observation_if_terminal

RUN_LEASE_SECONDS = 120


WORKER_ID = f"worker-{uuid.uuid4().hex}"


async def complete_run_command_cleanup(run: AgentRun) -> bool:
    """确认该 Run 外部命令清理后才释放 cleanup 责任。"""
    async with pg_manager.get_async_session_context() as db:
        current = await db.scalar(select(AgentRun).where(AgentRun.id == run.id).with_for_update(key_share=True))
        if current is None:
            raise RuntimeError("Run 的 cleanup Owner 不存在")
        if current.runtime_cleanup_pending:
            # 与 retry 领取持同一 Run 锁；取消也必须等待外部清理结束后才能释放。
            await await_io(asyncio.to_thread(get_sandbox_provider().cancel_run, current.uid, current.id))
            current.runtime_cleanup_pending = False
            await db.flush()
    if current.status == "cancelled":
        from yuxi.modules.agents.services.turns import finish_cancelled_run

        await finish_cancelled_run(current)
    return True


async def maintain_user_sandboxes() -> None:
    """维护用户环境；所有会话空闲后暂停，不删除 VM。"""
    await asyncio.to_thread(get_sandbox_provider().maintain)


async def mark_run_running(run_id: str, worker_id: str) -> bool:
    async with pg_manager.get_async_session_context() as db:
        repo = AgentRunRepository(db)
        _, acquired = await repo.mark_running(
            run_id,
            worker_id=worker_id,
            lease_seconds=RUN_LEASE_SECONDS,
        )
        return acquired


async def renew_run_lease(run_id: str, worker_id: str) -> bool:
    """在独立事务中续租；owner 或 lease 已失效时返回 False。"""
    async with pg_manager.get_async_session_context() as db:
        return await AgentRunRepository(db).renew_lease(
            run_id,
            worker_id=worker_id,
            lease_seconds=RUN_LEASE_SECONDS,
        )


async def run_attempt_finished(run_id: str, worker_id: str) -> bool:
    """确认终态由当前最后一次 attempt 提交，不能把其他 Owner 的终态当作成功收尾。"""
    async with pg_manager.get_async_session_context() as db:
        repo = AgentRunRepository(db)
        run = await repo.get_run(run_id)
        if run is None or run.status not in TERMINAL_RUN_STATUSES:
            return False
        attempts = await repo.list_run_attempts(run_id)
        if not attempts:
            return False
        attempt = attempts[-1]
        return (
            attempt.worker_id == worker_id
            and attempt.outcome == run.status
            and attempt.finished_at is not None
            and attempt.finished_at == run.finished_at
        )


async def release_run_lease_for_retry(run_id: str, worker_id: str) -> bool:
    """释放当前 attempt 的 lease，允许下一次 ARQ attempt 使用新 token。"""
    async with pg_manager.get_async_session_context() as db:
        repo = AgentRunRepository(db)
        released = await repo.release_lease_for_retry(run_id, worker_id=worker_id)
    return released


async def reconcile_expired_run_leases(*, now: datetime | None = None) -> list[str]:
    """收敛过期 Run ownership；重复或并发执行只返回本次实际转换的 Run。"""
    async with pg_manager.get_async_session_context() as db:
        candidates = await AgentRunRepository(db).list_expired_lease_candidates(now=now)
    reconciled: list[str] = []
    terminal_turn_ids: list[str] = []
    failures = 0
    for run_id, root_thread_id, uid, app_id in candidates:
        try:
            async with pg_manager.get_async_session_context() as db:
                agent_session = await SessionRepository(db).lock_session_by_thread_id(root_thread_id)
                if agent_session is None or agent_session.uid != uid or agent_session.app_id != app_id:
                    continue
                repo = AgentRunRepository(db)
                candidate = await repo.get_run(run_id)
                if candidate is None:
                    continue
                turn = await AgentTurnRepository(db).get_for_scope(
                    turn_id=candidate.turn_id,
                    thread_id=root_thread_id,
                    uid=uid,
                    app_id=app_id,
                    for_update=True,
                )
                if turn is None:
                    raise ValueError("失联 Run 的根 Turn 不存在")
                # 恢复使用相同 Input→Run 锁序；返回行无需参与失联状态裁决。
                await AgentInputRepository(db).get_pending_steer(thread_id=root_thread_id, uid=uid, app_id=app_id)
                run = await repo.reconcile_expired_lease(run_id, now=now)
                if run is None:
                    continue
                if turn.current_run_id == run.id:
                    agent_session.queue_paused = await AgentInputRepository(db).has_pending_inputs(
                        thread_id=agent_session.thread_id,
                        uid=agent_session.uid,
                        app_id=agent_session.app_id,
                    )
                    await AgentTurnRepository(db).set_terminal(turn, status="failed")

                    await notify_turn_state(db, run)
                    terminal_turn_ids.append(turn.id)
                reconciled.append(run.id)
        except Exception:
            failures += 1
            logger.exception("Expired lease recovery failed: run_id=%s", run_id)
    for turn_id in terminal_turn_ids:
        await finish_turn_observation_if_terminal(turn_id)
    await reconcile_pending_runtime_cleanups()
    if failures:
        raise RuntimeError(f"失联执行恢复失败：{failures} 条")
    return reconciled


async def reconcile_pending_runtime_cleanups() -> list[str]:
    """重试 PostgreSQL 持久拥有的 runtime cleanup，并在成功后发布终态。"""
    async with pg_manager.get_async_session_context() as db:
        pending_runs = await AgentRunRepository(db).list_pending_runtime_cleanups()
    cleaned: list[str] = []
    failures = 0
    for run in pending_runs:
        try:
            if not await complete_run_command_cleanup(run):
                continue
            if run.status in TERMINAL_RUN_STATUSES:
                await publish_run_settlement(run.id, run.status, thread_id=run.thread_id)
            if run.status in {"completed", "failed", "cancelled"}:
                await dispatch_next_input(
                    uid=run.uid,
                    agent_slug=run.agent_slug,
                    thread_id=run.thread_id,
                )
            cleaned.append(run.id)
        except Exception:
            failures += 1
            logger.exception("Run cleanup recovery failed: run_id=%s", run.id)
    from yuxi.modules.agents.services.turns import reconcile_cancelling_turns

    await reconcile_cancelling_turns()
    if failures:
        raise RuntimeError(f"执行清理恢复失败：{failures} 条")
    return cleaned
