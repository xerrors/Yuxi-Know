import json
import asyncio
import traceback
import uuid
from fastapi import APIRouter, Body
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk

from src import executor, config, retriever
from src.core import HistoryManager
from src.agents import agent_manager
from src.models import select_model
from src.utils.logging_config import logger

chat = APIRouter(prefix="/chat")



@chat.get("/")
async def chat_get():
    return "Chat Get!"

@chat.post("/")
def chat_post(
        query: str = Body(...),
        meta: dict = Body(None),
        history: list | None = Body(None),
        thread_id: str | None = Body(None)):

    model = select_model()
    meta["server_model_name"] = model.model_name
    history_manager = HistoryManager(history)
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
    model = select_model(model_provider=meta.get("model_provider"), model_name=meta.get("model_name"))
    async def predict_async(query):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, model.predict, query)

    response = await predict_async(query)
    logger.debug({"query": query, "response": response.content})

    return {"response": response.content}

@chat.post("/call_lite")
async def call(query: str = Body(...), meta: dict = Body(None)):
    meta = meta or {}
    async def predict_async(query):
        loop = asyncio.get_event_loop()
        model_provider = meta.get("model_provider", config.model_provider_lite)
        model_name = meta.get("model_name", config.model_name_lite)
        model = select_model(model_provider=model_provider, model_name=model_name)
        return await loop.run_in_executor(executor, model.predict, query)

    response = await predict_async(query)
    logger.debug({"query": query, "response": response.content})

    return {"response": response.content}

@chat.get("/agent")
async def get_agent():
    agents = [{
        "name": agent.name,
        "description": agent.description,
        "config_schema": agent.config_schema
    } for agent in agent_manager.agents.values()]
    return {"agents": agents}

@chat.post("/agent/{agent_name}")
def chat_agent(agent_name: str,
               query: str = Body(...),
               meta: dict = Body({}),
               history: list = Body(...),
               thread_id: str | None = Body(None)):

    meta["server_model_name"] = agent_name
    agent = agent_manager.get_runnable_agent(agent_name)

    history_manager = HistoryManager(history)
    messages = history_manager.get_history_with_msg(query, max_rounds=meta.get('history_round'))
    history_manager.add_user(query)  # 注意这里使用原始查询

    runnable_config = {
        "configurable": {
            "thread_id": thread_id or str(uuid.uuid4()),
            "use_web": meta.get("use_web", False),
            "return_keys": []
        }
    }

    def make_chunk(content=None, **kwargs):
        return json.dumps({
            "response": content,
            "model_name": agent_name,
            "meta": meta,
            **kwargs
        }, ensure_ascii=False).encode('utf-8') + b"\n"

    def stream_messages():
        content = ""
        yield make_chunk(status="waiting")
        for msg, metadata in agent.stream_messages(messages, runnable_config):
            # logger.debug(f">>>>>    msg: {msg.model_dump()}, >>>>>>>      {metadata=}")
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

        yield make_chunk(status="finished", history=history_manager.update_ai(content))

    return StreamingResponse(stream_messages(), media_type='application/json')
