import asyncio
import json
import traceback
import uuid
from collections.abc import AsyncIterator

from langchain.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.types import Command

from src import config as conf
from src import knowledge_base
from src.agents import agent_manager
from src.plugins.guard import content_guard
from src.repositories.agent_config_repository import AgentConfigRepository
from src.repositories.conversation_repository import ConversationRepository
from src.storage.postgres.manager import pg_manager
from src.utils.logging_config import logger


async def _get_langgraph_messages(agent_instance, config_dict):
    graph = await agent_instance.get_graph()
    state = await graph.aget_state(config_dict)

    if not state or not state.values:
        logger.warning("No state found in LangGraph")
        return None

    return state.values.get("messages", [])


def extract_agent_state(values: dict) -> dict:
    if not isinstance(values, dict):
        return {}

    def _norm_list(v):
        if v is None:
            return []
        if isinstance(v, (list, tuple)):
            return list(v)
        return [v]

    result = {}
    result["todos"] = _norm_list(values.get("todos"))[:20]
    result["files"] = _norm_list(values.get("files"))[:50]

    return result


async def _get_existing_message_ids(conv_repo: ConversationRepository, thread_id: str) -> set[str]:
    existing_messages = await conv_repo.get_messages_by_thread_id(thread_id)
    return {
        msg.extra_metadata["id"]
        for msg in existing_messages
        if msg.extra_metadata and "id" in msg.extra_metadata and isinstance(msg.extra_metadata["id"], str)
    }


async def _save_ai_message(conv_repo: ConversationRepository, thread_id: str, msg_dict: dict) -> None:
    content = msg_dict.get("content", "")
    tool_calls_data = msg_dict.get("tool_calls", [])

    ai_msg = await conv_repo.add_message_by_thread_id(
        thread_id=thread_id,
        role="assistant",
        content=content,
        message_type="text",
        extra_metadata=msg_dict,
    )

    if ai_msg and tool_calls_data:
        for tc in tool_calls_data:
            await conv_repo.add_tool_call(
                message_id=ai_msg.id,
                tool_name=tc.get("name", "unknown"),
                tool_input=tc.get("args", {}),
                status="pending",
                langgraph_tool_call_id=tc.get("id"),
            )


async def _save_tool_message(conv_repo: ConversationRepository, msg_dict: dict) -> None:
    tool_call_id = msg_dict.get("tool_call_id")
    content = msg_dict.get("content", "")

    if not tool_call_id:
        return

    if isinstance(content, list):
        tool_output = json.dumps(content) if content else ""
    else:
        tool_output = str(content)

    await conv_repo.update_tool_call_output(
        langgraph_tool_call_id=tool_call_id,
        tool_output=tool_output,
        status="success",
    )


async def save_partial_message(
    conv_repo: ConversationRepository,
    thread_id: str,
    full_msg=None,
    error_message: str | None = None,
    error_type: str = "interrupted",
):
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

        return await conv_repo.add_message_by_thread_id(
            thread_id=thread_id,
            role="assistant",
            content=content,
            message_type="text",
            extra_metadata=extra_metadata,
        )

    except Exception as e:
        logger.error(f"Error saving message: {e}")
        logger.error(traceback.format_exc())
        return None


async def save_messages_from_langgraph_state(
    agent_instance,
    thread_id: str,
    conv_repo: ConversationRepository,
    config_dict: dict,
) -> None:
    try:
        messages = await _get_langgraph_messages(agent_instance, config_dict)
        if messages is None:
            return

        existing_ids = await _get_existing_message_ids(conv_repo, thread_id)

        for msg in messages:
            msg_dict = msg.model_dump() if hasattr(msg, "model_dump") else {}
            msg_type = msg_dict.get("type", "unknown")

            if msg_type == "human" or getattr(msg, "id", None) in existing_ids:
                continue

            if msg_type == "ai":
                await _save_ai_message(conv_repo, thread_id, msg_dict)
            elif msg_type == "tool":
                await _save_tool_message(conv_repo, msg_dict)

    except Exception as e:
        logger.error(f"Error saving messages from LangGraph state: {e}")
        logger.error(traceback.format_exc())


