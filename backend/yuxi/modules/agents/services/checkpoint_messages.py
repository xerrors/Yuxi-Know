"""在调用者事务中对账 checkpoint 消息、提交 Run/Turn 结算并投递接续 Run。"""

from __future__ import annotations

import asyncio
import json
from typing import Any


from yuxi.infrastructure.observability.logging import logger
from yuxi.modules.agents.tool_results import tool_result_text, TOOL_FAILURE_MESSAGE
from yuxi.modules.agents.models.messages import MODEL_AUDIT_MESSAGE_TYPE, Message
from yuxi.modules.agents.repositories.messages import MessageRepository
from yuxi.modules.agents.repositories.attachments import AttachmentRepository
from yuxi.modules.agents.repositories.input import AgentInputRepository
from yuxi.modules.agents.repositories.model_audit import ModelMessageAuditRepository
from yuxi.modules.agents.repositories.runs import AgentRunRepository
from yuxi.modules.agents.repositories.sessions import SessionRepository
from yuxi.modules.agents.repositories.tool_audit import ToolMessageAuditRepository
from yuxi.modules.agents.repositories.turn import AgentTurnRepository
from yuxi.modules.agents.services.runs import settle_checkpoint
from yuxi.modules.agents.services.scheduler import Dispatch, deliver
from yuxi.shared.datetime import utc_now


