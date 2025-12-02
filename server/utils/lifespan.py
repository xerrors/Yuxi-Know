from contextlib import asynccontextmanager

from fastapi import FastAPI

from server.services import tasker


@asynccontextmanager
async def lifespan(app: FastAPI):
    await tasker.start()
    """FastAPI lifespan事件管理器"""
    yield
    await tasker.shutdown()