async def check_and_handle_interrupts(
    agent,
    langgraph_config: dict,
    make_chunk,
    meta: dict,
    thread_id: str,
) -> AsyncIterator[bytes]:
    try:
        graph = await agent.get_graph()
        state = await graph.aget_state(langgraph_config)

        if not state or not state.values:
            return

        interrupt_info = None

        if hasattr(state, "tasks") and state.tasks:
            for task in state.tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    interrupt_info = task.interrupts[0]
                    break

        if not interrupt_info and state.values:
            interrupt_data = state.values.get("__interrupt__")
            if interrupt_data and isinstance(interrupt_data, list) and len(interrupt_data) > 0:
                interrupt_info = interrupt_data[0]

        if interrupt_info:
            question = "是否批准以下操作？"
            operation = "需要人工审批的操作"
            if isinstance(interrupt_info, dict):
                question = interrupt_info.get("question", question)
                operation = interrupt_info.get("operation", operation)
            elif hasattr(interrupt_info, "question"):
                question = getattr(interrupt_info, "question", question)
                operation = getattr(interrupt_info, "operation", operation)

            meta["interrupt"] = {
                "question": question,
                "operation": operation,
                "thread_id": thread_id,
            }
            yield make_chunk(status="interrupted", message=question, meta=meta)

    except Exception as e:
        logger.error(f"Error checking interrupts: {e}")
        logger.error(traceback.format_exc())


