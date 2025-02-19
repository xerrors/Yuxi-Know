import json
import asyncio
from fastapi import APIRouter, Body
from fastapi.responses import StreamingResponse, Response
from concurrent.futures import ThreadPoolExecutor
from src.core import HistoryManager
from src.core.startup import startup
from src.utils.logging_config import setup_logger

chat = APIRouter(prefix="/chat")
logger = setup_logger("server-chat")
# 创建线程池
executor = ThreadPoolExecutor()

refs_pool = {}

@chat.get("/")
async def chat_get():
    return "Chat Get!"

@chat.post("/")
def chat_post(
        query: str = Body(...),
        meta: dict = Body(None),
        history: list = Body(...),
        cur_res_id: str = Body(...)):

    history_manager = HistoryManager(history)

    def make_chunk(content=None, status=None, history=None, reasoning_content=None):
        return json.dumps({
            "response": content,
            "reasoning_response": reasoning_content,
            "history": history,
            "model_name": startup.config.model_name,
            "status": status,
            "meta": meta,
        }, ensure_ascii=False).encode('utf-8') + b"\n"

    def generate_response():
        modified_query = query

        # 处理知识库检索
        if meta and meta.get("enable_retrieval"):
            chunk = make_chunk(status="searching")
            yield chunk

            modified_query, refs = startup.retriever(modified_query, history_manager.messages, meta)
            refs_pool[cur_res_id] = refs

        messages = history_manager.get_history_with_msg(modified_query, max_rounds=meta.get('history_round'))
        history_manager.add_user(query)  # 注意这里使用原始查询
        logger.debug(f"Web history: {history_manager.messages}")

        content = ""
        reasoning_content = ""
        for delta in startup.model.predict(messages, stream=True):
            if not delta.content and hasattr(delta, 'reasoning_content'):
                reasoning_content += delta.reasoning_content
                chunk = make_chunk(reasoning_content=reasoning_content, status="reasoning")
                yield chunk
                continue

            # 文心一言
            if hasattr(delta, 'is_full') and delta.is_full:
                content = delta.content
            else:
                content += delta.content or ""

            chunk = make_chunk(content=content,
                               reasoning_content=reasoning_content,
                               status="loading",
                               history=history_manager.update_ai(content))
            yield chunk

        logger.debug(f"Final response: {content}")
        logger.debug(f"Final reasoning response: {reasoning_content}")

    return StreamingResponse(generate_response(), media_type='application/json')

@chat.post("/call")
async def call(query: str = Body(...), meta: dict = Body(None)):
    async def predict_async(query):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, startup.model.predict, query)

    response = await predict_async(query)
    logger.debug({"query": query, "response": response.content})

    return {"response": response.content}

@chat.post("/call_lite")
async def call(query: str = Body(...), meta: dict = Body(None)):
    async def predict_async(query):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, startup.model_lite.predict, query)

    response = await predict_async(query)
    logger.debug({"query": query, "response": response.content})

    return {"response": response.content}

@chat.get("/refs")
def get_refs(cur_res_id: str):
    global refs_pool
    refs = refs_pool.pop(cur_res_id, None)
    return {"refs": refs}