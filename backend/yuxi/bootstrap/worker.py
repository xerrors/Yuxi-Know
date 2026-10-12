"""Worker 进程装配与后台执行维护。"""

from __future__ import annotations

import asyncio

from yuxi.infrastructure.observability.logging import logger
from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.infrastructure.postgres.schema import require_current_schema
from yuxi.modules.agents.services.cooperation import reconcile_stopped_trees, recover_cooperation_waits
from yuxi.modules.agents.services.leases import (
    WORKER_ID,
    reconcile_expired_run_leases,
    reconcile_pending_runtime_cleanups,
    release_idle_sandboxes,
)
from yuxi.modules.agents.services.scheduler import recover_pending_dispatches
from yuxi.modules.agents.services.transport import (
    RUN_RECONCILIATION_SECONDS,
    WORKER_RECONCILIATION_HEALTH_KEY,
    WORKER_RECONCILIATION_HEALTH_TTL_SECONDS,
    publish_worker_health,
)
from yuxi.modules.extensions.mcp.service import ensure_builtin_mcp_servers_in_db
from yuxi.modules.extensions.skills.builtin.sync import init_builtin_skills
from yuxi.modules.identity.security import AuthUtils
from yuxi.modules.schedules.service import claim_and_dispatch_due_jobs, recover_scheduled_dispatches
from yuxi.workers.background_jobs import reconcile_and_publish_jobs
from yuxi.workers.health import (
    JOB_RECONCILIATION_HEALTH_KEY,
    JOB_RECONCILIATION_HEALTH_TTL_SECONDS,
    JOB_RECONCILIATION_SECONDS,
)

_RECONCILIATION_TASK_KEY = "agent_run_reconciliation_task"
_SANDBOX_CLEANUP_TASK_KEY = "sandbox_cleanup_task"


_JOB_RECONCILIATION_TASK_KEY = "background_job_reconciliation_task"


async def _worker_startup(ctx):
    """初始化 worker 依赖。"""

    if not isinstance(ctx, dict):
        raise TypeError("ARQ worker context 必须是字典")
    AuthUtils.require_security_secrets()
    ctx["worker_id"] = WORKER_ID
    pg_manager.initialize()
    await require_current_schema(pg_manager)
    async with pg_manager.get_async_session_context() as session:
        from yuxi.modules.system.options import ensure_options_in_db, invalidate_option_cache, system_options

        await ensure_options_in_db(session)
        await session.commit()
    await invalidate_option_cache(system_options.key)
    try:
        await ensure_builtin_mcp_servers_in_db()
    except Exception as exc:
        logger.error(
            "Optional worker component failed: component=builtin_mcp_servers, type=%s",
            type(exc).__name__,
        )
    async with pg_manager.get_async_session_context() as session:
        await init_builtin_skills(session)
    await _reconcile_agent_runs_once()
    await reconcile_and_publish_jobs()
    await _publish_job_reconciliation_health()
    ctx[_SANDBOX_CLEANUP_TASK_KEY] = asyncio.create_task(_reconcile_sandboxes_forever())
    ctx[_RECONCILIATION_TASK_KEY] = asyncio.create_task(_reconcile_agent_run_leases_forever())
    ctx[_JOB_RECONCILIATION_TASK_KEY] = asyncio.create_task(_reconcile_background_jobs_forever())


async def _worker_shutdown(ctx):
    """关闭 worker 共享连接。"""

    if isinstance(ctx, dict):
        reconciliation_tasks = [
            ctx.pop(_RECONCILIATION_TASK_KEY, None),
            ctx.pop(_JOB_RECONCILIATION_TASK_KEY, None),
            ctx.pop(_SANDBOX_CLEANUP_TASK_KEY, None),
        ]
        reconciliation_tasks = [task for task in reconciliation_tasks if task is not None]
        for task in reconciliation_tasks:
            task.cancel()
        if reconciliation_tasks:
            await asyncio.gather(*reconciliation_tasks, return_exceptions=True)
    from yuxi.modules.agents.services.transport import close_queue_clients

    await close_queue_clients()
    await pg_manager.close()


async def _reconcile_agent_run_leases_forever() -> None:
    """周期收敛执行状态，各阶段失败不阻断其他调度。"""
    while True:
        await asyncio.sleep(RUN_RECONCILIATION_SECONDS)
        await _reconcile_agent_runs_once()


async def _reconcile_agent_runs_once() -> None:
    """隔离阶段错误；只有完整成功才续报恢复能力健康。"""
    healthy = True
    for phase, operation in (
        ("expired_leases", reconcile_expired_run_leases),
        ("runtime_cleanup", reconcile_pending_runtime_cleanups),
        ("stopped_trees", reconcile_stopped_trees),
        ("cooperation_waits", recover_cooperation_waits),
        ("pending_dispatches", recover_pending_dispatches),
        ("scheduled_dispatches", recover_scheduled_dispatches),
        ("due_jobs", claim_and_dispatch_due_jobs),
    ):
        try:
            await operation()
        except Exception:
            healthy = False
            logger.exception("Agent reconciliation failed: phase=%s", phase)
    if healthy:
        try:
            await _publish_reconciliation_health()
        except Exception:
            logger.exception("Agent reconciliation health publication failed")


async def _reconcile_sandboxes_forever() -> None:
    """外部沙盒回收独立运行，慢释放不占据调度恢复循环。"""
    while True:
        try:
            await release_idle_sandboxes()
        except Exception:
            logger.exception("Sandbox cleanup reconciliation failed")
        await asyncio.sleep(RUN_RECONCILIATION_SECONDS)


async def _reconcile_background_jobs_forever() -> None:
    """周期收敛失联通用 Job，并补发持久 pending 意图。"""
    while True:
        await asyncio.sleep(JOB_RECONCILIATION_SECONDS)
        try:
            reconciled = await reconcile_and_publish_jobs()
            if reconciled:
                logger.warning("Reconciled expired durable jobs: count=%s", len(reconciled))
            await _publish_job_reconciliation_health()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error("Failed to reconcile durable jobs", exc_info=True)


async def _publish_job_reconciliation_health() -> None:
    """续租 worker 的 后台作业 收敛与 pending 补发能力。"""
    await publish_worker_health(
        JOB_RECONCILIATION_HEALTH_KEY,
        WORKER_ID,
        JOB_RECONCILIATION_HEALTH_TTL_SECONDS,
    )


async def _publish_reconciliation_health() -> None:
    """续租 worker 的 AgentRun lease 收敛能力；持续失败后 readiness 自动失效。"""

    await publish_worker_health(
        WORKER_RECONCILIATION_HEALTH_KEY,
        WORKER_ID,
        WORKER_RECONCILIATION_HEALTH_TTL_SECONDS,
    )