async def save_messages_from_langgraph_state(
    state,
    thread_id: str,
    session_repo: SessionRepository,
    *,
    run_id: str,
    turn_id: str,
    worker_id: str,
    trace_info: dict[str, Any] | None = None,
    complete_run: bool = False,
    steer_before_model: bool = False,
    interrupt_run: bool = False,
    interrupt_error_type: str | None = None,
    interrupt_error_message: str | None = None,
    token_usage: dict[str, Any] | None = None,
    waitpoint: dict[str, Any] | None = None,
) -> str | None:
    """在当前 Run lease 下对账 checkpoint 消息并原子提交结果。"""
    if complete_run and interrupt_run:
        raise ValueError("AgentRun 不能同时完成和中断")
    if not worker_id or not turn_id:
        raise ValueError("持久化 AgentRun 输出需要 worker、thread 和 Turn 因果归属")

    run_repo = AgentRunRepository(session_repo.db)
    next_dispatch: Dispatch | None = None
    try:
        await session_repo.db.flush()
        agent_session = await session_repo.lock_session_by_thread_id(thread_id)
        if agent_session is None:
            raise ValueError("AgentRun 的 Thread 不存在")
        persisted_run = await run_repo.get_run(run_id)
        if persisted_run is None:
            raise ValueError("AgentRun 不存在")
        turn = await AgentTurnRepository(session_repo.db).get_for_scope(
            turn_id=turn_id,
            thread_id=thread_id,
            uid=agent_session.uid,
            app_id=agent_session.app_id,
            for_update=True,
        )
        if turn is None or turn.current_run_id != run_id:
            raise ValueError("AgentRun 不是当前 Turn 的执行段")
        pending_steer = None
        if complete_run and turn.status == "running" and not agent_session.queue_paused:
            pending_steer = await AgentInputRepository(session_repo.db).get_pending_steer(
                thread_id=thread_id,
                uid=agent_session.uid,
                app_id=agent_session.app_id,
            )
            if pending_steer is not None and await AttachmentRepository(session_repo.db).has_unready(pending_steer.id):
                pending_steer = None
        continue_after_cancelled_steer = complete_run and steer_before_model and pending_steer is None
        if continue_after_cancelled_steer:
            complete_run = False
        locked_run = await run_repo.lock_output_persistence(
            run_id,
            worker_id=worker_id,
            thread_id=thread_id,
        )
        if locked_run is None:
            raise ValueError(f"AgentRun 不存在: {run_id}")

        existing_ids = await MessageRepository(session_repo.db).get_message_source_ids_by_thread_id(thread_id)
        current_model_audits = await ModelMessageAuditRepository(session_repo.db).list_for_run(run_id)
        model_operation_ids = {message.operation_id for message in current_model_audits if message.operation_id}
        current_tool_audits = await ToolMessageAuditRepository(session_repo.db).list_for_run(run_id)
        tool_audits_by_operation = {message.operation_id: message for message in current_tool_audits if message.operation_id}
        resume_input = await session_repo.db.get(Message, persisted_run.input_message_id) if persisted_run.input_message_id else None
        rejected_calls = set((resume_input.extra_metadata or {}).get("rejected_tool_calls", [])) if resume_input else set()
        state_model_messages: dict[str, dict[str, Any]] = {}
        state_tool_messages: dict[str, dict[str, Any]] = {}
        last_state_ai_id: str | None = None
        last_ai_message = None
        for message in state.values.get("messages", []) or []:
            if hasattr(message, "model_dump"):
                msg_dict = message.model_dump()
            elif isinstance(message, dict):
                msg_dict = dict(message)
            else:
                continue

            msg_type = msg_dict.get("type", "unknown")
            if msg_type == "unknown":
                role = msg_dict.get("role")
                if role in {"assistant", "ai"}:
                    msg_type = "ai"
                elif role in {"user", "human"}:
                    msg_type = "human"
                elif role == "tool":
                    msg_type = "tool"
            msg_id = getattr(message, "id", None) or msg_dict.get("id")
            if msg_type == "ai":
                last_state_ai_id = str(msg_id) if msg_id else None
                if msg_id and str(msg_id) in model_operation_ids:
                    # Checkpoint 包含完整历史；相同来源键只对账最后一条 AIMessage。
                    state_model_messages[str(msg_id)] = msg_dict
                elif not current_model_audits and msg_id not in existing_ids:
                    last_ai_message = await _save_ai_message(
                        MessageRepository(session_repo.db),
                        thread_id,
                        msg_dict,
                        trace_info=trace_info,
                        run_id=run_id,
                        turn_id=turn_id,
                    )
            elif msg_type == "tool":
                tool_call_id = str(msg_dict.get("tool_call_id") or "")
                if tool_call_id in rejected_calls and tool_call_id not in tool_audits_by_operation:
                    audit = await ToolMessageAuditRepository(session_repo.db).record_approval_rejection(
                        run_id=run_id,
                        thread_id=thread_id,
                        worker_id=worker_id,
                        tool_call_id=tool_call_id,
                        content=tool_result_text(msg_dict.get("content")),
                    )
                    from yuxi.modules.agents.repositories.public_items import PublicItemRepository

                    await PublicItemRepository(session_repo.db).save(
                        run_id=run_id,
                        worker_id=worker_id,
                        operation_id=tool_call_id,
                        role="tool",
                        key="output",
                        item={
                            "type": "function_call_output",
                            "call_id": tool_call_id,
                            "output": audit.content,
                            "error": audit.content,
                            "status": "failed",
                        },
                    )
                    tool_audits_by_operation[tool_call_id] = audit
                if tool_call_id in tool_audits_by_operation:
                    state_tool_messages[tool_call_id] = msg_dict

        reconciled_audits: dict[str, Any] = {}
        for operation_id, msg_dict in state_model_messages.items():
            reconciled = await _reconcile_model_audit_message(
                session_repo,
                run_id=run_id,
                operation_id=operation_id,
                msg_dict=msg_dict,
                trace_info=trace_info,
            )
            if reconciled is not None:
                reconciled_audits[operation_id] = reconciled
        last_ai_message = reconciled_audits.get(last_state_ai_id or "") or last_ai_message
        for tool_call_id, msg_dict in state_tool_messages.items():
            audit = tool_audits_by_operation[tool_call_id]
            if interrupt_run or not _should_reconcile_tool_state(audit, msg_dict):
                continue
            await _reconcile_tool_error_from_state(
                session_repo,
                run_id=run_id,
                thread_id=thread_id,
                worker_id=worker_id,
                tool_call_id=tool_call_id,
                msg_dict=msg_dict,
            )
        if current_model_audits and (complete_run or interrupt_run):
            terminal_ai_message = reconciled_audits.get(last_state_ai_id or "")
            if complete_run and pending_steer is None and terminal_ai_message is None:
                raise ValueError("最终 State AIMessage 无法与当前 Run 的 Model lifecycle 事实关联")
            last_ai_message = terminal_ai_message
        if complete_run and pending_steer is None and last_ai_message is None:
            raise ValueError("最终 checkpoint 缺少当前 Run 的 AI 输出")
        if last_ai_message is not None:
            has_tool_calls = bool((last_ai_message.extra_metadata or {}).get("tool_calls"))
            should_publish = (
                last_ai_message.message_type != MODEL_AUDIT_MESSAGE_TYPE or complete_run or (interrupt_run and not has_tool_calls)
            )
            if should_publish:
                await MessageRepository(session_repo.db).publish_assistant_output(last_ai_message)
            await run_repo.set_output_message(run_id, last_ai_message.id, worker_id=worker_id)

        terminal_status = "completed" if complete_run else "interrupted" if interrupt_run else None
        if terminal_status:
            if interrupt_run and waitpoint and waitpoint["kind"] == "approval":
                waitpoint = _bind_approval_calls(waitpoint, last_ai_message)
            settlement = await settle_checkpoint(
                db=session_repo.db,
                run=locked_run,
                worker_id=worker_id,
                status=terminal_status,
                waitpoint=waitpoint,
                error_type=interrupt_error_type if interrupt_run else None,
                error_message=interrupt_error_message if interrupt_run else None,
                token_usage=token_usage or {"available": False},
            )
            if not settlement.changed:
                raise ValueError(f"AgentRun 输出已写入但 {terminal_status} 终态未能在同一事务提交")
            terminal_status = settlement.status
            next_dispatch = settlement.next_dispatch
        await session_repo.db.commit()
        if next_dispatch:
            await deliver(next_dispatch)
        return "running" if continue_after_cancelled_steer else terminal_status
    except asyncio.CancelledError:
        await session_repo.db.rollback()
        raise
    except Exception:
        await session_repo.db.rollback()
        raise


