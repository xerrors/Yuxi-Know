import os
import json
import asyncio
import traceback
import uuid
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk

from src import executor, config, retriever
from src.core import HistoryManager
from src.agents import agent_manager
from src.models import select_model
from src.utils.logging_config import logger
from src.agents.tools_factory import get_all_tools
from server.routers.auth_router import get_admin_user
from server.utils.auth_middleware import get_required_user
from server.models.user_model import User

chat = APIRouter(prefix="/chat")

@chat.get("/default_agent")
async def get_default_agent(current_user: User = Depends(get_required_user)):
    """获取默认智能体ID（需要登录）"""
    try:
        default_agent_id = config.default_agent_id
        # 如果没有设置默认智能体，尝试获取第一个可用的智能体
        if not default_agent_id:
            agents = [agent.get_info() for agent in agent_manager.agents.values()]
            if agents:
                default_agent_id = agents[0].get("name", "")

        return {"default_agent_id": default_agent_id}
    except Exception as e:
        logger.error(f"获取默认智能体出错: {e}")
        raise HTTPException(status_code=500, detail=f"获取默认智能体出错: {str(e)}")

@chat.post("/set_default_agent")
async def set_default_agent(agent_id: str = Body(..., embed=True), current_user = Depends(get_admin_user)):
    """设置默认智能体ID (仅管理员)"""
    try:
        # 验证智能体是否存在
        agents = [agent.get_info() for agent in agent_manager.agents.values()]
        agent_ids = [agent.get("name", "") for agent in agents]

        if agent_id not in agent_ids:
            raise HTTPException(status_code=404, detail=f"智能体 {agent_id} 不存在")

        # 设置默认智能体ID
        config.default_agent_id = agent_id
        # 保存配置
        config.save()

        return {"success": True, "default_agent_id": agent_id}
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"设置默认智能体出错: {e}")
        raise HTTPException(status_code=500, detail=f"设置默认智能体出错: {str(e)}")

@chat.get("/")
async def chat_get(current_user: User = Depends(get_required_user)):
    """聊天服务健康检查（需要登录）"""
    return "Chat Get!"

@chat.post("/")
async def chat_post(
        query: str = Body(...),
        meta: dict = Body(None),
        history: list[dict] | None = Body(None),
        thread_id: str | None = Body(None),
        current_user: User = Depends(get_required_user)):
    """处理聊天请求的主要端点（需要登录）"""

    model = select_model()
    meta["server_model_name"] = model.model_name
    history_manager = HistoryManager(history, system_prompt=meta.get("system_prompt"))
    logger.debug(f"Received query: {query} with meta: {meta}")

    def make_chunk(content=None, **kwargs):
        return json.dumps({
            "response": content,
            "meta": meta,
            **kwargs
        }, ensure_ascii=False).encode('utf-8') + b"\n"

    def need_retrieve(meta):
        return meta.get("use_web") or meta.get("use_graph") or meta.get("db_id")

    def generate_response():
        modified_query = query
        refs = None

        # 处理知识库检索
        if meta and need_retrieve(meta):
            chunk = make_chunk(status="searching")
            yield chunk

            try:
                modified_query, refs = retriever(modified_query, history_manager.messages, meta)
            except Exception as e:
                logger.error(f"Retriever error: {e}, {traceback.format_exc()}")
                yield make_chunk(message=f"Retriever error: {e}", status="error")
                return

            yield make_chunk(status="generating")

        messages = history_manager.get_history_with_msg(modified_query, max_rounds=meta.get('history_round'))
        history_manager.add_user(query)  # 注意这里使用原始查询

        content = ""
        reasoning_content = ""
        try:
            for delta in model.predict(messages, stream=True):
                if not delta.content and hasattr(delta, 'reasoning_content'):
                    reasoning_content += delta.reasoning_content or ""
                    chunk = make_chunk(reasoning_content=reasoning_content, status="reasoning")
                    yield chunk
                    continue

                # 文心一言
                if hasattr(delta, 'is_full') and delta.is_full:
                    content = delta.content
                else:
                    content += delta.content or ""

                chunk = make_chunk(content=delta.content, status="loading")
                yield chunk

            logger.debug(f"Final response: {content}")
            logger.debug(f"Final reasoning response: {reasoning_content}")
            yield make_chunk(status="finished",
                            history=history_manager.update_ai(content),
                            refs=refs)
        except Exception as e:
            logger.error(f"Model error: {e}, {traceback.format_exc()}")
            yield make_chunk(message=f"Model error: {e}", status="error")
            return

    return StreamingResponse(generate_response(), media_type='application/json')

@chat.post("/call")
async def call(query: str = Body(...), meta: dict = Body(None), current_user: User = Depends(get_required_user)):
    """调用模型进行简单问答（需要登录）"""
    meta = meta or {}
    model = select_model(model_provider=meta.get("model_provider"), model_name=meta.get("model_name"))
    async def predict_async(query):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, model.predict, query)

    response = await predict_async(query)
    logger.debug({"query": query, "response": response.content})

    return {"response": response.content}

