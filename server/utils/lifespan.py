import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from server.services import tasker

#TODO:[已完成]使用lifespan进行统一生命周期管理

@asynccontextmanager
async def lifespan(app: FastAPI):
    await tasker.start()
    """FastAPI lifespan事件管理器"""
    yield
    await tasker.shutdown()