async def save_partial_message(
    session_repo: SessionRepository,
    thread_id: str,
    *,
    run_id: str,
    turn_id: str,
    worker_id: str,
    full_msg=None,
    error_message: str | None = None,
    error_type: str = "interrupted",
    trace_info: dict[str, Any] | None = None,
):
    """在同一事务内保存错误输出并结束当前 Run 与 Turn。"""
    try:
        extra_metadata = {
            "error_type": error_type,
            "is_error": True,
            "error_message": error_message or f"发生错误: {error_type}",
        }
        if full_msg:
            msg_dict = full_msg.model_dump() if hasattr(full_msg, "model_dump") else {}
            content = full_msg.content if hasattr(full_msg, "content") else str(full_msg)
            extra_metadata = msg_dict | extra_metadata
        else:
            content = ""

        if trace_info:
            extra_metadata.update(trace_info)

        if not worker_id or not turn_id:
            raise ValueError("持久化 AgentRun 部分输出需要当前 worker 和 Turn")
        run_repo = AgentRunRepository(session_repo.db)
        agent_session = await session_repo.lock_session_by_thread_id(thread_id)
        if agent_session is None:
            raise ValueError("AgentRun 的 Thread 不存在")
        persisted_run = await run_repo.get_run(run_id)
        if persisted_run is None:
            raise ValueError("AgentRun 不存在")
        turn = await AgentTurnRepository(session_repo.db).get_for_scope(
            turn_id=turn_id,
            thread_id=thread_id,
            uid=agent_session.uid,
            app_id=agent_session.app_id,
            for_update=True,
        )
        if turn is None or turn.current_run_id != run_id:
            raise ValueError("AgentRun 不是当前 Turn 的执行段")
        locked_run = await run_repo.lock_output_persistence(
            run_id,
            worker_id=worker_id,
            thread_id=thread_id,
        )
        if locked_run is None:
            raise ValueError(f"AgentRun 不存在: {run_id}")

        message = await MessageRepository(session_repo.db).add_message_by_thread_id(
            thread_id=thread_id,
            role="assistant",
            content=content,
            message_type="text",
            extra_metadata=extra_metadata,
            run_id=run_id,
            turn_id=turn_id,
        )
        if message is None:
            raise ValueError("AgentRun 错误输出消息未能持久化")
        await run_repo.set_output_message(run_id, message.id, worker_id=worker_id)
        settlement = await settle_checkpoint(
            db=session_repo.db,
            run=locked_run,
            worker_id=worker_id,
            status="failed",
            error_type=error_type,
            error_message=error_message,
            token_usage={"available": False},
        )
        if not settlement.changed:
            raise ValueError("AgentRun 错误输出与失败终态未能在同一事务提交")
        await session_repo.db.commit()
        return message

    except Exception as e:
        await session_repo.db.rollback()
        logger.exception(f"Error saving message: {e}")
        return None


def _ai_message_content_and_tool_calls(msg_dict: dict) -> tuple[str, list[dict]]:
    """提取 AIMessage 可展示正文和兼容 ToolCall 投影。"""
    content = msg_dict.get("content", "")
    tool_calls_data = msg_dict.get("tool_calls") or []
    if isinstance(content, list):
        if not tool_calls_data:
            tool_calls_data = [
                {"id": item.get("id"), "name": item.get("name"), "args": item.get("args") or {}}
                for item in content
                if isinstance(item, dict) and item.get("type") == "tool_call"
            ]
        content = "\n".join(item.get("text", "") for item in content if isinstance(item, dict) and isinstance(item.get("text"), str))
    elif not isinstance(content, str):
        content = str(content)
    return content, list(tool_calls_data)


