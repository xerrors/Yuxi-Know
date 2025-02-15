import json
import asyncio
from fastapi import APIRouter, Body
from fastapi.responses import StreamingResponse, Response
from concurrent.futures import ThreadPoolExecutor
from src.core import HistoryManager
from src.core.startup import startup
from src.utils.logging_config import setup_logger
from src.utils.web_search import WebSearcher

chat = APIRouter(prefix="/chat")
logger = setup_logger("server-chat")
# 创建线程池
executor = ThreadPoolExecutor()

refs_pool = {}
web_searcher = WebSearcher()

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

    def make_chunk(content, status, history):
        return json.dumps({
            "response": content,
            "history": history,
            "model_name": startup.config.model_name,
            "status": status,
            "meta": meta,
        }, ensure_ascii=False).encode('utf-8') + b"\n"

    def generate_response():
        modified_query = query
        
        # 处理网页搜索
        if meta and meta.get("enable_web_search"):
            chunk = make_chunk("正在进行网络搜索...", "searching", history=None)
            yield chunk

            try:
                search_results = web_searcher.search(query)
                if search_results:
                    search_context = web_searcher.format_search_results(search_results)
                    # 将搜索结果添加到查询中
                    modified_query = f"""基于以下网络搜索结果回答问题：

                    {search_context}

                    用户问题：{query}

                    请综合以上搜索结果，给出准确、客观的回答。如果搜索结果与问题相关性不大，请直接基于你的知识回答。
                    """
                    logger.info(f"Web search results added to query")
                else:
                    logger.warning("No web search results found")
            except Exception as e:
                logger.error(f"Web search error: {str(e)}")
                chunk = make_chunk("网络搜索失败，将直接回答问题。", "loading", history=None)
                yield chunk

        # 处理知识库检索
        if meta and meta.get("enable_retrieval"):
            chunk = make_chunk("", "searching", history=None)
            yield chunk

            modified_query, refs = startup.retriever(modified_query, history_manager.messages, meta)
            refs_pool[cur_res_id] = refs

        messages = history_manager.get_history_with_msg(modified_query, max_rounds=meta.get('history_round'))
        history_manager.add_user(query)  # 注意这里使用原始查询
        logger.debug(f"Final query: {modified_query}")

        content = ""
        for delta in startup.model.predict(messages, stream=True):
            if not delta.content:
                continue

            if hasattr(delta, 'is_full') and delta.is_full:
                content = delta.content
            else:
                content += delta.content

            chunk = make_chunk(content, "loading", history=history_manager.update_ai(content))
            yield chunk

    return StreamingResponse(generate_response(), media_type='application/json')

@chat.post("/call")
async def call(query: str = Body(...), meta: dict = Body(None)):
    async def predict_async(query):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, startup.model.predict, query)

    response = await predict_async(query)
    logger.debug({"query": query, "response": response.content})

    return {"response": response.content}

@chat.get("/refs")
def get_refs(cur_res_id: str):
    global refs_pool
    refs = refs_pool.pop(cur_res_id, None)
    return {"refs": refs}