async def stream_agent_chat(
    *,
    agent_id: str,
    query: str,
    config: dict,
    meta: dict,
    image_content: str | None,
    current_user,
    db,
) -> AsyncIterator[bytes]:
    start_time = asyncio.get_event_loop().time()

    def make_chunk(content=None, **kwargs):
        return (
            json.dumps(
                {"request_id": meta.get("request_id"), "response": content, **kwargs}, ensure_ascii=False
            ).encode("utf-8")
            + b"\n"
        )

    if image_content:
        human_message = HumanMessage(
            content=[
                {"type": "text", "text": query},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_content}"}},
            ]
        )
        message_type = "multimodal_image"
    else:
        human_message = HumanMessage(content=query)
        message_type = "text"

    init_msg = {"role": "user", "content": query, "type": "human"}
    if image_content:
        init_msg["message_type"] = "multimodal_image"
        init_msg["image_content"] = image_content
    else:
        init_msg["message_type"] = "text"

    yield make_chunk(status="init", meta=meta, msg=init_msg)

    if conf.enable_content_guard and await content_guard.check(query):
        yield make_chunk(
            status="error", error_type="content_guard_blocked", error_message="输入内容包含敏感词", meta=meta
        )
        return

    try:
        agent = agent_manager.get_agent(agent_id)
    except Exception as e:
        logger.error(f"Error getting agent {agent_id}: {e}, {traceback.format_exc()}")
        yield make_chunk(
            status="error",
            error_type="agent_error",
            error_message=f"智能体 {agent_id} 获取失败: {str(e)}",
            meta=meta,
        )
        return

    messages = [human_message]

    user_id = str(current_user.id)
    department_id = current_user.department_id
    if not department_id:
        yield make_chunk(status="error", error_type="no_department", error_message="当前用户未绑定部门", meta=meta)
        return

    agent_config_id = config.get("agent_config_id")
    config_repo = AgentConfigRepository(db)
    config_item = None
    if agent_config_id is not None:
        try:
            config_item = await config_repo.get_by_id(int(agent_config_id))
        except Exception:
            logger.warning(f"Failed to fetch agent config {agent_config_id}: {traceback.format_exc()}")
            config_item = None
        if config_item is not None and (config_item.department_id != department_id or config_item.agent_id != agent_id):
            config_item = None

    if config_item is None:
        config_item = await config_repo.get_or_create_default(
            department_id=department_id, agent_id=agent_id, created_by=user_id
        )
        agent_config_id = config_item.id

    if not (thread_id := config.get("thread_id")):
        thread_id = str(uuid.uuid4())
        logger.warning(f"No thread_id provided, generated new thread_id: {thread_id}")

    agent_config = (config_item.config_json or {}).get("context", {})
    input_context = {
        "user_id": user_id,
        "thread_id": thread_id,
        "department_id": department_id,
        "agent_config_id": agent_config_id,
        "agent_config": agent_config,
    }

    try:
        conv_repo = ConversationRepository(db)

        try:
            await conv_repo.add_message_by_thread_id(
                thread_id=thread_id,
                role="user",
                content=query,
                message_type=message_type,
                image_content=image_content,
                extra_metadata={"raw_message": human_message.model_dump()},
            )
        except Exception as e:
            logger.error(f"Error saving user message: {e}")

        try:
            assert thread_id, "thread_id is required"
            attachments = await conv_repo.get_attachments_by_thread_id(thread_id)
            input_context["attachments"] = attachments
        except Exception as e:
            logger.error(f"Error loading attachments for thread_id={thread_id}: {e}")
            input_context["attachments"] = []

        # 根据用户权限过滤知识库
        requested_knowledge_names = input_context["agent_config"].get("knowledges")
        logger.info(f"Requesting knowledges: {requested_knowledge_names}")
        if requested_knowledge_names and isinstance(requested_knowledge_names, list) and requested_knowledge_names:
            user_info = {"role": "user", "department_id": department_id}
            accessible_databases = await knowledge_base.get_databases_by_user(user_info)
            accessible_kb_names = {
                db.get("name")
                for db in accessible_databases.get("databases", [])
                if isinstance(db, dict) and db.get("name")
            }
            logger.info(f"Accessible knowledges: {accessible_kb_names}")

            filtered_knowledge_names = [kb for kb in requested_knowledge_names if kb in accessible_kb_names]
            blocked_knowledge_names = [kb for kb in requested_knowledge_names if kb not in accessible_kb_names]
            if blocked_knowledge_names:
                logger.warning(f"用户 {user_id} 无权访问知识库: {blocked_knowledge_names}, 已自动过滤")
            input_context["agent_config"]["knowledges"] = filtered_knowledge_names

        full_msg = None
        accumulated_content = []
        langgraph_config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}
        async for msg, metadata in agent.stream_messages(messages, input_context=input_context):
            if isinstance(msg, AIMessageChunk):
                accumulated_content.append(msg.content)

                content_for_check = "".join(accumulated_content[-10:])
                if conf.enable_content_guard and await content_guard.check_with_keywords(content_for_check):
                    full_msg = AIMessage(content="".join(accumulated_content))
                    await save_partial_message(conv_repo, thread_id, full_msg, "content_guard_blocked")
                    meta["time_cost"] = asyncio.get_event_loop().time() - start_time
                    yield make_chunk(status="interrupted", message="检测到敏感内容，已中断输出", meta=meta)
                    return

                yield make_chunk(content=msg.content, msg=msg.model_dump(), metadata=metadata, status="loading")
            else:
                msg_dict = msg.model_dump()
                yield make_chunk(msg=msg_dict, metadata=metadata, status="loading")

                try:
                    if msg_dict.get("type") == "tool":
                        graph = await agent.get_graph()
                        state = await graph.aget_state(langgraph_config)
                        agent_state = extract_agent_state(getattr(state, "values", {})) if state else {}
                        if agent_state:
                            yield make_chunk(status="agent_state", agent_state=agent_state, meta=meta)
                except Exception as e:
                    logger.error(f"Error processing tool message: {e}")

        if not full_msg and accumulated_content:
            full_msg = AIMessage(content="".join(accumulated_content))

        if conf.enable_content_guard and hasattr(full_msg, "content") and await content_guard.check(full_msg.content):
            await save_partial_message(conv_repo, thread_id, full_msg, "content_guard_blocked")
            meta["time_cost"] = asyncio.get_event_loop().time() - start_time
            yield make_chunk(status="interrupted", message="检测到敏感内容，已中断输出", meta=meta)
            return

        async for chunk in check_and_handle_interrupts(agent, langgraph_config, make_chunk, meta, thread_id):
            yield chunk

        meta["time_cost"] = asyncio.get_event_loop().time() - start_time
        try:
            graph = await agent.get_graph()
            state = await graph.aget_state(langgraph_config)
            agent_state = extract_agent_state(getattr(state, "values", {})) if state else {}
        except Exception:
            agent_state = {}

        if agent_state:
            yield make_chunk(status="agent_state", agent_state=agent_state, meta=meta)

        yield make_chunk(status="finished", meta=meta)

        await save_messages_from_langgraph_state(
            agent_instance=agent,
            thread_id=thread_id,
            conv_repo=conv_repo,
            config_dict=langgraph_config,
        )

    except (asyncio.CancelledError, ConnectionError) as e:
        logger.warning(f"Client disconnected, cancelling stream: {e}")

        async def save_cleanup():
            nonlocal full_msg
            if not full_msg and accumulated_content:
                full_msg = AIMessage(content="".join(accumulated_content))

            async with pg_manager.get_async_session_context() as new_db:
                new_conv_repo = ConversationRepository(new_db)
                await save_partial_message(
                    new_conv_repo,
                    thread_id,
                    full_msg=full_msg,
                    error_message="对话已中断" if not full_msg else None,
                    error_type="interrupted",
                )

        cleanup_task = asyncio.create_task(save_cleanup())
        try:
            await asyncio.shield(cleanup_task)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error(f"Error during cleanup save: {exc}")

        yield make_chunk(status="interrupted", message="对话已中断", meta=meta)

    except Exception as e:
        logger.error(f"Error streaming messages: {e}, {traceback.format_exc()}")

        error_msg = f"Error streaming messages: {e}"
        error_type = "unexpected_error"

        if not full_msg and accumulated_content:
            full_msg = AIMessage(content="".join(accumulated_content))

        async with pg_manager.get_async_session_context() as new_db:
            new_conv_repo = ConversationRepository(new_db)
            await save_partial_message(
                new_conv_repo,
                thread_id,
                full_msg=full_msg,
                error_message=error_msg,
                error_type=error_type,
            )

        yield make_chunk(status="error", error_type=error_type, error_message=error_msg, meta=meta)


