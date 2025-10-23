import asyncio
import json
import traceback
import uuid
import yaml
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain.messages import AIMessageChunk, HumanMessage
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.storage.db.models import User, MessageFeedback, Message, Conversation
from src.storage.conversation import ConversationManager
from src.storage.db.manager import db_manager
from server.routers.auth_router import get_admin_user
from server.utils.auth_middleware import get_db, get_required_user
from src import executor
from src import config as conf
from src.agents import agent_manager
from src.agents.common.tools import gen_tool_info, get_buildin_tools
from src.models import select_model
from src.plugins.guard import content_guard
from src.utils.logging_config import logger

chat = APIRouter(prefix="/chat", tags=["chat"])

# =============================================================================
# > === 智能体管理分组 ===
# =============================================================================


@chat.get("/default_agent")
async def get_default_agent(current_user: User = Depends(get_required_user)):
    """获取默认智能体ID（需要登录）"""
    try:
        default_agent_id = conf.default_agent_id
        # 如果没有设置默认智能体，尝试获取第一个可用的智能体
        if not default_agent_id:
            agents = await agent_manager.get_agents_info()
            if agents:
                default_agent_id = agents[0].get("id", "")

        return {"default_agent_id": default_agent_id}
    except Exception as e:
        logger.error(f"获取默认智能体出错: {e}")
        raise HTTPException(status_code=500, detail=f"获取默认智能体出错: {str(e)}")


@chat.post("/set_default_agent")
async def set_default_agent(request_data: dict = Body(...), current_user=Depends(get_admin_user)):
    """设置默认智能体ID (仅管理员)"""
    try:
        agent_id = request_data.get("agent_id")
        if not agent_id:
            raise HTTPException(status_code=422, detail="缺少必需的 agent_id 字段")

        # 验证智能体是否存在
        agents = await agent_manager.get_agents_info()
        agent_ids = [agent.get("id", "") for agent in agents]

        if agent_id not in agent_ids:
            raise HTTPException(status_code=404, detail=f"智能体 {agent_id} 不存在")

        # 设置默认智能体ID
        conf.default_agent_id = agent_id
        # 保存配置
        conf.save()

        return {"success": True, "default_agent_id": agent_id}
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"设置默认智能体出错: {e}")
        raise HTTPException(status_code=500, detail=f"设置默认智能体出错: {str(e)}")


# =============================================================================
# > === 对话分组 ===
# =============================================================================


@chat.post("/call")
async def call(query: str = Body(...), meta: dict = Body(None), current_user: User = Depends(get_required_user)):
    """调用模型进行简单问答（需要登录）"""
    meta = meta or {}
    model = select_model(
        model_provider=meta.get("model_provider"),
        model_name=meta.get("model_name"),
        model_spec=meta.get("model_spec") or meta.get("model"),
    )

    async def call_async(query):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, model.call, query)

    response = await call_async(query)
    logger.debug({"query": query, "response": response.content})

    return {"response": response.content}


@chat.get("/agent")
async def get_agent(current_user: User = Depends(get_required_user)):
    """获取所有可用智能体（需要登录）"""
    agents = await agent_manager.get_agents_info()
    # logger.debug(f"agents: {agents}")
    metadata = {}
    if Path("src/config/static/agents_meta.yaml").exists():
        with open("src/config/static/agents_meta.yaml") as f:
            metadata = yaml.safe_load(f)
    return {"agents": agents, "metadata": metadata}

