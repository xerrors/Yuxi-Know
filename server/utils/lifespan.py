from contextlib import asynccontextmanager

from fastapi import FastAPI

from server.services import tasker
from src.services.mcp_service import init_mcp_servers
from src.storage.postgres.manager import pg_manager
from src.knowledge import knowledge_base
from src.utils import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan事件管理器"""
    # 初始化数据库连接
    try:
        pg_manager.initialize()
    except Exception as e:
        logger.error(f"Failed to initialize database during startup: {e}")

    # 初始化 MCP 服务器配置
    try:
        await init_mcp_servers()
    except Exception as e:
        logger.error(f"Failed to initialize MCP servers during startup: {e}")

    # 初始化知识库管理器
    try:
        await knowledge_base.initialize()
    except Exception as e:
        logger.error(f"Failed to initialize knowledge base manager: {e}")

    await tasker.start()
    yield
    await tasker.shutdown()
    await pg_manager.close()
