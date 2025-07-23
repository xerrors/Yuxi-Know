from fastapi import APIRouter
from server.routers.system_router import system
from server.routers.auth_router import auth
from server.routers.chat_router import chat
from server.routers.knowledge_router import knowledge
from server.routers.graph_router import graph
from server.routers.tool_router import tool

router = APIRouter()

# 注册路由结构
router.include_router(system)      # /api/system/*
router.include_router(auth)        # /api/auth/*
router.include_router(chat)        # /api/chat/*
router.include_router(knowledge)   # /api/knowledge/*
router.include_router(graph)       # /api/graph/*
router.include_router(tool)        # /api/tool/*