#TODO:[未完成]这个thread_id在前端是直接生成的1234，最好传入thread_id时做校验只允许uuid4
@chat.post("/agent/{agent_id}")
async def chat_agent(
    agent_id: str,
    query: str = Body(...),
    config: dict = Body({}),
    meta: dict = Body({}),
    current_user: User = Depends(get_required_user),
    db: Session = Depends(get_db),
):
    """使用特定智能体进行对话（需要登录）"""
    start_time = asyncio.get_event_loop().time()

    logger.info(f"agent_id: {agent_id}, query: {query}, config: {config}, meta: {meta}")

    meta.update(
        {
            "query": query,
            "agent_id": agent_id,
            "server_model_name": config.get("model", agent_id),
            "thread_id": config.get("thread_id"),
            "user_id": current_user.id,
        }
    )

    # 将meta和thread_id整合到config中
    def make_chunk(content=None, **kwargs):
        return (
            json.dumps(
                {"request_id": meta.get("request_id"), "response": content, **kwargs}, ensure_ascii=False
            ).encode("utf-8")
            + b"\n"
        )

    async def save_messages_from_langgraph_state(
        agent_instance,
        thread_id,
        conv_mgr,
        config_dict,
    ):
        """
        从 LangGraph state 中读取完整消息并保存到数据库
        这样可以获得完整的 tool_calls 参数
        """
        try:
            graph = await agent_instance.get_graph()
            state = await graph.aget_state(config_dict)

            if not state or not state.values:
                logger.warning("No state found in LangGraph")
                return

            messages = state.values.get("messages", [])
            logger.debug(f"Retrieved {len(messages)} messages from LangGraph state")

            # 获取已保存的消息数量，避免重复保存
            existing_messages = conv_mgr.get_messages_by_thread_id(thread_id)
            existing_ids = {
                msg.extra_metadata["id"]
                for msg in existing_messages
                if msg.extra_metadata and "id" in msg.extra_metadata
            }

            for msg in messages:
                msg_dict = msg.model_dump() if hasattr(msg, "model_dump") else {}
                msg_type = msg_dict.get("type", "unknown")

                if msg_type == "human" or msg.id in existing_ids:
                    continue

                elif msg_type == "ai":
                    # AI 消息
                    content = msg_dict.get("content", "")
                    tool_calls_data = msg_dict.get("tool_calls", [])

                    # 格式清洗
                    if finish_reason := msg_dict.get("response_metadata", {}).get("finish_reason"):
                        if "tool_call" in finish_reason and len(finish_reason) > len("tool_call"):
                            model_name = msg_dict.get("response_metadata", {}).get("model_name", "")
                            repeat_count = len(finish_reason) // len("tool_call")
                            msg_dict["response_metadata"]["finish_reason"] = "tool_call"
                            msg_dict["response_metadata"]["model_name"] = model_name[: len(model_name) // repeat_count]

                    # 保存 AI 消息
                    ai_msg = conv_mgr.add_message_by_thread_id(
                        thread_id=thread_id,
                        role="assistant",
                        content=content,
                        message_type="text",
                        extra_metadata=msg_dict,  # 保存原始 model_dump
                    )

                    # 保存 tool_calls（如果有）- 使用 LangGraph 的 tool_call_id
                    if tool_calls_data:
                        logger.debug(f"Saving {len(tool_calls_data)} tool calls from AI message")
                        for tc in tool_calls_data:
                            conv_mgr.add_tool_call(
                                message_id=ai_msg.id,
                                tool_name=tc.get("name", "unknown"),
                                tool_input=tc.get("args", {}),  # 完整的参数
                                status="pending",  # 工具还未执行
                                langgraph_tool_call_id=tc.get("id"),  # 保存 LangGraph tool_call_id
                            )

                    logger.debug(f"Saved AI message {ai_msg.id} with {len(tool_calls_data)} tool calls")

                elif msg_type == "tool":
                    # 工具执行结果消息 - 使用 tool_call_id 精确匹配
                    tool_call_id = msg_dict.get("tool_call_id")
                    content = msg_dict.get("content", "")
                    name = msg_dict.get("name", "")

                    if tool_call_id:
                        # 确保tool_output是字符串类型，避免SQLite不支持列表类型
                        if isinstance(content, list):
                            tool_output = json.dumps(content) if content else ""
                        else:
                            tool_output = str(content)

                        # 通过 LangGraph tool_call_id 精确匹配并更新
                        updated_tc = conv_mgr.update_tool_call_output(
                            langgraph_tool_call_id=tool_call_id,
                            tool_output=tool_output,
                            status="success",
                        )
                        if updated_tc:
                            logger.debug(f"Updated tool_call {tool_call_id} ({name}) with output")
                        else:
                            logger.warning(f"Tool call {tool_call_id} not found for update")

                else:
                    logger.warning(f"Unknown message type: {msg_type}, skipping")
                    continue

                logger.debug(f"Processed message type={msg_type}")

            logger.info("Saved messages from LangGraph state")

        except Exception as e:
            logger.error(f"Error saving messages from LangGraph state: {e}")
            logger.error(traceback.format_exc())

    #TODO:[功能建议]针对需要人工审批后再执行的工具，可以使用langgraph的interrupt方法中断对话，等待用户输入后再使用command跳转回去
    async def stream_messages():
        # 代表服务端已经收到了请求
        yield make_chunk(status="init", meta=meta, msg=HumanMessage(content=query).model_dump())

        # Input guard
        if conf.enable_content_guard and await content_guard.check(query):
            yield make_chunk(status="error", message="输入内容包含敏感词", meta=meta)
            return

        try:
            agent = agent_manager.get_agent(agent_id)
        except Exception as e:
            logger.error(f"Error getting agent {agent_id}: {e}, {traceback.format_exc()}")
            yield make_chunk(message=f"Error getting agent {agent_id}: {e}", status="error")
            return

        messages = [{"role": "user", "content": query}]

        # 构造运行时配置，如果没有thread_id则生成一个
        user_id = str(current_user.id)
        thread_id = config.get("thread_id")
        input_context = {"user_id": user_id, "thread_id": thread_id}

        if not thread_id:
            thread_id = str(uuid.uuid4())
            logger.warning(f"No thread_id provided, generated new thread_id: {thread_id}")

        # Initialize conversation manager
        conv_manager = ConversationManager(db)

        # Save user message
        try:
            conv_manager.add_message_by_thread_id(
                thread_id=thread_id,
                role="user",
                content=query,
                message_type="text",
                extra_metadata={"raw_message": HumanMessage(content=query).model_dump()},
            )
        except Exception as e:
            logger.error(f"Error saving user message: {e}")

        try:
            full_msg = None
            async for msg, metadata in agent.stream_messages(messages, input_context=input_context):
                if isinstance(msg, AIMessageChunk):
                    full_msg = msg if not full_msg else full_msg + msg
                    if conf.enable_content_guard and await content_guard.check_with_keywords(full_msg.content[-20:]):
                        logger.warning("Sensitive content detected in stream")
                        yield make_chunk(message="检测到敏感内容，已中断输出", status="error")
                        return

                    yield make_chunk(content=msg.content, msg=msg.model_dump(), metadata=metadata, status="loading")

                else:
                    yield make_chunk(msg=msg.model_dump(), metadata=metadata, status="loading")

            if (
                conf.enable_content_guard
                and hasattr(full_msg, "content")
                and await content_guard.check(full_msg.content)
            ):
                logger.warning("Sensitive content detected in final message")
                yield make_chunk(message="检测到敏感内容，已中断输出", status="error")
                return

            meta["time_cost"] = asyncio.get_event_loop().time() - start_time
            yield make_chunk(status="finished", meta=meta)

            # After streaming finished, save all messages from LangGraph state
            langgraph_config = {"configurable": input_context}
            await save_messages_from_langgraph_state(
                agent_instance=agent,
                thread_id=thread_id,
                conv_mgr=conv_manager,
                config_dict=langgraph_config,
            )

        except (asyncio.CancelledError, ConnectionError) as e:
            # 客户端主动中断连接，尝试保存已生成的部分内容
            logger.warning(f"Client disconnected, cancelling stream: {e}")
            if full_msg:
                # 创建新的 db session，因为原 session 可能已关闭
                new_db = db_manager.get_session()
                try:
                    new_conv_manager = ConversationManager(new_db)
                    msg_dict = full_msg.model_dump() if hasattr(full_msg, "model_dump") else {}
                    content = full_msg.content if hasattr(full_msg, "content") else str(full_msg)
                    new_conv_manager.add_message_by_thread_id(
                        thread_id=thread_id,
                        role="assistant",
                        content=content,
                        message_type="text",
                        extra_metadata=msg_dict | {"error_type": "interrupted"},  # 保存原始 model_dump
                    )
                finally:
                    new_db.close()

            # 通知前端中断（可能发送不到，但用于一致性）
            yield make_chunk(status="interrupted", message="对话已中断", meta=meta)

        except Exception as e:
            logger.error(f"Error streaming messages: {e}, {traceback.format_exc()}")
            if full_msg:
                # 创建新的 db session，因为原 session 可能已关闭
                new_db = db_manager.get_session()
                try:
                    new_conv_manager = ConversationManager(new_db)
                    msg_dict = full_msg.model_dump() if hasattr(full_msg, "model_dump") else {}
                    content = full_msg.content if hasattr(full_msg, "content") else str(full_msg)
                    new_conv_manager.add_message_by_thread_id(
                        thread_id=thread_id,
                        role="assistant",
                        content=content,
                        message_type="text",
                        extra_metadata=msg_dict | {"error_type": "unexpect"},  # 保存原始 model_dump
                    )
                finally:
                    new_db.close()
            yield make_chunk(message=f"Error streaming messages: {e}", status="error")

    return StreamingResponse(stream_messages(), media_type="application/json")


# =============================================================================
# > === 模型管理分组 ===
# =============================================================================


@chat.get("/models")
async def get_chat_models(model_provider: str, current_user: User = Depends(get_admin_user)):
    """获取指定模型提供商的模型列表（需要登录）"""
    model = select_model(model_provider=model_provider)
    return {"models": model.get_models()}


@chat.post("/models/update")
async def update_chat_models(model_provider: str, model_names: list[str], current_user=Depends(get_admin_user)):
    """更新指定模型提供商的模型列表 (仅管理员)"""
    conf.model_names[model_provider].models = model_names
    conf._save_models_to_file(model_provider)
    return {"models": conf.model_names[model_provider].models}


@chat.get("/tools")
async def get_tools(agent_id: str, current_user: User = Depends(get_required_user)):
    """获取所有可用工具（需要登录）"""
    # 获取Agent实例和配置类
    if not (agent := agent_manager.get_agent(agent_id)):
        raise HTTPException(status_code=404, detail=f"智能体 {agent_id} 不存在")

    if hasattr(agent, "get_tools"):
        tools = agent.get_tools()
    else:
        tools = get_buildin_tools()

    tools_info = gen_tool_info(tools)
    return {"tools": {tool["id"]: tool for tool in tools_info}}


@chat.post("/agent/{agent_id}/config")
async def save_agent_config(agent_id: str, config: dict = Body(...), current_user: User = Depends(get_required_user)):
    """保存智能体配置到YAML文件（需要登录）"""
    try:
        # 获取Agent实例和配置类
        if not (agent := agent_manager.get_agent(agent_id)):
            raise HTTPException(status_code=404, detail=f"智能体 {agent_id} 不存在")

        # 使用配置类的save_to_file方法保存配置
        result = agent.context_schema.save_to_file(config, agent.module_name)

        if result:
            return {"success": True, "message": f"智能体 {agent.name} 配置已保存"}
        else:
            raise HTTPException(status_code=500, detail="保存智能体配置失败")

    except Exception as e:
        logger.error(f"保存智能体配置出错: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"保存智能体配置出错: {str(e)}")


@chat.get("/agent/{agent_id}/history")
async def get_agent_history(
    agent_id: str, thread_id: str, current_user: User = Depends(get_required_user), db: Session = Depends(get_db)
):
    """获取智能体历史消息（需要登录）- NEW STORAGE ONLY"""
    try:
        # 获取Agent实例验证
        if not agent_manager.get_agent(agent_id):
            raise HTTPException(status_code=404, detail=f"智能体 {agent_id} 不存在")

        # Use new storage system ONLY
        conv_manager = ConversationManager(db)
        messages = conv_manager.get_messages_by_thread_id(thread_id)

        # Convert to frontend-compatible format
        history = []
        for msg in messages:
            # Map role to type that frontend expects
            role_type_map = {"user": "human", "assistant": "ai", "tool": "tool", "system": "system"}

            msg_dict = {
                "id": msg.id,  # Include message ID for feedback
                "type": role_type_map.get(msg.role, msg.role),  # human/ai/tool/system
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "error_type": msg.extra_metadata.get("error_type") if msg.extra_metadata else None,
            }

            # Add tool calls if present (for AI messages)
            if msg.tool_calls and len(msg.tool_calls) > 0:
                msg_dict["tool_calls"] = [
                    {
                        "id": str(tc.id),
                        "name": tc.tool_name,
                        "function": {"name": tc.tool_name},  # Frontend compatibility
                        "args": tc.tool_input or {},
                        "tool_call_result": {"content": tc.tool_output} if tc.tool_output else None,
                        "status": tc.status,
                    }
                    for tc in msg.tool_calls
                ]

            history.append(msg_dict)

        logger.info(f"Loaded {len(history)} messages from new storage for thread {thread_id}")
        return {"history": history}

    except Exception as e:
        logger.error(f"获取智能体历史消息出错: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取智能体历史消息出错: {str(e)}")


@chat.get("/agent/{agent_id}/config")
async def get_agent_config(agent_id: str, current_user: User = Depends(get_required_user)):
    """从YAML文件加载智能体配置（需要登录）"""
    try:
        # 检查智能体是否存在
        if not (agent := agent_manager.get_agent(agent_id)):
            raise HTTPException(status_code=404, detail=f"智能体 {agent_id} 不存在")

        config = await agent.get_config()
        logger.debug(f"config: {config}, ContextClass: {agent.context_schema=}")
        return {"success": True, "config": config}

    except Exception as e:
        logger.error(f"加载智能体配置出错: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"加载智能体配置出错: {str(e)}")


# ==================== 线程管理 API ====================


class ThreadCreate(BaseModel):
    title: str | None = None
    agent_id: str
    metadata: dict | None = None


class ThreadResponse(BaseModel):
    id: str
    user_id: str
    agent_id: str
    title: str | None = None
    created_at: str
    updated_at: str


# =============================================================================
# > === 会话管理分组 ===
# =============================================================================


@chat.post("/thread", response_model=ThreadResponse)
async def create_thread(
    thread: ThreadCreate, db: Session = Depends(get_db), current_user: User = Depends(get_required_user)
):
    """创建新对话线程 (使用新存储系统)"""
    thread_id = str(uuid.uuid4())
    logger.debug(f"thread.agent_id: {thread.agent_id}")

    # Create conversation using new storage system
    conv_manager = ConversationManager(db)
    conversation = conv_manager.create_conversation(
        user_id=str(current_user.id),
        agent_id=thread.agent_id,
        title=thread.title or "新的对话",
        thread_id=thread_id,
        metadata=thread.metadata,
    )

    logger.info(f"Created conversation with thread_id: {thread_id}")

    return {
        "id": conversation.thread_id,
        "user_id": conversation.user_id,
        "agent_id": conversation.agent_id,
        "title": conversation.title,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
    }


@chat.get("/threads", response_model=list[ThreadResponse])
async def list_threads(agent_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_required_user)):
    """获取用户的所有对话线程 (使用新存储系统)"""
    assert agent_id, "agent_id 不能为空"

    logger.debug(f"agent_id: {agent_id}")

    # Use new storage system
    conv_manager = ConversationManager(db)
    conversations = conv_manager.list_conversations(
        user_id=str(current_user.id),
        agent_id=agent_id,
        status="active",
    )

    return [
        {
            "id": conv.thread_id,
            "user_id": conv.user_id,
            "agent_id": conv.agent_id,
            "title": conv.title,
            "created_at": conv.created_at.isoformat(),
            "updated_at": conv.updated_at.isoformat(),
        }
        for conv in conversations
    ]


@chat.delete("/thread/{thread_id}")
async def delete_thread(thread_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_required_user)):
    """删除对话线程 (使用新存储系统)"""
    # Use new storage system
    conv_manager = ConversationManager(db)
    conversation = conv_manager.get_conversation_by_thread_id(thread_id)

    if not conversation or conversation.user_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="对话线程不存在")

    # Soft delete
    success = conv_manager.delete_conversation(thread_id, soft_delete=True)

    if not success:
        raise HTTPException(status_code=500, detail="删除失败")

    return {"message": "删除成功"}


