"""AgentRun worker 职责。"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

from sqlalchemy import or_, select, text

from yuxi.modules.agents.services.cooperation_notifications import notify_turn_state
from yuxi.modules.agents.runtime_locks import cooperation_lock_key, sandbox_release_lock_key
from yuxi.infrastructure.observability.logging import logger
from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.agents.repositories.input import AgentInputRepository
from yuxi.modules.agents.repositories.runs import TERMINAL_RUN_STATUSES, AgentRunRepository
from yuxi.modules.agents.repositories.sessions import SessionRepository
from yuxi.modules.agents.repositories.turn import AgentTurnRepository
from yuxi.modules.agents.runtime.sandbox.provider import get_sandbox_provider
from yuxi.modules.agents.services.event_writer import publish_run_settlement
from yuxi.modules.agents.services.scheduler import dispatch_next_input
from yuxi.modules.agents.services.tracing import finish_turn_observation_if_terminal
from yuxi.modules.workspace.services.bindings import (
    resolve_session_workdir_path,
)
from yuxi.shared.datetime import utc_now

RUN_LEASE_SECONDS = 120


WORKER_ID = f"worker-{uuid.uuid4().hex}"


SANDBOX_IDLE_SECONDS = 300


async def release_runtime_if_idle(run: AgentRun) -> bool:
    """结束当前执行的清理责任，共享沙盒由独立空闲回收释放。"""
    from yuxi.modules.agents.models.cooperation import CooperationRuntime

    async with pg_manager.get_async_session_context() as db:
        current = await db.scalar(select(AgentRun).where(AgentRun.id == run.id).with_for_update(key_share=True))
        if current is None:
            raise RuntimeError("Run 的 cleanup Owner 不存在")
        if not current.runtime_cleanup_pending:
            return True
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": cooperation_lock_key(current.runtime_scope_id)},
        )
        current.runtime_cleanup_pending = False
        active = await db.scalar(
            select(AgentRun.id)
            .where(AgentRun.runtime_scope_id == current.runtime_scope_id, AgentRun.status.notin_(TERMINAL_RUN_STATUSES))
            .limit(1)
        )
        if active is None:
            runtime = await db.get(CooperationRuntime, current.runtime_scope_id)
            if runtime is not None and runtime.idle_since is None:
                runtime.idle_since = utc_now()
        await db.flush()
    return True


async def release_idle_sandboxes() -> None:
    """分页回收空闲沙盒，独立记录失败并继续其他树。"""
    from datetime import timedelta

    from yuxi.modules.agents.models.cooperation import CooperationRuntime

    cutoff = utc_now() - timedelta(seconds=SANDBOX_IDLE_SECONDS)
    after = ""
    failures = 0
    while True:
        async with pg_manager.get_async_session_context() as db:
            roots = list(
                (
                    await db.scalars(
                        select(CooperationRuntime.tree_root_thread_id)
                        .where(
                            CooperationRuntime.released.is_(False),
                            or_(CooperationRuntime.idle_since.is_(None), CooperationRuntime.idle_since <= cutoff),
                            CooperationRuntime.tree_root_thread_id > after,
                        )
                        .order_by(CooperationRuntime.tree_root_thread_id)
                        .limit(100)
                    )
                ).all()
            )
        if not roots:
            break
        for root_id in roots:
            try:
                await _release_idle_sandbox(root_id, cutoff)
            except Exception:
                failures += 1
                logger.exception("Sandbox idle release failed: tree_root_id=%s", root_id)
        after = roots[-1]
    if failures:
        raise RuntimeError(f"空闲沙盒回收失败：{failures} 棵树")


async def _release_idle_sandbox(root_id: str, cutoff: datetime) -> None:
    """只锁沙盒生命周期，领取执行与回收互斥，消息仍可提交。"""
    from yuxi.modules.agents.models.cooperation import CooperationRuntime

    async with pg_manager.get_async_session_context() as db:
        if not await db.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": sandbox_release_lock_key(root_id)},
        ):
            return
        runtime = await db.get(CooperationRuntime, root_id, populate_existing=True)
        if runtime is None or runtime.released:
            return
        if (
            await db.scalar(
                select(AgentRun.id).where(AgentRun.runtime_scope_id == root_id, AgentRun.status.notin_(TERMINAL_RUN_STATUSES)).limit(1)
            )
            is not None
        ):
            return
        # pending Run 取消不会经过执行清理，周期扫描补齐这一空闲转换。
        if runtime.idle_since is None:
            runtime.idle_since = utc_now()
            return
        if runtime.idle_since > cutoff:
            return
        root = await db.scalar(select(Session).where(Session.thread_id == root_id))
        workdir = await resolve_session_workdir_path(agent_session=root, uid=root.uid, db=db)
        release = asyncio.create_task(
            asyncio.to_thread(
                get_sandbox_provider().release,
                root_id,
                uid=root.uid,
                clear_cache_on_delete_failure=True,
                workdir_path=workdir,
            )
        )
        try:
            await asyncio.shield(release)
        except asyncio.CancelledError:
            # to_thread 不会随协程取消；外部释放结束前不能交出生命周期锁。
            while not release.done():
                try:
                    await asyncio.shield(release)
                except asyncio.CancelledError:
                    continue
            release.result()
            raise
        runtime.released = True


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
                    agent_session.queue_paused = True
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
            if not await release_runtime_if_idle(run):
                continue
            if run.status in TERMINAL_RUN_STATUSES:
                await publish_run_settlement(run.id, run.status, thread_id=run.thread_id)
            if run.status == "completed":
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
