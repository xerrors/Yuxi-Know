from contextlib import asynccontextmanager

from fastapi import FastAPI

from server.services import tasker
from src.services.mcp_service import init_mcp_servers
from src.utils import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan事件管理器"""
    # 初始化 MCP 服务器配置
    try:
        await init_mcp_servers()
    except Exception as e:
        logger.error(f"Failed to initialize MCP servers during startup: {e}")

    await tasker.start()
    yield
    await tasker.shutdown()