class ThreadUpdate(BaseModel):
    title: str | None = None


@chat.put("/thread/{thread_id}", response_model=ThreadResponse)
async def update_thread(
    thread_id: str,
    thread_update: ThreadUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_required_user),
):
    """更新对话线程信息 (使用新存储系统)"""
    # Use new storage system
    conv_manager = ConversationManager(db)
    conversation = conv_manager.get_conversation_by_thread_id(thread_id)

    if not conversation or conversation.user_id != str(current_user.id) or conversation.status == "deleted":
        raise HTTPException(status_code=404, detail="对话线程不存在")

    # Update conversation
    updated_conv = conv_manager.update_conversation(
        thread_id=thread_id,
        title=thread_update.title,
    )

    if not updated_conv:
        raise HTTPException(status_code=500, detail="更新失败")

    return {
        "id": updated_conv.thread_id,
        "user_id": updated_conv.user_id,
        "agent_id": updated_conv.agent_id,
        "title": updated_conv.title,
        "created_at": updated_conv.created_at.isoformat(),
        "updated_at": updated_conv.updated_at.isoformat(),
    }


# =============================================================================
# > === 消息反馈分组 ===
# =============================================================================


class MessageFeedbackRequest(BaseModel):
    rating: str  # 'like' or 'dislike'
    reason: str | None = None  # Optional reason for dislike


