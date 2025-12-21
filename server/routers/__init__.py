from fastapi import APIRouter

from server.routers.auth_router import auth
from server.routers.chat_router import chat
from server.routers.dashboard_router import dashboard
from server.routers.graph_router import graph
from server.routers.knowledge_router import knowledge
from server.routers.evaluation_router import evaluation
from server.routers.mindmap_router import mindmap
from server.routers.system_router import system
from server.routers.task_router import tasks
from server.routers.sql_database_router import sql_db

router = APIRouter()

# 注册路由结构
router.include_router(system)  # /api/system/*
router.include_router(auth)  # /api/auth/*
router.include_router(chat)  # /api/chat/*
router.include_router(dashboard)  # /api/dashboard/*
router.include_router(knowledge)  # /api/knowledge/*
router.include_router(evaluation)  # /api/evaluation/*
router.include_router(mindmap)  # /api/mindmap/*
router.include_router(graph)  # /api/graph/*
router.include_router(tasks)  # /api/tasks/*
router.include_router(sql_db)  # /api/tasks/*
