"""Web 调试与集中反馈的 Turn 观测跳转。"""

from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.infrastructure.observability.langfuse import get_trace_url_by_id_async
from yuxi.modules.agents.repositories.feedback import AgentFeedbackRepository
from yuxi.modules.agents.repositories.turn import AgentTurnRepository
from yuxi.modules.agents.scope import ActorScope
from yuxi.modules.agents.services.thread_access import require_thread
from yuxi.shared.errors import PermissionDeniedError, ResourceNotFoundError


async def get_thread_turn_trace(*, db: AsyncSession, scope: ActorScope, thread_id: str, turn_id: str) -> dict:
    """读取管理员自身会话中指定轮次的观测地址。"""
    _require_trace_reader(scope)
    await require_thread(db=db, scope=scope, thread_id=thread_id)
    turn = await AgentTurnRepository(db).get_for_scope(turn_id=turn_id, thread_id=thread_id, uid=scope.uid, app_id=scope.app_id)
    if turn is None:
        raise ResourceNotFoundError("Turn 不存在")
    return await _resolve_turn_trace(db=db, turn_id=turn.id)


async def get_feedback_turn_trace(*, db: AsyncSession, scope: ActorScope, feedback_id: str) -> dict:
    """按集中反馈的真实执行关联读取轮次观测地址。"""
    _require_trace_reader(scope)
    turn = await AgentFeedbackRepository(db).get_platform_turn(feedback_id=feedback_id, scope=scope)
    if turn is None:
        raise ResourceNotFoundError("反馈不存在")
    return await _resolve_turn_trace(db=db, turn_id=turn.id)


def _require_trace_reader(scope: ActorScope) -> None:
    """观测跳转仅接受超级管理员产品 JWT。"""
    if not scope.is_superadmin or scope.api_key_id is not None or scope.app_id is not None:
        raise PermissionDeniedError("仅平台管理员可读取观测地址")


async def _resolve_turn_trace(*, db: AsyncSession, turn_id: str) -> dict:
    """用当前轮次持久 Trace 惰性解析地址。"""
    trace_id = await AgentTurnRepository(db).get_trace_id(turn_id)
    return {
        "turn_id": turn_id,
        "langfuse_trace_id": trace_id,
        "langfuse_url": await get_trace_url_by_id_async(trace_id) if trace_id else None,
    }
