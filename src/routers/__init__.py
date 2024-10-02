from fastapi import APIRouter
from src.routers.chat_router import chat
from src.routers.data_router import data
from src.routers.base_router import base
from src.routers.tool_router import tool

router = APIRouter()
router.include_router(base)
router.include_router(chat)
router.include_router(data)
router.include_router(tool)
