"""同一事务内收敛 Run、Turn 与 steer 接管。"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.modules.agents.models.inputs import AgentInput
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.modules.agents.repositories.attachments import AttachmentRepository
from yuxi.modules.agents.repositories.input import AgentInputRepository
from yuxi.modules.agents.repositories.runs import AgentRunRepository
from yuxi.modules.agents.repositories.sessions import SessionRepository
from yuxi.modules.agents.repositories.turn import AgentTurnRepository
from yuxi.modules.agents.scope import ActorScope
from yuxi.modules.agents.services.cooperation_notifications import notify_turn_state
from yuxi.modules.agents.services.run_creation import create_turn_run
from yuxi.modules.agents.services.scheduler import Dispatch
from yuxi.modules.workspace.services.bindings import resolve_session_workdir_binding
from yuxi.shared.errors import ResourceNotFoundError


@dataclass(frozen=True, slots=True)
class RunSettlement:
    """返回本事务固定的 Run 结束原因及后续投递目标。"""

    status: str
    changed: bool
    next_dispatch: Dispatch | None = None


async def should_yield_for_steer(run_id: str) -> bool:
    """供 Agent 图安全钩子查询待接管输入；终态仍在 Thread 锁内裁决。"""
    from yuxi.infrastructure.postgres.manager import pg_manager

    async with pg_manager.get_async_session_context() as db:
        run = await AgentRunRepository(db).get_run(run_id)
        if run is None or run.status != "running":
            return False
        agent_session = await SessionRepository(db).get_session_by_thread_id(run.thread_id)
        if agent_session is None or agent_session.queue_paused:
            return False
        turn = await AgentTurnRepository(db).get(run.turn_id)
        if turn is None or turn.status != "running" or turn.current_run_id != run_id:
            return False
        pending = await AgentInputRepository(db).get_pending_steer(
            thread_id=run.thread_id,
            uid=run.uid,
            app_id=run.app_id,
            for_update=False,
            turn_id=turn.id,
        )
        return pending is not None and not await AttachmentRepository(db).has_unready(pending.id)


async def settle_checkpoint(
    *,
    db: AsyncSession,
    run: AgentRun,
    agent_session: Session,
    turn: AgentTurn,
    pending_steer: AgentInput | None,
    worker_id: str | None,
    status: str,
    token_usage: dict | None,
    waitpoint: dict | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
) -> RunSettlement:
    """消费同事务已锁的 Session/Turn 和 steer 裁决，更新持久终态。"""
    turn_repo = AgentTurnRepository(db)
    run_repo = AgentRunRepository(db)
    if turn.current_run_id != run.id:
        raise ValueError("Run 不是目标 Turn 的当前执行段")
    if agent_session.uid != run.uid or agent_session.app_id != run.app_id:
        raise ValueError("Run 的 Thread 归属不一致")

    if status == "completed" and pending_steer is not None:
        terminal, changed = await run_repo.set_terminal_status(run.id, status="yielded", token_usage=token_usage, worker_id=worker_id)
        if terminal is None or not changed:
            raise ValueError("Steer 接管前当前 Run 所有权已失效")
        next_dispatch = await _consume_steer(db=db, agent_session=agent_session, turn=turn, previous=run, pending=pending_steer)
        return RunSettlement(status="yielded", changed=True, next_dispatch=next_dispatch)

    if status == "interrupted" and turn.status == "running":
        if not waitpoint or waitpoint.get("run_id") != run.id:
            raise ValueError("等待终态缺少绑定当前 Run 的等待点")
        terminal, changed = await run_repo.set_terminal_status(
            run.id,
            status="interrupted",
            token_usage=token_usage,
            worker_id=worker_id,
            error_type=error_type,
            error_message=error_message,
        )
        if terminal is None or not changed:
            raise ValueError("等待终态的 Run 所有权已失效")
        await turn_repo.set_waiting(turn, run_id=run.id, waitpoint=waitpoint)

        await notify_turn_state(db, run)
        return RunSettlement(status="interrupted", changed=True)

    if status == "completed" and turn.status == "running":
        terminal, changed = await run_repo.set_terminal_status(run.id, status="completed", token_usage=token_usage, worker_id=worker_id)
        if terminal is None or not changed:
            raise ValueError("完成终态的 Run 所有权已失效")
        await turn_repo.set_terminal(turn, status="completed", result_run_id=run.id)

        await notify_turn_state(db, run)
        return RunSettlement(status="completed", changed=True)

    if status in {"failed", "cancelled"}:
        terminal, changed = await run_repo.set_terminal_status(
            run.id,
            status=status,
            token_usage=token_usage,
            worker_id=worker_id,
            error_type=error_type,
            error_message=error_message,
        )
        if terminal is None or not changed:
            return RunSettlement(status=terminal.status if terminal else status, changed=False)
        agent_session.queue_paused = await AgentInputRepository(db).has_pending_inputs(
            thread_id=agent_session.thread_id,
            uid=agent_session.uid,
            app_id=agent_session.app_id,
        )
        if status == "failed":
            await turn_repo.set_terminal(turn, status="failed")
        elif turn.status != "cancelling":
            await turn_repo.set_cancelling(turn)

        await notify_turn_state(db, run)
        return RunSettlement(status=status, changed=True)

    raise ValueError(f"Turn 状态 {turn.status} 不能接受 Run 终态 {status}")


async def lock_ready_steer(db: AsyncSession, *, agent_session: Session, turn: AgentTurn) -> AgentInput | None:
    """在 Thread/Turn 锁之后锁定 steer，裁决附件就绪，再允许取得 Run 锁。"""
    if turn.status != "running" or agent_session.queue_paused:
        return None
    pending = await AgentInputRepository(db).get_pending_steer(
        thread_id=agent_session.thread_id,
        uid=agent_session.uid,
        app_id=agent_session.app_id,
        turn_id=turn.id,
    )
    if pending is None or await AttachmentRepository(db).has_unready(pending.id):
        return None
    return pending


async def get_run_snapshot(*, db: AsyncSession, scope: ActorScope, thread_id: str, run_id: str) -> dict:
    """按 Thread/Turn/APP 归属读取执行段及持久输出。"""
    agent_session = await SessionRepository(db).get_session_by_thread_id(thread_id)
    if agent_session is None or agent_session.uid != scope.uid or agent_session.app_id != scope.app_id:
        raise ResourceNotFoundError("Run 不存在")
    run = await AgentRunRepository(db).get_run(run_id)
    if run is None or run.uid != scope.uid or run.app_id != scope.app_id or run.thread_id != thread_id:
        raise ResourceNotFoundError("Run 不存在")
    turn = await AgentTurnRepository(db).get_for_scope(
        turn_id=run.turn_id,
        thread_id=run.thread_id,
        uid=scope.uid,
        app_id=scope.app_id,
    )
    if turn is None:
        raise ResourceNotFoundError("Run 不存在")
    from yuxi.modules.agents.services.public_items import serialize_public_run

    input_ids = await AgentInputRepository(db).input_ids_for_runs([run.id])
    result = serialize_public_run(run, input_ids[run.id])
    if run.output_message_id is not None:
        from yuxi.modules.agents.models.messages import Message

        message = await db.get(Message, run.output_message_id)
        if message is None or message.run_id != run.id or message.turn_id != run.turn_id:
            raise ValueError("Run 输出消息归属不一致")
        from yuxi.modules.agents.services.public_items import serialize_public_items

        result["output"] = serialize_public_items(message, run, turn.result_run_id)
    else:
        result["output"] = None
    result["langfuse_url"] = None
    if run.langfuse_trace_id:
        from yuxi.infrastructure.observability.langfuse import get_trace_url_by_id_async

        result["langfuse_url"] = await get_trace_url_by_id_async(run.langfuse_trace_id)
    return result


async def _consume_steer(*, db: AsyncSession, agent_session: Session, turn: AgentTurn, previous: AgentRun, pending) -> Dispatch:
    """消费 Thread 优先批次，在当前 Turn 建立下一执行段。"""
    input_repo = AgentInputRepository(db)
    batch = await input_repo.ready_batch(thread_id=previous.thread_id, uid=previous.uid, app_id=previous.app_id, turn_id=turn.id)
    if not batch or batch[0].id != pending.id or batch[0].kind != "steer":
        raise ValueError("Steer 队头已变化或尚未就绪")
    run = await create_turn_run(
        db=db, agent_session=agent_session, turn=turn, source=pending, previous=previous, api_key_id=pending.api_key_id
    )
    run_id = run.id
    messages = await input_repo.consume(inputs=batch, turn_id=turn.id, run_id=run_id)
    await AgentRunRepository(db).set_input_message(run_id, messages[0].id)
    binding = await resolve_session_workdir_binding(agent_session=agent_session, uid=previous.uid, db=db)
    return Dispatch(run_id=run_id, binding=binding)
