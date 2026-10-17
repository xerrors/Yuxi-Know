"""Web 管理员的 Turn 观测地址协议。"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.api.dependencies.auth import get_db, get_superadmin_user
from yuxi.modules.agents.scope import ActorScope
from yuxi.modules.agents.services.trace_links import get_feedback_turn_trace, get_thread_turn_trace
from yuxi.modules.identity.models import User

trace_router = APIRouter(tags=["agent"], include_in_schema=False)


class TurnTraceLink(BaseModel):
    """指定轮次的可选观测地址。"""

    turn_id: str
    langfuse_trace_id: str | None
    langfuse_url: str | None


async def require_trace_scope(request: Request, user: User = Depends(get_superadmin_user)) -> ActorScope:
    """只接受产品超级管理员身份。"""
    if getattr(request.state, "api_key", None) is not None:
        raise HTTPException(status_code=403, detail="API Key 无权读取观测地址")
    return ActorScope(uid=str(user.uid), app_id=None, is_superadmin=True)


@trace_router.get("/agent/threads/{thread_id}/turns/{turn_id}/langfuse", response_model=TurnTraceLink)
async def retrieve_turn_trace(
    thread_id: str,
    turn_id: str,
    scope: ActorScope = Depends(require_trace_scope),
    db: AsyncSession = Depends(get_db),
):
    """读取自身会话中本轮的 Langfuse 地址。"""
    return await get_thread_turn_trace(db=db, scope=scope, thread_id=thread_id, turn_id=turn_id)


@trace_router.get("/system/agent-feedback/{feedback_id}/langfuse", response_model=TurnTraceLink)
async def retrieve_feedback_trace(
    feedback_id: str,
    scope: ActorScope = Depends(require_trace_scope),
    db: AsyncSession = Depends(get_db),
):
    """读取平台反馈所关联轮次的 Langfuse 地址。"""
    return await get_feedback_turn_trace(db=db, scope=scope, feedback_id=feedback_id)
