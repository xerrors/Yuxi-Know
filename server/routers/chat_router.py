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

chat = APIRouter(prefix="/chat")

@chat.get("/")
async def chat_get():
    return "Chat Get!"

@chat.post("/")
async def chat_post(
        query: str = Body(...),
        meta: dict = Body(None),
        history: list[dict] | None = Body(None),
        thread_id: str | None = Body(None)):
    """处理聊天请求的主要端点。
    Args:
        query: 用户的输入查询文本
        meta: 包含请求元数据的字典，可以包含以下字段：
            - use_web: 是否使用网络搜索
            - use_graph: 是否使用知识图谱
            - db_id: 数据库ID
            - history_round: 历史对话轮数限制
            - system_prompt: 系统提示词（str，不含变量）
        history: 对话历史记录列表
        thread_id: 对话线程ID
    Returns:
        StreamingResponse: 返回一个流式响应，包含以下状态：
            - searching: 正在搜索知识库
            - generating: 正在生成回答
            - reasoning: 正在推理
            - loading: 正在加载回答
            - finished: 回答完成
            - error: 发生错误
    Raises:
        HTTPException: 当检索器或模型发生错误时抛出
    """

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
async def call(query: str = Body(...), meta: dict = Body(None)):
    meta = meta or {}
    model = select_model(model_provider=meta.get("model_provider"), model_name=meta.get("model_name"))
    async def predict_async(query):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, model.predict, query)

    response = await predict_async(query)
    logger.debug({"query": query, "response": response.content})

    return {"response": response.content}

@chat.get("/agent")
async def get_agent():
    agents = [agent.get_info() for agent in agent_manager.agents.values()]
    return {"agents": agents}

@chat.post("/agent/{agent_name}")
def chat_agent(agent_name: str,
               query: str = Body(...),
               history: list = Body(...),
               config: dict = Body({}),
               meta: dict = Body({})):

    meta.update({
        "query": query,
        "agent_name": agent_name,
        "server_model_name": config.get("model", agent_name) ,
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
async def get_chat_models(model_provider: str):
    """获取指定模型提供商的模型列表"""
    model = select_model(model_provider=model_provider)
    return {"models": model.get_models()}

@chat.post("/models/update")
async def update_chat_models(model_provider: str, model_names: list[str]):
    """更新指定模型提供商的模型列表"""
    config.model_names[model_provider]["models"] = model_names
    config._save_models_to_file()
    return {"models": config.model_names[model_provider]["models"]}

@chat.get("/tools")
async def get_tools():
    """获取所有工具"""
    return {"tools": list(get_all_tools().keys())}
