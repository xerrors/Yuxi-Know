"""同一事务内收敛 Run、Turn 与 steer 接管。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.modules.agents.repositories.attachments import AttachmentRepository
from yuxi.modules.agents.repositories.input import AgentInputRepository
from yuxi.modules.agents.repositories.runs import AgentRunRepository
from yuxi.modules.agents.repositories.sessions import SessionRepository
from yuxi.modules.agents.repositories.turn import AgentTurnRepository
from yuxi.modules.agents.services.scope import ActorScope


@dataclass(frozen=True, slots=True)
class RunSettlement:
    """返回本事务固定的 Run 结束原因及后续投递目标。"""

    status: str
    changed: bool
    next_run_id: str | None = None


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
        )
        return pending is not None and not await AttachmentRepository(db).has_unready(pending.id)


async def settle_checkpoint(
    *,
    db: AsyncSession,
    run: AgentRun,
    worker_id: str | None,
    status: str,
    token_usage: dict | None,
    waitpoint: dict | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
) -> RunSettlement:
    """在已锁 Thread 的输出事务内决定 yielded、waiting 或整轮终态。"""
    turn_repo = AgentTurnRepository(db)
    turn = await turn_repo.get_for_scope(
        turn_id=run.turn_id,
        thread_id=run.thread_id,
        uid=run.uid,
        app_id=run.app_id,
        for_update=True,
    )
    if turn is None or turn.current_run_id != run.id:
        raise ValueError("Run 不是目标 Turn 的当前执行段")
    input_repo = AgentInputRepository(db)
    run_repo = AgentRunRepository(db)
    agent_session = await SessionRepository(db).get_session_by_thread_id(run.thread_id)
    if agent_session is None or agent_session.uid != run.uid or agent_session.app_id != run.app_id:
        raise ValueError("Run 的 Thread 归属不一致")

    if status == "completed" and turn.status == "running" and not agent_session.queue_paused:
        pending = await input_repo.get_pending_steer(
            thread_id=run.thread_id,
            uid=run.uid,
            app_id=run.app_id,
        )
        if pending is not None and not await AttachmentRepository(db).has_unready(pending.id):
            terminal, changed = await run_repo.set_terminal_status(run.id, status="yielded", token_usage=token_usage, worker_id=worker_id)
            if terminal is None or not changed:
                raise ValueError("Steer 接管前当前 Run 所有权已失效")
            next_run_id = await _consume_steer(db=db, agent_session=agent_session, turn=turn, previous=run, pending=pending)
            return RunSettlement(status="yielded", changed=True, next_run_id=next_run_id)

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
        from yuxi.modules.agents.services.cooperation import notify_turn_state

        await notify_turn_state(db, run)
        return RunSettlement(status="interrupted", changed=True)

    if status == "completed" and turn.status == "running":
        terminal, changed = await run_repo.set_terminal_status(run.id, status="completed", token_usage=token_usage, worker_id=worker_id)
        if terminal is None or not changed:
            raise ValueError("完成终态的 Run 所有权已失效")
        await turn_repo.set_terminal(turn, status="completed", result_run_id=run.id)
        from yuxi.modules.agents.services.cooperation import notify_turn_state

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
        agent_session.queue_paused = True
        if status == "failed":
            await turn_repo.set_terminal(turn, status="failed")
        elif turn.status != "cancelling":
            await turn_repo.set_cancelling(turn)
        from yuxi.modules.agents.services.cooperation import notify_turn_state

        await notify_turn_state(db, run)
        return RunSettlement(status=status, changed=True)

    raise ValueError(f"Turn 状态 {turn.status} 不能接受 Run 终态 {status}")


async def get_run_snapshot(*, db: AsyncSession, scope: ActorScope, thread_id: str, run_id: str) -> dict:
    """按 Thread/Turn/APP 归属读取执行段及持久输出。"""
    agent_session = await SessionRepository(db).get_session_by_thread_id(thread_id)
    if agent_session is None or agent_session.uid != scope.uid or agent_session.app_id != scope.app_id:
        raise HTTPException(status_code=404, detail="Run 不存在")
    run = await AgentRunRepository(db).get_run(run_id)
    if run is None or run.uid != scope.uid or run.app_id != scope.app_id or run.thread_id != thread_id:
        raise HTTPException(status_code=404, detail="Run 不存在")
    turn = await AgentTurnRepository(db).get_for_scope(
        turn_id=run.turn_id,
        thread_id=run.thread_id,
        uid=scope.uid,
        app_id=scope.app_id,
    )
    if turn is None:
        raise HTTPException(status_code=404, detail="Run 不存在")
    from yuxi.modules.agents.services.public_items import serialize_public_run

    input_ids = await AgentInputRepository(db).input_ids_for_runs([run.id])
    result = serialize_public_run(run, input_ids[run.id])
    if run.output_message_id is not None:
        from yuxi.modules.agents.models.messages import Message

        message = await db.get(Message, run.output_message_id)
        if message is None or message.run_id != run.id or message.turn_id != run.turn_id:
            raise ValueError("Run 输出消息归属不一致")
        await db.refresh(message, attribute_names=["tool_calls"])
        from yuxi.modules.agents.services.public_items import serialize_public_items

        result["output"] = serialize_public_items(message, run, turn.result_run_id)
    else:
        result["output"] = None
    result["langfuse_url"] = None
    if run.langfuse_trace_id:
        from yuxi.infrastructure.observability.langfuse import get_trace_url_by_id_async

        result["langfuse_url"] = await get_trace_url_by_id_async(run.langfuse_trace_id)
    return result


async def _consume_steer(*, db: AsyncSession, agent_session: Session, turn: AgentTurn, previous: AgentRun, pending) -> str:
    """消费 Thread 优先批次，在当前 Turn 建立下一执行段。"""
    input_repo = AgentInputRepository(db)
    batch = await input_repo.ready_batch(thread_id=previous.thread_id, uid=previous.uid, app_id=previous.app_id)
    if not batch or batch[0].id != pending.id or batch[0].kind != "steer":
        raise ValueError("Steer 队头已变化或尚未就绪")
    run_id = str(uuid.uuid4())
    await AgentRunRepository(db).create_run(
        run_id=run_id,
        thread_id=agent_session.thread_id,
        runtime_scope_id=previous.runtime_scope_id,
        agent_slug=previous.agent_slug,
        uid=previous.uid,
        turn_id=turn.id,
        app_id=previous.app_id,
        api_key_id=pending.api_key_id,
        input_payload=previous.input_payload or {},
        source=pending.source,
        channel=pending.channel,
        external_id=pending.external_id,
        origin_metadata=pending.origin_metadata or {},
        session_record_id=agent_session.id,
        resume_from_run_id=previous.id,
        run_type="chat",
        created_by_run_id=previous.created_by_run_id,
    )
    await AgentTurnRepository(db).set_current(turn, run_id=run_id)
    messages = await input_repo.consume(inputs=batch, turn_id=turn.id, run_id=run_id)
    await AgentRunRepository(db).set_input_message(run_id, messages[0].id)
    return run_id
