"""线程级主动上下文压缩用例。"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.infrastructure.observability.logging import logger
from yuxi.modules.agents.models.inputs import AgentInput
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.modules.agents.repositories.definitions import AgentRepository
from yuxi.modules.agents.services.thread_access import require_thread
from yuxi.modules.agents.scope import ActorScope
from yuxi.modules.agents.repositories.state import AgentStateRepository
from yuxi.modules.agents.runtime.agent_backends import AgentBackendNotFoundError, get_agent_backend
from yuxi.modules.agents.runtime.context import DEFAULT_SUMMARY_THRESHOLD_K, BaseContext, prepare_agent_runtime_context
from yuxi.modules.agents.runtime.middlewares import create_summary_middleware_from_context
from yuxi.modules.agents.runtime.middlewares.token_usage import TOKEN_USAGE_CONTEXT_FIELDS
from yuxi.modules.agents.runtime.sandbox import ProvisionerSandboxBackend, get_sandbox_provider
from yuxi.modules.agents.runtime.sandbox.backend import create_agent_composite_backend
from yuxi.modules.agents.runtime.sandbox.paths import runtime_workdir_path
from yuxi.modules.extensions.skills.projection import get_user_skills_root_dir
from yuxi.modules.identity.models import User
from yuxi.modules.workspace.services.bindings import ensure_session_workdir_available
from yuxi.shared.errors import ResourceNotFoundError, StateConflictError


async def compress_thread_context(
    *,
    thread_id: str,
    current_user: User,
    db: AsyncSession,
    app_id: str | None = None,
) -> dict[str, Any]:
    """在线程空闲时压缩 checkpoint；同线程新请求由 Session 行锁串行化。"""
    uid = str(current_user.uid)
    agent_session = await require_thread(db=db, scope=ActorScope(uid=uid, app_id=app_id), thread_id=thread_id, lock=True)
    if agent_session.status != "active":
        raise ResourceNotFoundError("对话线程不存在")

    agent_slug = agent_session.agent_id
    await _ensure_thread_idle(db=db, thread_id=thread_id)

    agent_item = await AgentRepository(db).get_visible_by_slug(
        slug=agent_slug,
        user=current_user,
    )
    if agent_item is None:
        raise ResourceNotFoundError("智能体不存在")
    try:
        agent = get_agent_backend(agent_item.backend_id)
    except AgentBackendNotFoundError as exc:
        raise ResourceNotFoundError(str(exc)) from exc

    context = agent.context_schema()
    configured = agent_session.config_snapshot
    if configured is None:
        raise ValueError("Session 缺少配置快照")
    context.update_config(configured)
    model_spec = context.model
    workdir_path = await ensure_session_workdir_available(
        agent_session=agent_session,
        uid=uid,
        db=db,
    )
    # 主动压缩没有 Run lease，使用独立维护沙盒，避免释放协作树的执行环境。
    runtime_scope_id = str(uuid.uuid4())
    context.update(
        {
            "uid": uid,
            "thread_id": thread_id,
            "model": model_spec,
            "runtime_scope_id": runtime_scope_id,
            "workdir_relative_path": workdir_path,
            "workdir_path": runtime_workdir_path(workdir_path),
        }
    )
    result = await _compress_agent_checkpoint_in_runtime(
        agent=agent,
        context=context,
        runtime_scope_id=runtime_scope_id,
        uid=uid,
        workdir_path=workdir_path,
    )
    await db.commit()
    return result


async def _ensure_thread_idle(*, db: AsyncSession, thread_id: str) -> None:
    """在 Thread 锁内拒绝活跃 Turn 和待消费 Input。"""
    active_turn = await db.scalar(
        select(AgentTurn.id)
        .where(
            AgentTurn.thread_id == thread_id,
            AgentTurn.status.in_(("running", "waiting", "cancelling")),
        )
        .limit(1)
    )
    pending_input = await db.scalar(select(AgentInput.id).where(AgentInput.thread_id == thread_id, AgentInput.status == "pending").limit(1))
    if active_turn is None and pending_input is None:
        return
    raise StateConflictError("线程仍有运行、交互或排队输入，暂时不能压缩", code="thread_busy")


async def _compress_agent_checkpoint_in_runtime(
    *,
    agent,
    context: BaseContext,
    runtime_scope_id: str,
    uid: str,
    workdir_path: str,
) -> dict[str, Any]:
    """在一次性 Sandbox 生命周期内压缩 checkpoint。"""
    try:
        await prepare_agent_runtime_context(context)
        await _ensure_runtime_available(thread_id=runtime_scope_id, uid=uid, workdir_path=workdir_path)
        result = await _compress_agent_checkpoint(agent=agent, context=context)
    except BaseException:
        try:
            await _release_runtime(thread_id=runtime_scope_id, uid=uid, workdir_path=workdir_path)
        except BaseException as release_error:
            logger.error(f"主动压缩失败后释放 Sandbox 失败: {release_error}")
        raise
    else:
        await _release_runtime(thread_id=runtime_scope_id, uid=uid, workdir_path=workdir_path)
        return result


async def _ensure_runtime_available(*, thread_id: str, uid: str, workdir_path: str) -> None:
    """确保主动压缩可以通过 Agent backend 写入可恢复历史。"""
    await asyncio.to_thread(get_user_skills_root_dir(uid).mkdir, parents=True, exist_ok=True)
    backend = ProvisionerSandboxBackend(thread_id=thread_id, uid=uid, workdir_path=workdir_path)
    await asyncio.to_thread(backend.ensure_available)


async def _release_runtime(*, thread_id: str, uid: str, workdir_path: str) -> None:
    """释放主动压缩创建或复用的 Sandbox。"""
    await asyncio.to_thread(
        get_sandbox_provider().release,
        thread_id,
        uid=uid,
        clear_cache_on_delete_failure=True,
        workdir_path=workdir_path,
    )


async def _compress_agent_checkpoint(*, agent, context: BaseContext) -> dict[str, Any]:
    """使用当前 Agent 配置生成摘要并通过 canonical graph 更新 checkpoint。"""
    graph = await agent.get_graph(context=context)
    compressor = create_summary_middleware_from_context(
        context,
        backend=create_agent_composite_backend(context),
    )
    state_repository = AgentStateRepository(
        graph,
        uid=str(context.uid),
        thread_id=str(context.thread_id),
    )
    values = await state_repository.get_values()
    update, result = await compressor.aforce_summarize(values)
    if update:
        trigger_tokens = getattr(context, "summary_threshold", DEFAULT_SUMMARY_THRESHOLD_K) * 1024
        await state_repository.update(
            _with_compression_usage(
                update,
                previous_values=values,
                result=result,
                summary_trigger_tokens=trigger_tokens,
            )
        )
    return result


def _with_compression_usage(
    update: dict[str, Any],
    *,
    previous_values: dict[str, Any],
    result: dict[str, Any],
    summary_trigger_tokens: int,
) -> dict[str, Any]:
    """把主动压缩结果合并进下一轮上下文压力指标。"""
    previous_usage = previous_values.get("token_usage")
    token_usage = {
        key: value
        for key, value in (previous_usage.items() if isinstance(previous_usage, dict) else ())
        if key not in TOKEN_USAGE_CONTEXT_FIELDS
    }
    token_usage.update(
        {
            "compression": dict(result),
            "summary_active": True,
            "summary_trigger_tokens": summary_trigger_tokens,
        }
    )
    return {**update, "token_usage": token_usage}