async def stream_agent_resume(
    *,
    agent_id: str,
    thread_id: str,
    approved: bool,
    meta: dict,
    config: dict,
    current_user,
    db,
) -> AsyncIterator[bytes]:
    start_time = asyncio.get_event_loop().time()

    def make_resume_chunk(content=None, **kwargs):
        return (
            json.dumps(
                {"request_id": meta.get("request_id"), "response": content, **kwargs}, ensure_ascii=False
            ).encode("utf-8")
            + b"\n"
        )

    try:
        agent = agent_manager.get_agent(agent_id)
    except Exception as e:
        logger.error(f"Error getting agent {agent_id}: {e}, {traceback.format_exc()}")
        yield (
            f'{{"request_id": "{meta.get("request_id")}", "message": '
            f'"Error getting agent {agent_id}: {e}", "status": "error"}}\n'
        )
        return

    init_msg = {"type": "system", "content": f"Resume with approved: {approved}"}
    yield make_resume_chunk(status="init", meta=meta, msg=init_msg)

    resume_command = Command(resume=approved)
    graph = await agent.get_graph()

    user_id = str(current_user.id)
    department_id = current_user.department_id
    if not department_id:
        yield make_resume_chunk(
            status="error", error_type="no_department", error_message="当前用户未绑定部门", meta=meta
        )
        return

    agent_config_id = (config or {}).get("agent_config_id")
    config_repo = AgentConfigRepository(db)
    config_item = None
    if agent_config_id is not None:
        try:
            config_item = await config_repo.get_by_id(int(agent_config_id))
        except Exception:
            logger.warning(f"Failed to fetch agent config {agent_config_id}: {traceback.format_exc()}")
            config_item = None
        if config_item is not None and (config_item.department_id != department_id or config_item.agent_id != agent_id):
            config_item = None

    if config_item is None:
        config_item = await config_repo.get_or_create_default(
            department_id=department_id, agent_id=agent_id, created_by=user_id
        )
        agent_config_id = config_item.id

    input_context = {
        "user_id": user_id,
        "thread_id": thread_id,
        "department_id": department_id,
        "agent_config_id": agent_config_id,
        "agent_config": (config_item.config_json or {}).get("context", config_item.config_json or {}),
    }
    context = agent.context_schema()
    agent_config = input_context.get("agent_config")
    if isinstance(agent_config, dict):
        context.update(agent_config)
    context.update(input_context)

    stream_source = graph.astream(
        resume_command,
        context=context,
        config={"configurable": {"thread_id": thread_id, "user_id": user_id}},
        stream_mode="messages",
    )

    try:
        async for msg, metadata in stream_source:
            msg_dict = msg.model_dump()
            if "id" not in msg_dict:
                msg_dict["id"] = str(uuid.uuid4())

            yield make_resume_chunk(
                content=getattr(msg, "content", ""), msg=msg_dict, metadata=metadata, status="loading"
            )

        langgraph_config = {"configurable": {"thread_id": thread_id, "user_id": str(current_user.id)}}
        async for chunk in check_and_handle_interrupts(agent, langgraph_config, make_resume_chunk, meta, thread_id):
            yield chunk

        meta["time_cost"] = asyncio.get_event_loop().time() - start_time
        yield make_resume_chunk(status="finished", meta=meta)

        conv_repo = ConversationRepository(db)
        await save_messages_from_langgraph_state(
            agent_instance=agent,
            thread_id=thread_id,
            conv_repo=conv_repo,
            config_dict=langgraph_config,
        )

    except (asyncio.CancelledError, ConnectionError) as e:
        logger.warning(f"Client disconnected during resume: {e}")

        async with pg_manager.get_async_session_context() as new_db:
            new_conv_repo = ConversationRepository(new_db)
            await save_partial_message(
                new_conv_repo, thread_id, error_message="对话恢复已中断", error_type="resume_interrupted"
            )

        yield make_resume_chunk(status="interrupted", message="对话恢复已中断", meta=meta)

    except Exception as e:
        logger.error(f"Error during resume: {e}, {traceback.format_exc()}")

        async with pg_manager.get_async_session_context() as new_db:
            new_conv_repo = ConversationRepository(new_db)
            await save_partial_message(
                new_conv_repo, thread_id, error_message=f"Error during resume: {e}", error_type="resume_error"
            )

        yield make_resume_chunk(message=f"Error during resume: {e}", status="error")


async def get_agent_state_view(
    *,
    agent_id: str,
    thread_id: str,
    current_user_id: str,
    db,
) -> dict:
    if not agent_manager.get_agent(agent_id):
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"智能体 {agent_id} 不存在")

    conv_repo = ConversationRepository(db)
    conversation = await conv_repo.get_conversation_by_thread_id(thread_id)
    if not conversation or conversation.user_id != str(current_user_id) or conversation.status == "deleted":
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="对话线程不存在")

    agent = agent_manager.get_agent(agent_id)
    graph = await agent.get_graph()
    langgraph_config = {"configurable": {"user_id": str(current_user_id), "thread_id": thread_id}}
    state = await graph.aget_state(langgraph_config)
    agent_state = extract_agent_state(getattr(state, "values", {})) if state else {}
    return {"agent_state": agent_state}