class MessageFeedbackResponse(BaseModel):
    id: int
    message_id: int
    rating: str
    reason: str | None
    created_at: str


@chat.post("/message/{message_id}/feedback", response_model=MessageFeedbackResponse)
async def submit_message_feedback(
    message_id: int,
    feedback_data: MessageFeedbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_required_user),
):
    """Submit user feedback for a specific message"""
    try:
        # Validate rating
        if feedback_data.rating not in ["like", "dislike"]:
            raise HTTPException(status_code=422, detail="Rating must be 'like' or 'dislike'")

        # Verify message exists and get conversation to check permissions
        message = db.query(Message).filter_by(id=message_id).first()

        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        # Verify user has access to this message (through conversation)
        conversation = db.query(Conversation).filter_by(id=message.conversation_id).first()
        if not conversation or conversation.user_id != str(current_user.id):
            raise HTTPException(status_code=403, detail="Access denied")

        # Check if feedback already exists (user can only submit once)
        existing_feedback = (
            db.query(MessageFeedback).filter_by(message_id=message_id, user_id=str(current_user.id)).first()
        )

        if existing_feedback:
            raise HTTPException(status_code=409, detail="Feedback already submitted for this message")

        # Create new feedback
        new_feedback = MessageFeedback(
            message_id=message_id,
            user_id=str(current_user.id),
            rating=feedback_data.rating,
            reason=feedback_data.reason,
        )

        db.add(new_feedback)
        db.commit()
        db.refresh(new_feedback)

        logger.info(f"User {current_user.id} submitted {feedback_data.rating} feedback for message {message_id}")

        return MessageFeedbackResponse(
            id=new_feedback.id,
            message_id=new_feedback.message_id,
            rating=new_feedback.rating,
            reason=new_feedback.reason,
            created_at=new_feedback.created_at.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting message feedback: {e}, {traceback.format_exc()}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to submit feedback: {str(e)}")


@chat.get("/message/{message_id}/feedback")
async def get_message_feedback(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_required_user),
):
    """Get feedback status for a specific message (for current user)"""
    try:
        # Get user's feedback for this message
        feedback = db.query(MessageFeedback).filter_by(message_id=message_id, user_id=str(current_user.id)).first()

        if not feedback:
            return {"has_feedback": False, "feedback": None}

        return {
            "has_feedback": True,
            "feedback": {
                "id": feedback.id,
                "rating": feedback.rating,
                "reason": feedback.reason,
                "created_at": feedback.created_at.isoformat(),
            },
        }

    except Exception as e:
        logger.error(f"Error getting message feedback: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get feedback: {str(e)}")
