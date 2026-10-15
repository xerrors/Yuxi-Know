"""Turn 等待、恢复、取消及明确结果查询。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from yuxi.infrastructure.observability.logging import logger
from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.modules.agents.models.messages import Message
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.modules.agents.receipts import input_intent_hash, require_idempotency_key, require_receipt_replay
from yuxi.modules.agents.repositories.input_receipt import AgentInputReceiptRepository
from yuxi.modules.agents.repositories.runs import AgentRunRepository
from yuxi.modules.agents.repositories.turn import AgentTurnRepository
from yuxi.modules.agents.scope import ActorScope
from yuxi.modules.agents.services.cooperation_notifications import notify_turn_state, notify_user_intervention
from yuxi.modules.agents.services.run_creation import create_resume_run
from yuxi.modules.agents.services.scheduler import Dispatch, deliver
from yuxi.modules.agents.services.thread_access import require_thread
from yuxi.modules.agents.services.tracing import finish_turn_observation_if_terminal
from yuxi.modules.agents.services.transport import publish_cancel_signals
from yuxi.modules.workspace.services.bindings import resolve_session_workdir_binding
from yuxi.shared.errors import InvalidInputError, InvalidOperationError, ResourceNotFoundError, StateConflictError


async def resume_turn(
    *,
    db: AsyncSession,
    scope: ActorScope,
    thread_id: str,
    turn_id: str,
    waitpoint_id: str,
    response: dict,
    idempotency_key: str,
) -> dict:
    """一次性消费明确等待点，在同一 Turn 建立下一段恢复 Run。"""
    require_idempotency_key(idempotency_key)
    event_type = "yuxi.session.input.resume"
    intent_hash = input_intent_hash(event_type, turn_id, waitpoint_id, response)
    receipt_repo = AgentInputReceiptRepository(db)
    existing = await receipt_repo.get_for_scope(uid=scope.uid, app_id=scope.app_id, thread_id=thread_id, idempotency_key=idempotency_key)
    if existing is not None:
        require_receipt_replay(existing, event_type, intent_hash)
        return _accepted(existing)

    agent_session = await require_thread(db=db, scope=scope, thread_id=thread_id)
    # 与 Agent 删除保持 Agent → Session 的锁序。
    from yuxi.modules.agents.repositories.definitions import AgentRepository
    from yuxi.modules.identity.repositories.users import UserRepository

    user = await UserRepository(db).get_by_uid(scope.uid)
    agent = (
        None
        if user is None or user.is_deleted
        else await AgentRepository(db).get_visible_by_slug(
            slug=agent_session.agent_id,
            user=user,
            for_key_share=True,
        )
    )
    if agent is None:
        raise ResourceNotFoundError("Agent 不可访问")
    agent_session = await require_thread(db=db, scope=scope, thread_id=thread_id, lock=True)
    if agent_session.status != "active":
        raise StateConflictError("Thread 已归档")
    turn_repo = AgentTurnRepository(db)
    turn = await turn_repo.get_for_scope(turn_id=turn_id, thread_id=thread_id, uid=scope.uid, app_id=scope.app_id, for_update=True)
    if turn is None:
        raise ResourceNotFoundError("Turn 不存在")
    existing = await receipt_repo.get_for_scope(uid=scope.uid, app_id=scope.app_id, thread_id=thread_id, idempotency_key=idempotency_key)
    if existing is not None:
        require_receipt_replay(existing, event_type, intent_hash)
        return _accepted(existing)
    waitpoint = turn.waitpoint
    if turn.status != "waiting" or not waitpoint or waitpoint.get("id") != waitpoint_id:
        raise StateConflictError("等待点已变化或已被消费")
    previous = await AgentRunRepository(db).get_run(turn.current_run_id)
    if previous is None or previous.status != "interrupted" or waitpoint.get("run_id") != previous.id:
        raise StateConflictError("等待点与 interrupted Run 不一致")
    resume_value = _validate_resume_response(waitpoint, response)
    binding = await resolve_session_workdir_binding(agent_session=agent_session, uid=scope.uid, db=db)

    run = await create_resume_run(
        db=db,
        agent_session=agent_session,
        turn=turn,
        previous=previous,
        api_key_id=scope.api_key_id,
        response=response,
        metadata={
            "resume": resume_value,
            "waitpoint_id": waitpoint_id,
            "rejected_tool_calls": [
                call["tool_call_id"]
                for call, decision in zip(waitpoint.get("calls", []), resume_value.get("decisions", []))
                if decision["type"] == "reject"
            ],
        },
    )
    run_id = run.id
    receipt = await receipt_repo.create(
        receipt_id=str(uuid.uuid4()),
        idempotency_key=idempotency_key,
        uid=scope.uid,
        app_id=scope.app_id,
        thread_id=thread_id,
        event_type=event_type,
        intent_hash=intent_hash,
        turn_id=turn.id,
        run_id=run_id,
    )

    await notify_user_intervention(db, agent_session, key=receipt.id, action="resume")
    await db.commit()
    await deliver(Dispatch(run_id=run_id, binding=binding))
    return _accepted(receipt)


async def cancel_turn(
    *,
    db: AsyncSession,
    scope: ActorScope,
    thread_id: str,
    turn_id: str | None,
    idempotency_key: str,
    expected_run_id: str | None = None,
    notify_parent: bool = True,
) -> dict:
    """取消指定轮次，保留已产生副作用与待消费输入。"""
    require_idempotency_key(idempotency_key)
    event_type = "agent.session.input.cancel"
    intent_hash = input_intent_hash(event_type, turn_id, expected_run_id)
    receipt_repo = AgentInputReceiptRepository(db)
    existing = await receipt_repo.get_for_scope(uid=scope.uid, app_id=scope.app_id, thread_id=thread_id, idempotency_key=idempotency_key)
    if existing is not None:
        require_receipt_replay(existing, event_type, intent_hash)
        return _accepted(existing)

    agent_session = await require_thread(db=db, scope=scope, thread_id=thread_id, lock=True)
    existing = await receipt_repo.get_for_scope(uid=scope.uid, app_id=scope.app_id, thread_id=thread_id, idempotency_key=idempotency_key)
    if existing is not None:
        require_receipt_replay(existing, event_type, intent_hash)
        return _accepted(existing)
    turn_repo = AgentTurnRepository(db)
    turn = (
        await turn_repo.get_for_scope(turn_id=turn_id, thread_id=thread_id, uid=scope.uid, app_id=scope.app_id, for_update=True)
        if turn_id is not None
        else await turn_repo.lock_active_for_thread(thread_id=thread_id, uid=scope.uid, app_id=scope.app_id)
    )
    if turn is None:
        raise ResourceNotFoundError("Turn 不存在")
    if expected_run_id is not None and turn.current_run_id != expected_run_id:
        raise StateConflictError("当前 Run 已变化")
    if turn.status not in {"running", "waiting", "cancelling", "cancelled"}:
        raise StateConflictError("Turn 已结束，无法取消")

    cancelled_run_ids: list[str] = []
    waiting_cleanup = False
    terminal_changed = False
    if turn.status != "cancelled":
        agent_session.queue_paused = True
        waiting_cleanup = turn.status == "waiting" or (turn.status == "cancelling" and bool(turn.waitpoint))
        if turn.status != "cancelling":
            await turn_repo.set_cancelling(turn)
        run = await AgentRunRepository(db).get_run(turn.current_run_id)
        if run is None:
            raise ValueError("Turn 当前 Run 不存在")
        if run.status in {"pending", "running", "cancel_requested"}:
            run, cancelled_run_ids = await AgentRunRepository(db).request_cancel_run(run_id=run.id, uid=scope.uid)
            if run.status == "cancelled" and not run.runtime_cleanup_pending:
                await turn_repo.set_terminal(turn, status="cancelled")
                terminal_changed = True
        elif run.status == "cancelled":
            if not run.runtime_cleanup_pending:
                await turn_repo.set_terminal(turn, status="cancelled")
                terminal_changed = True
        elif run.status != "interrupted" or not waiting_cleanup:
            raise StateConflictError("当前 Run 已结束，取消目标已变化")

    receipt = await receipt_repo.create(
        receipt_id=str(uuid.uuid4()),
        idempotency_key=idempotency_key,
        uid=scope.uid,
        app_id=scope.app_id,
        thread_id=thread_id,
        event_type=event_type,
        intent_hash=intent_hash,
        turn_id=turn.id,
        run_id=turn.current_run_id,
    )

    if terminal_changed:
        await notify_turn_state(db, run)
    if notify_parent:
        await notify_user_intervention(db, agent_session, key=receipt.id, action="cancel_turn")
    await db.commit()
    if terminal_changed:
        await finish_turn_observation_if_terminal(turn.id)
    if cancelled_run_ids:
        await publish_cancel_signals(cancelled_run_ids)
    if waiting_cleanup:
        try:
            await settle_waiting_cancel(thread_id=thread_id, turn_id=turn.id, uid=scope.uid, app_id=scope.app_id)
        except Exception:
            # 取消已提交；保留 cancelling，由后台重试并报告恢复失败。
            logger.exception("Failed to settle accepted cancellation: %s", turn.id)
    return _accepted(receipt)


async def get_turn_snapshot(*, db: AsyncSession, scope: ActorScope, thread_id: str, turn_id: str) -> dict:
    """按明确 Turn 关系读取执行段、等待点和最终结果。"""
    await require_thread(db=db, scope=scope, thread_id=thread_id)
    turn_repo = AgentTurnRepository(db)
    turn = await turn_repo.get_for_scope(turn_id=turn_id, thread_id=thread_id, uid=scope.uid, app_id=scope.app_id)
    if turn is None:
        raise ResourceNotFoundError("Turn 不存在")
    from yuxi.modules.agents.repositories.input import AgentInputRepository
    from yuxi.modules.agents.services.public_items import serialize_public_run

    runs = await turn_repo.list_runs(turn.id)
    input_ids = await AgentInputRepository(db).input_ids_for_runs([run.id for run in runs])
    result_run = next((run for run in runs if run.id == turn.result_run_id), None)
    current_run = next((run for run in runs if run.id == turn.current_run_id), None)
    output = None
    if result_run is not None and result_run.output_message_id is not None:
        output_message = await db.get(Message, result_run.output_message_id)
        if output_message is None or output_message.run_id != result_run.id or output_message.turn_id != turn.id:
            raise ValueError("Turn 最终结果消息归属不一致")
        from yuxi.modules.agents.services.public_items import serialize_public_items

        output = serialize_public_items(output_message, result_run, turn.result_run_id)
    audits = await turn_repo.list_model_usage_audits(turn.id)
    from yuxi.modules.agents.services.public_resources import turn_core

    started_at = min((run.started_at for run in runs if run.started_at), default=None)
    return {
        "core": turn_core(turn, current_run, started_at=started_at),
        "turn_id": turn.id,
        "thread_id": thread_id,
        "status": turn.status,
        "current_run_id": turn.current_run_id,
        "result_run_id": turn.result_run_id,
        "waitpoint": turn.waitpoint,
        "runs": [serialize_public_run(run, input_ids[run.id]) for run in runs],
        "output": output,
        "usage": _summarize_turn_usage(audits),
        "error": (
            {"type": current_run.error_type, "message": current_run.error_message}
            if turn.status in {"failed", "cancelled"} and current_run is not None
            else None
        ),
    }


def _summarize_turn_usage(audits: list[Message]) -> dict:
    """每个 Model operation 只计一次，并明确缺失或未完成的用量。"""
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    missing = 0
    counted = 0
    for audit in audits:
        usage = audit.usage if isinstance(audit.usage, dict) else {}
        valid = (
            bool(audit.operation_id)
            and audit.execution_status == "completed"
            and all(isinstance(usage.get(key), int) and not isinstance(usage[key], bool) and usage[key] >= 0 for key in totals)
        )
        if not valid:
            missing += 1
            continue
        for key in totals:
            totals[key] += usage[key]
        counted += 1
    return {
        "available": counted > 0,
        "complete": bool(audits) and missing == 0,
        "operations": counted,
        "missing_operations": missing,
        **totals,
    }


async def list_turn_page(
    *,
    db: AsyncSession,
    scope: ActorScope,
    thread_id: str,
    after: str | None,
    limit: int,
    order: str,
) -> dict:
    """批量投影轮次列表，完整输出由单轮资源查询。"""
    await require_thread(db=db, scope=scope, thread_id=thread_id)
    repo = AgentTurnRepository(db)
    try:
        rows = await repo.list_page(thread_id=thread_id, uid=scope.uid, app_id=scope.app_id, after=after, limit=limit, order=order)
    except ValueError as exc:
        raise InvalidOperationError(str(exc)) from exc
    starts = await repo.get_start_times(turn_ids=[turn.id for turn, _run in rows[:limit]], uid=scope.uid, app_id=scope.app_id)
    from yuxi.modules.agents.services.public_resources import turn_core

    data = [
        {
            **turn_core(turn, run, started_at=starts.get(turn.id)),
            "yuxi": {
                "current_run_id": turn.current_run_id,
                "result_run_id": turn.result_run_id,
                "waitpoint": turn.waitpoint,
            },
        }
        for turn, run in rows[:limit]
    ]
    return {
        "object": "list",
        "data": data,
        "first_id": data[0]["id"] if data else None,
        "last_id": data[-1]["id"] if data else None,
        "has_more": len(rows) > limit,
    }


async def settle_waiting_cancel(*, thread_id: str, turn_id: str, uid: str, app_id: str | None) -> bool:
    """清理等待 checkpoint，再把 cancelling Turn 变为 cancelled。"""
    async with pg_manager.get_async_session_context() as db:
        scope = ActorScope(uid=uid, app_id=app_id)
        await require_thread(db=db, scope=scope, thread_id=thread_id)
        turn = await AgentTurnRepository(db).get_for_scope(turn_id=turn_id, thread_id=thread_id, uid=uid, app_id=app_id)
        if turn is None or turn.status != "cancelling" or not turn.waitpoint:
            return False
        run = await AgentRunRepository(db).get_run(turn.current_run_id)
        if run is None or run.status != "interrupted":
            return False
    await _clear_waitpoint_checkpoint(run)

    async with pg_manager.get_async_session_context() as db:
        agent_session = await require_thread(db=db, scope=scope, thread_id=thread_id, lock=True)
        turn = await AgentTurnRepository(db).get_for_scope(turn_id=turn_id, thread_id=thread_id, uid=uid, app_id=app_id, for_update=True)
        if turn is None or turn.status != "cancelling" or turn.current_run_id != run.id:
            return False
        if not agent_session.queue_paused:
            raise ValueError("等待取消未保持队列暂停")
        await AgentTurnRepository(db).set_terminal(turn, status="cancelled")

        await notify_turn_state(db, run)
    await finish_turn_observation_if_terminal(turn_id)
    return True


async def reconcile_cancelling_turns() -> list[str]:
    """补偿清理进程失联后仍占用线程的 cancelling Turn。"""
    async with pg_manager.get_async_session_context() as db:
        candidates = list((await db.execute(select(AgentTurn).where(AgentTurn.status == "cancelling"))).scalars())
    settled = []
    failures = 0
    for candidate in candidates:
        try:
            run_id = candidate.current_run_id
            async with pg_manager.get_async_session_context() as db:
                run = await AgentRunRepository(db).get_run(run_id)
            if run is None:
                continue
            if run.status == "interrupted" and candidate.waitpoint:
                if await settle_waiting_cancel(
                    thread_id=candidate.thread_id,
                    turn_id=candidate.id,
                    uid=candidate.uid,
                    app_id=candidate.app_id,
                ):
                    settled.append(candidate.id)
            elif run.status == "cancelled" and not run.runtime_cleanup_pending:
                async with pg_manager.get_async_session_context() as db:
                    scope = ActorScope(uid=candidate.uid, app_id=candidate.app_id)
                    await require_thread(db=db, scope=scope, thread_id=candidate.thread_id, lock=True)
                    turn = await AgentTurnRepository(db).get_for_scope(
                        turn_id=candidate.id,
                        thread_id=candidate.thread_id,
                        uid=candidate.uid,
                        app_id=candidate.app_id,
                        for_update=True,
                    )
                    if turn is not None and turn.status == "cancelling":
                        await AgentTurnRepository(db).set_terminal(turn, status="cancelled")

                        await notify_turn_state(db, run)
                        settled.append(candidate.id)
                if candidate.id in settled:
                    await finish_turn_observation_if_terminal(candidate.id)
        except Exception:
            failures += 1
            logger.exception("Failed to reconcile cancelling Turn: %s", candidate.id)
    if failures:
        raise RuntimeError(f"cancelling Turn recovery failed for {failures} records")
    return settled


async def _clear_waitpoint_checkpoint(run: AgentRun) -> None:
    """为取消中的 Run 装配原图并清理等待 checkpoint。"""
    from yuxi.modules.agents.repositories.definitions import AgentRepository
    from yuxi.modules.agents.runtime.agent_backends import get_agent_backend
    from yuxi.modules.agents.runtime.checkpoint_cleanup import cancel_waitpoint_checkpoint
    from yuxi.modules.workspace.runtime_paths import runtime_workdir_path
    from yuxi.modules.workspace.services.bindings import resolve_session_workdir_binding

    async with pg_manager.get_async_session_context() as db:
        agent_item = await AgentRepository(db).get_by_slug(run.agent_slug)
        if agent_item is None:
            raise ValueError("等待点 Agent 不存在")
        backend = get_agent_backend(agent_item.backend_id)
        agent_session = await require_thread(
            db=db,
            scope=ActorScope(uid=run.uid, app_id=run.app_id),
            thread_id=run.thread_id,
        )
        binding = await resolve_session_workdir_binding(agent_session=agent_session, uid=run.uid, db=db)

    context = backend.context_schema()
    context.update_config(run.input_payload["context_snapshot"])
    context.update(
        {
            "thread_id": run.thread_id,
            "uid": run.uid,
            "run_id": run.id,
            "worker_id": "waitpoint-cleanup",
            "runtime_scope_id": run.runtime_scope_id,
            "workdir_relative_path": binding.workdir_path,
            "workdir_path": runtime_workdir_path(binding.workdir_path),
        }
    )
    # 持久 Run 与 Thread 的完整归属已验证；清理不取得资源使用授权。
    graph = await backend.get_graph(context=context, checkpoint_only=True)
    config = {"configurable": {"uid": run.uid, "thread_id": run.thread_id}}
    await cancel_waitpoint_checkpoint(graph, config)


def _validate_resume_response(waitpoint: dict, response: dict) -> dict:
    """将结构化回答或审批核对为 LangGraph resume payload。"""
    if not isinstance(response, dict):
        raise InvalidInputError("恢复响应必须是对象")
    if waitpoint["kind"] == "answer":
        if response.get("type") != "answer" or not isinstance(response.get("answers"), list):
            raise InvalidInputError("等待点需要 answer 响应")
        questions = waitpoint.get("questions") or []
        answers = response["answers"]
        expected_ids = [question.get("question_id") for question in questions]
        received_ids = [item.get("question_id") for item in answers if isinstance(item, dict)]
        if len(answers) != len(questions) or received_ids != expected_ids:
            raise InvalidInputError("回答必须覆盖等待点全部问题并保持顺序")
        if any(not isinstance(item.get("answer"), (str, list, dict)) for item in answers):
            raise InvalidInputError("回答内容类型无效")
        return {item["question_id"]: item["answer"] for item in answers}

    if waitpoint["kind"] == "approval":
        if response.get("type") != "approval" or not isinstance(response.get("decisions"), list):
            raise InvalidInputError("等待点需要 approval 响应")
        calls = waitpoint.get("calls") or []
        decisions = response["decisions"]
        received_ids = [item.get("call_id") for item in decisions if isinstance(item, dict)]
        if len(decisions) != len(calls) or received_ids != [call.get("call_id") for call in calls]:
            raise InvalidInputError("审批必须覆盖等待点全部调用并保持顺序")
        if any(item.get("decision") not in call.get("allowed_decisions", []) for item, call in zip(decisions, calls)):
            raise InvalidInputError("审批决定不在允许范围内")
        return {"decisions": [{"type": item["decision"]} for item in decisions]}

    raise StateConflictError("等待点类型无效")


def _accepted(receipt) -> dict:
    """返回首次固定的控制目标。"""
    return {
        "event_id": receipt.id,
        "thread_id": receipt.thread_id,
        "turn_id": receipt.turn_id,
        "run_id": receipt.run_id,
        "status": "accepted",
    }
