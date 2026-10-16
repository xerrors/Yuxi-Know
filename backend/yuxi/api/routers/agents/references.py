"""Web 回答阅读中的来源标注接口。"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.api.dependencies.auth import get_db, get_required_user
from yuxi.modules.agents.scope import ActorScope
from yuxi.modules.agents.services.references import annotate_turn_references, get_turn_references
from yuxi.modules.identity.models import User

reference_router = APIRouter(prefix="/agent/threads", tags=["agent"], include_in_schema=False)


async def require_web_reference_scope(request: Request, user: User = Depends(get_required_user)) -> ActorScope:
    """仅允许 Web 登录用户读取产品 Thread 的来源标注。"""
    if getattr(request.state, "api_key", None) is not None:
        raise HTTPException(status_code=403, detail="来源标注仅支持 Web 登录用户")
    return ActorScope(uid=str(user.uid), app_id=None, is_superadmin=user.role == "superadmin")


@reference_router.get("/{thread_id}/turns/{turn_id}/references")
async def retrieve_turn_references(
    thread_id: str,
    turn_id: str,
    scope: ActorScope = Depends(require_web_reference_scope),
    db: AsyncSession = Depends(get_db),
):
    """读取本轮可见检索来源与持久标注。"""
    return await get_turn_references(db=db, scope=scope, thread_id=thread_id, turn_id=turn_id)


@reference_router.post("/{thread_id}/turns/{turn_id}/references")
async def annotate_answer_references(
    thread_id: str,
    turn_id: str,
    scope: ActorScope = Depends(require_web_reference_scope),
    db: AsyncSession = Depends(get_db),
):
    """按需调用模型标注当前 Turn 的最终回答。"""
    return await annotate_turn_references(db=db, scope=scope, thread_id=thread_id, turn_id=turn_id)
