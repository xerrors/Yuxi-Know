from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
import json
from src.core import HistoryManager
from src.core.startup import startup
from src.utils.logging_config import setup_logger

chat = APIRouter(prefix="/chat")
logger = setup_logger("server-chat")

@chat.get("/")
async def chat_get():
    return "Chat Get!"

@chat.post("/")
async def chat_post(request: Request):
    request_data = await request.json()
    query = request_data['query']
    meta = request_data.get('meta')
    history_manager = HistoryManager(request_data['history'])

    new_query, refs = startup.retriever(query, history_manager.messages, meta)

    messages = history_manager.get_history_with_msg(new_query, max_rounds=meta.get('history_round'))
    history_manager.add_user(query)
    logger.debug(f"Web history: {history_manager.messages}")

    async def generate_response():
        content = ""
        for delta in startup.model.predict(messages, stream=True):
            if not delta.content:
                continue

            if hasattr(delta, 'is_full') and delta.is_full:
                content = delta.content
            else:
                content += delta.content

            response_chunk = json.dumps({
                "history": history_manager.update_ai(content),
                "response": content,
                "refs": refs  # TODO: 优化 refs，不需要每次都返回
            }, ensure_ascii=False).encode('utf8') + b'\n'
            yield response_chunk

    return StreamingResponse(generate_response(), media_type='application/json')

@chat.post("/call")
async def call(request: Request):
    request_data = await request.json()
    query = request_data['query']
    response = startup.model.predict(query)
    logger.debug({"query": query, "response": response.content})

    return {"response": response.content}