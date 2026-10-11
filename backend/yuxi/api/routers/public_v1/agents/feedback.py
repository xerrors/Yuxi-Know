"""当前用户的结果评价与会话反馈读取协议。"""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.api.dependencies.auth import get_db
from yuxi.api.routers.public_v1.agents.auth import PublicAgentContext, require_public_context
from yuxi.api.routers.public_v1.agents.responses import PUBLIC_ERRORS
from yuxi.api.routers.public_v1.agents.schemas import FeedbackPage, FeedbackRecord
from yuxi.modules.agents.services.feedback import list_feedback, remove_user_feedback, save_user_feedback

router = APIRouter(dependencies=[Depends(require_public_context)], responses=PUBLIC_ERRORS)


class UserFeedbackInput(BaseModel):
    """替换最终回答的完整当前评价。"""

    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(min_length=1, max_length=64)
    rating: Literal["like", "dislike"]
    reason: str | None = None


@router.put("/sessions/{session_id}/turns/{turn_id}/feedback", summary="保存最终回答的用户评价", response_model=FeedbackRecord)
async def put_feedback(
    session_id: str,
    turn_id: str,
    payload: UserFeedbackInput,
    context: PublicAgentContext = Depends(require_public_context),
    db: AsyncSession = Depends(get_db),
):
    """只接受自身用户与 APP 的最终结果，提交后返回持久记录。"""
    return await save_user_feedback(db=db, scope=context.scope, thread_id=session_id, turn_id=turn_id, **payload.model_dump())


@router.delete("/sessions/{session_id}/turns/{turn_id}/feedback", status_code=204, summary="撤销当前用户评价")
async def delete_feedback(
    session_id: str,
    turn_id: str,
    run_id: str = Query(min_length=1, max_length=64),
    context: PublicAgentContext = Depends(require_public_context),
    db: AsyncSession = Depends(get_db),
):
    """同一合法目标重复撤销成功，Agent 标记保持不变。"""
    await remove_user_feedback(db=db, scope=context.scope, thread_id=session_id, turn_id=turn_id, run_id=run_id)
    return Response(status_code=204)


@router.get("/sessions/{session_id}/feedback", summary="分页或批量恢复会话反馈", response_model=FeedbackPage)
async def get_feedback(
    session_id: str,
    source: Literal["user", "agent"] | None = None,
    run_ids: list[str] | None = Query(default=None, max_length=100),
    after: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=100),
    context: PublicAgentContext = Depends(require_public_context),
    db: AsyncSession = Depends(get_db),
):
    """按完整 ActorScope 读取当前会话，不返回原始对话或 manifest。"""
    return await list_feedback(db=db, scope=context.scope, thread_id=session_id, source=source, run_ids=run_ids, after=after, limit=limit)