async def _project_ai_tool_calls(
    repository: MessageRepository,
    *,
    message_id: int,
    tool_calls_data: list[dict],
) -> None:
    """从 AIMessage 单向投影阶段二仍需兼容的 ToolCall。"""
    for tool_call in tool_calls_data:
        await repository.add_tool_call(
            message_id=message_id,
            tool_name=tool_call.get("name") or "unknown",
            tool_input=tool_call.get("args", {}),
            status="pending",
            langgraph_tool_call_id=tool_call.get("id"),
        )


async def _save_ai_message(
    repository: MessageRepository,
    thread_id: str,
    msg_dict: dict,
    *,
    trace_info: dict[str, Any] | None,
    run_id: str,
    turn_id: str,
):
    """保存当前 Run 未进入 Model audit 的可见 AI 输出。"""
    content, _ = _ai_message_content_and_tool_calls(msg_dict)
    extra_metadata = dict(msg_dict)
    if trace_info:
        extra_metadata.update(trace_info)

    ai_msg = await repository.add_message_by_thread_id(
        thread_id=thread_id,
        role="assistant",
        content=content,
        message_type="text",
        extra_metadata=extra_metadata,
        run_id=run_id,
        turn_id=turn_id,
    )
    return ai_msg


async def _reconcile_model_audit_message(
    session_repo: SessionRepository,
    *,
    run_id: str,
    operation_id: str,
    msg_dict: dict,
    trace_info: dict[str, Any] | None,
) -> Any | None:
    """用终态 State 补全同一稳定来源键的 Model 审计消息。"""
    message = await ModelMessageAuditRepository(session_repo.db).get(
        run_id=run_id,
        operation_id=operation_id,
    )
    if message is None:
        return None

    content, tool_calls_data = _ai_message_content_and_tool_calls(msg_dict)
    metadata = {**dict(message.extra_metadata or {}), **dict(msg_dict)}
    if trace_info:
        metadata.update(trace_info)
    metadata["state_reconciled"] = True
    message.content = content
    message.extra_metadata = metadata
    if message.execution_status == "running":
        message.execution_status = "completed"
        message.finished_at = utc_now()
        metadata["finished_by_reconcile"] = True
    await session_repo.db.flush()
    if tool_calls_data:
        await _project_ai_tool_calls(
            MessageRepository(session_repo.db),
            message_id=message.id,
            tool_calls_data=tool_calls_data,
        )
    return message


async def _reconcile_tool_error_from_state(
    session_repo: SessionRepository,
    *,
    run_id: str,
    thread_id: str,
    worker_id: str | None,
    tool_call_id: str,
    msg_dict: dict[str, Any],
) -> None:
    """用终态 State 补全等待 Run 裁决的 Tool error。"""
    if not worker_id:
        raise ValueError("ToolMessage 对账需要当前 worker 所有权")
    content = tool_result_text(msg_dict.get("content"))
    await ToolMessageAuditRepository(session_repo.db).fail(
        run_id=run_id,
        thread_id=thread_id,
        worker_id=worker_id,
        tool_call_id=tool_call_id,
        output=json.loads(json.dumps(msg_dict, ensure_ascii=False, default=str)),
        content=content,
        error_message=content or TOOL_FAILURE_MESSAGE,
        finished_at=utc_now(),
        duration_ms=None,
        finished_sequence=None,
    )


def _should_reconcile_tool_state(audit: Any, tool_message: dict[str, Any]) -> bool:
    """只用终态 State 补全仍等待 Run 裁决的 Tool error。"""
    if audit.execution_status != "running":
        return False
    metadata = audit.extra_metadata if isinstance(audit.extra_metadata, dict) else {}
    return metadata.get("awaiting_run_terminal") is True and tool_message.get("status") == "error"


def _bind_approval_calls(waitpoint: dict, model_message: Message | None) -> dict:
    """在等待事务中把有序审批动作绑定到当前模型声明，禁止关联历史调用。"""
    declarations = list((model_message.extra_metadata or {}).get("tool_calls", [])) if model_message else []
    calls = []
    for action in waitpoint["calls"]:
        position = next(
            (index for index, call in enumerate(declarations) if call["name"] == action["name"] and call["args"] == action["args"]),
            None,
        )
        if position is None:
            raise ValueError("审批等待点缺少当前模型的工具声明")
        declaration = declarations.pop(position)
        calls.append({**action, "tool_call_id": declaration["id"]})
    return {**waitpoint, "calls": calls}
