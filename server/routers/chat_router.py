import asyncio
import json
import traceback
import uuid
import yaml
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk, HumanMessage
from pydantic import BaseModel
from sqlalchemy.orm import Session

from server.models.thread_model import Thread
from server.models.user_model import User
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
    model = select_model(model_provider=meta.get("model_provider"), model_name=meta.get("model_name"))

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
    if Path("src/static/agents_meta.yaml").exists():
        with open("src/static/agents_meta.yaml") as f:
            metadata = yaml.safe_load(f)
    return {"agents": agents, "metadata": metadata}


@chat.post("/agent/{agent_id}")
async def chat_agent(
    agent_id: str,
    query: str = Body(...),
    config: dict = Body({}),
    meta: dict = Body({}),
    current_user: User = Depends(get_required_user),
):
    """使用特定智能体进行对话（需要登录）"""

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

    async def stream_messages():
        # 代表服务端已经收到了请求
        yield make_chunk(status="init", meta=meta, msg=HumanMessage(content=query).model_dump())

        # Input guard
        if conf.enable_content_guard and content_guard.check(query):
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

        try:
            # Output guard for streaming
            accumulated_content = ""
            async for msg, metadata in agent.stream_messages(messages, input_context=input_context):
                # logger.debug(f"msg: {msg.model_dump()}, metadata: {metadata}")
                if isinstance(msg, AIMessageChunk):

                    accumulated_content += msg.content
                    if conf.enable_content_guard and content_guard.check(accumulated_content):
                        logger.warning(f"Sensitive content detected in stream: {accumulated_content}")
                        yield make_chunk(message="检测到敏感内容，已中断输出", status="error")
                        return

                    yield make_chunk(content=msg.content, msg=msg.model_dump(), metadata=metadata, status="loading")

                else:
                    yield make_chunk(msg=msg.model_dump(), metadata=metadata, status="loading")

            # Additional content guard with llm
            if conf.enable_content_guard and content_guard.check_with_llm(accumulated_content):
                logger.warning(f"Content guard triggered: {accumulated_content=}")
                yield make_chunk(message="检测到敏感内容，已中断输出", status="error")
                return

            yield make_chunk(status="finished", meta=meta)
        except Exception as e:
            logger.error(f"Error streaming messages: {e}, {traceback.format_exc()}")
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
    conf.model_names[model_provider]["models"] = model_names
    conf._save_models_to_file()
    return {"models": conf.model_names[model_provider]["models"]}


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
async def get_agent_history(agent_id: str, thread_id: str, current_user: User = Depends(get_required_user)):
    """获取智能体历史消息（需要登录）"""
    try:
        # 获取Agent实例和配置类
        if not (agent := agent_manager.get_agent(agent_id)):
            raise HTTPException(status_code=404, detail=f"智能体 {agent_id} 不存在")

        # 获取历史消息
        history = await agent.get_history(user_id=str(current_user.id), thread_id=thread_id)
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
    description: str | None = None
    metadata: dict | None = None


class ThreadResponse(BaseModel):
    id: str
    user_id: str
    agent_id: str
    title: str | None = None
    description: str | None = None
    create_at: str
    update_at: str


# =============================================================================
# > === 会话管理分组 ===
# =============================================================================


@chat.post("/thread", response_model=ThreadResponse)
async def create_thread(
    thread: ThreadCreate, db: Session = Depends(get_db), current_user: User = Depends(get_required_user)
):
    """创建新对话线程"""
    thread_id = str(uuid.uuid4())
    logger.debug(f"thread.agent_id: {thread.agent_id}")

    new_thread = Thread(
        id=thread_id,
        user_id=str(current_user.id),
        agent_id=thread.agent_id,
        title=thread.title or "新的对话",
        description=thread.description,
    )

    db.add(new_thread)
    db.commit()
    db.refresh(new_thread)

    return {
        "id": new_thread.id,
        "user_id": new_thread.user_id,
        "agent_id": new_thread.agent_id,
        "title": new_thread.title,
        "description": new_thread.description,
        "create_at": new_thread.create_at.isoformat(),
        "update_at": new_thread.update_at.isoformat(),
    }


@chat.get("/threads", response_model=list[ThreadResponse])
async def list_threads(agent_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_required_user)):
    """获取用户的所有对话线程"""
    assert agent_id, "agent_id 不能为空"
    query = db.query(Thread).filter(
        Thread.user_id == str(current_user.id),
        Thread.status == 1,
        Thread.agent_id == agent_id,
    )

    logger.debug(f"agent_id: {agent_id}")

    threads = query.order_by(Thread.update_at.desc()).all()

    return [
        {
            "id": thread.id,
            "user_id": thread.user_id,
            "agent_id": thread.agent_id,
            "title": thread.title,
            "description": thread.description,
            "create_at": thread.create_at.isoformat(),
            "update_at": thread.update_at.isoformat(),
        }
        for thread in threads
    ]


@chat.delete("/thread/{thread_id}")
async def delete_thread(thread_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_required_user)):
    """删除对话线程"""
    thread = db.query(Thread).filter(Thread.id == thread_id, Thread.user_id == str(current_user.id)).first()

    if not thread:
        raise HTTPException(status_code=404, detail="对话线程不存在")

    # 软删除
    thread.status = 0
    db.commit()

    return {"message": "删除成功"}


class ThreadUpdate(BaseModel):
    title: str | None = None
    description: str | None = None


@chat.put("/thread/{thread_id}", response_model=ThreadResponse)
async def update_thread(
    thread_id: str,
    thread_update: ThreadUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_required_user),
):
    """更新对话线程信息"""
    thread = (
        db.query(Thread)
        .filter(Thread.id == thread_id, Thread.user_id == str(current_user.id), Thread.status == 1)
        .first()
    )

    if not thread:
        raise HTTPException(status_code=404, detail="对话线程不存在")

    if thread_update.title is not None:
        thread.title = thread_update.title

    if thread_update.description is not None:
        thread.description = thread_update.description

    db.commit()
    db.refresh(thread)

    return {
        "id": thread.id,
        "user_id": thread.user_id,
        "agent_id": thread.agent_id,
        "title": thread.title,
        "description": thread.description,
        "create_at": thread.create_at.isoformat(),
        "update_at": thread.update_at.isoformat(),
    }
