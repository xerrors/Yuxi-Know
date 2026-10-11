"""Agent 对话的 Public Session 协议。"""

from fastapi import APIRouter

from yuxi.api.routers.public_v1.agents.capabilities import router as capabilities_router
from yuxi.api.routers.public_v1.agents.directory import router as directory_router
from yuxi.api.routers.public_v1.agents.events import router as events_router
from yuxi.api.routers.public_v1.agents.feedback import router as feedback_router
from yuxi.api.routers.public_v1.agents.threads import router as threads_router
from yuxi.api.routers.public_v1.agents.turns import router as turns_router

public_agents_router = APIRouter(prefix="/v1/agents", tags=["agents-public-v1"])
public_agents_router.include_router(threads_router)
public_agents_router.include_router(turns_router)
public_agents_router.include_router(feedback_router)
public_agents_router.include_router(events_router)
public_agents_router.include_router(capabilities_router)
public_agents_router.include_router(directory_router)

__all__ = ["public_agents_router"]