@chat.get("/agent")
async def get_agent(current_user: User = Depends(get_required_user)):
    """获取所有可用智能体（需要登录）"""
    agents = [agent.get_info() for agent in agent_manager.agents.values()]
    return {"agents": agents}

@chat.post("/agent/{agent_name}")
def chat_agent(agent_name: str,
               query: str = Body(...),
               history: list = Body(...),
               config: dict = Body({}),
               meta: dict = Body({}),
               current_user: User = Depends(get_required_user)):
    """使用特定智能体进行对话（需要登录）"""

    meta.update({
        "query": query,
        "agent_name": agent_name,
        "server_model_name": config.get("model", agent_name),
        "thread_id": config.get("thread_id"),
    })

    # 将meta和thread_id整合到config中
    def make_chunk(content=None, **kwargs):

        return json.dumps({
            "request_id": meta.get("request_id"),
            "response": content,
            **kwargs
        }, ensure_ascii=False).encode('utf-8') + b"\n"

    def stream_messages():

        # 代表服务端已经收到了请求
        yield make_chunk(status="init", meta=meta)

        try:
            agent = agent_manager.get_runnable_agent(agent_name)
        except Exception as e:
            logger.error(f"Error getting agent {agent_name}: {e}, {traceback.format_exc()}")
            yield make_chunk(message=f"Error getting agent {agent_name}: {e}", status="error")
            return

        # 从config中获取history_round
        history_round = config.get("history_round")
        history_manager = HistoryManager(history)
        messages = history_manager.get_history_with_msg(query, max_rounds=history_round)
        history_manager.add_user(query)

        # 构造运行时配置，如果没有thread_id则生成一个
        if "thread_id" not in config or not config["thread_id"]:
            config["thread_id"] = str(uuid.uuid4())

        runnable_config = {"configurable": {**config}}

        content = ""

        try:
            for msg, metadata in agent.stream_messages(messages, config_schema=runnable_config):
                if isinstance(msg, AIMessageChunk) and msg.content != "<tool_call>":
                    content += msg.content
                    yield make_chunk(content=msg.content,
                                    msg=msg.model_dump(),
                                    metadata=metadata,
                                    status="loading")
                else:
                    yield make_chunk(msg=msg.model_dump(),
                                    metadata=metadata,
                                    status="loading")

            yield make_chunk(status="finished",
                            history=history_manager.update_ai(content),
                            meta=meta)
        except Exception as e:
            logger.error(f"Error streaming messages: {e}, {traceback.format_exc()}")
            yield make_chunk(message=f"Error streaming messages: {e}", status="error")

    return StreamingResponse(stream_messages(), media_type='application/json')

@chat.get("/models")
async def get_chat_models(model_provider: str, current_user: User = Depends(get_admin_user)):
    """获取指定模型提供商的模型列表（需要登录）"""
    model = select_model(model_provider=model_provider)
    return {"models": model.get_models()}

@chat.post("/models/update")
async def update_chat_models(model_provider: str, model_names: list[str], current_user = Depends(get_admin_user)):
    """更新指定模型提供商的模型列表 (仅管理员)"""
    config.model_names[model_provider]["models"] = model_names
    config._save_models_to_file()
    return {"models": config.model_names[model_provider]["models"]}

@chat.get("/tools")
async def get_tools(current_user: User = Depends(get_admin_user)):
    """获取所有可用工具（需要登录）"""
    return {"tools": list(get_all_tools().keys())}

@chat.post("/agent/{agent_name}/config")
async def save_agent_config(
    agent_name: str,
    config: dict = Body(...),
    current_user: User = Depends(get_admin_user)
):
    """保存智能体配置到YAML文件（需要管理员权限）"""
    try:
        # 获取Agent实例和配置类
        agent = agent_manager.get_agent(agent_name)
        if not agent:
            raise HTTPException(status_code=404, detail=f"智能体 {agent_name} 不存在")

        # 使用配置类的save_to_file方法保存配置
        config_cls = agent.config_schema
        result = config_cls.save_to_file(config, agent_name)

        if result:
            return {"success": True, "message": f"智能体 {agent_name} 配置已保存"}
        else:
            raise HTTPException(status_code=500, detail=f"保存智能体配置失败")

    except Exception as e:
        logger.error(f"保存智能体配置出错: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"保存智能体配置出错: {str(e)}")

@chat.get("/agent/{agent_name}/config")
async def get_agent_config(
    agent_name: str,
    current_user: User = Depends(get_admin_user)
):
    """从YAML文件加载智能体配置（需要管理员权限）"""
    try:
        # 检查智能体是否存在
        if not (agent := agent_manager.get_agent(agent_name)):
            raise HTTPException(status_code=404, detail=f"智能体 {agent_name} 不存在")

        config = agent.config_schema.from_runnable_config(config={}, agent_name=agent_name)
        return {"success": True, "config": config}

    except Exception as e:
        logger.error(f"加载智能体配置出错: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"加载智能体配置出错: {str(e)}")
