"""用户评价和 Agent 改进标记的事务 Owner。"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.modules.agents.models.messages import Message
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.modules.agents.repositories.definitions import AgentRepository
from yuxi.modules.agents.repositories.feedback import AgentFeedbackRepository
from yuxi.modules.agents.services.scope import ActorScope
from yuxi.modules.agents.services.threads import require_thread
from yuxi.modules.identity.models import User
from yuxi.shared.datetime import utc_now


async def save_user_feedback(
    *, db: AsyncSession, scope: ActorScope, thread_id: str, turn_id: str, run_id: str, rating: str, reason: str | None
) -> dict:
    """保存合法最终回答的完整当前评价，提交后才返回成功。"""
    if rating not in {"like", "dislike"}:
        raise HTTPException(status_code=422, detail="评价必须为 like 或 dislike")
    reason = normalize_reason(reason, source="user")
    await require_feedback_target(db=db, scope=scope, thread_id=thread_id, turn_id=turn_id, run_id=run_id)
    record = await AgentFeedbackRepository(db).save_user(run_id=run_id, rating=rating, reason=reason)
    result = record.to_dict()
    await db.commit()
    return result


async def remove_user_feedback(*, db: AsyncSession, scope: ActorScope, thread_id: str, turn_id: str, run_id: str) -> None:
    """在同一授权与最终输出边界内幂等撤销评价。"""
    await require_feedback_target(db=db, scope=scope, thread_id=thread_id, turn_id=turn_id, run_id=run_id)
    await AgentFeedbackRepository(db).remove_user(run_id)
    await db.commit()


async def mark_run_for_improvement(
    *, db: AsyncSession, run_id: str, uid: str, thread_id: str, worker_id: str, tool_call_id: str, reason: str
) -> dict:
    """以可信执行身份记录线索，同一调用重放返回已提交记录。"""
    from yuxi.modules.agents.runtime.middlewares.authorization import AgentExecutionRevoked

    reason = normalize_reason(reason, source="agent")
    run = await db.get(AgentRun, run_id)
    if run is None or run.uid != uid or run.thread_id != thread_id:
        raise AgentExecutionRevoked("执行身份或会话已失效")
    await require_thread(db=db, scope=ActorScope(uid=uid, app_id=run.app_id), thread_id=thread_id, lock=True)
    # 租约续租、撤销和本次写入竞争同一 Run 行锁，旧 attempt 不能在检查后偷写。
    run = await db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update().execution_options(populate_existing=True))
    user = await db.scalar(select(User).where(User.uid == uid, User.is_deleted == 0))
    if user is None or await AgentRepository(db).get_visible_by_slug(slug=run.agent_slug, user=user) is None:
        raise AgentExecutionRevoked("执行账号或 Agent 使用权限已撤销")
    if not tool_call_id or not tool_call_id.strip():
        raise HTTPException(status_code=422, detail="缺少可信工具调用 ID")
    repo = AgentFeedbackRepository(db)
    existing = await repo.get(run_id=run_id, source="agent", tool_call_id=tool_call_id)
    if existing is not None:
        if existing.reason != reason:
            raise HTTPException(status_code=409, detail="同一工具调用不能改变标记原因")
        return existing.to_dict()
    if (
        run.status != "running"
        or not worker_id
        or run.worker_id != worker_id
        or run.lease_expires_at is None
        or run.lease_expires_at <= utc_now()
    ):
        raise AgentExecutionRevoked("执行 ownership 或租约已失效")
    record = await repo.add_mark(run_id=run_id, tool_call_id=tool_call_id, reason=reason)
    result = record.to_dict()
    await db.commit()
    return result


async def list_feedback(*, db: AsyncSession, scope: ActorScope, thread_id: str | None = None, platform: bool = False, **filters) -> dict:
    """读取自身会话或 JWT 平台管理员的有界记录。"""
    if platform:
        if not scope.is_superadmin or scope.api_key_id is not None or scope.app_id is not None:
            raise HTTPException(status_code=403, detail="仅平台管理员可查询集中反馈")
    elif thread_id is None:
        raise HTTPException(status_code=404, detail="Thread 不存在")
    else:
        await require_thread(db=db, scope=scope, thread_id=thread_id)
    try:
        return await AgentFeedbackRepository(db).list_page(scope=scope, platform=platform, thread_id=thread_id, **filters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def require_feedback_target(*, db: AsyncSession, scope: ActorScope, thread_id: str, turn_id: str, run_id: str) -> None:
    """锁定拥有者会话，验证评价针对显式绑定的最终助手输出。"""
    agent_session = await require_thread(db=db, scope=scope, thread_id=thread_id, lock=True)
    turn = await db.scalar(
        select(AgentTurn).where(
            AgentTurn.id == turn_id, AgentTurn.thread_id == thread_id, AgentTurn.uid == scope.uid, AgentTurn.app_id == scope.app_id
        )
    )
    run = await db.scalar(
        select(AgentRun).where(
            AgentRun.id == run_id,
            AgentRun.thread_id == thread_id,
            AgentRun.turn_id == turn_id,
            AgentRun.uid == scope.uid,
            AgentRun.app_id == scope.app_id,
        )
    )
    if turn is None or run is None:
        raise HTTPException(status_code=404, detail="Turn 或 Run 不存在")
    if turn.status not in {"completed", "failed", "cancelled"} or turn.result_run_id != run.id:
        raise HTTPException(status_code=409, detail="只能评价本轮的最终回答")
    output = await db.get(Message, run.output_message_id) if run.output_message_id is not None else None
    if (
        output is None
        or output.run_id != run.id
        or output.turn_id != turn.id
        or output.session_record_id != agent_session.id
        or output.role != "assistant"
        or not output.content.strip()
    ):
        raise HTTPException(status_code=409, detail="本轮没有可评价的最终回答")


def normalize_reason(reason: str | None, *, source: str) -> str | None:
    """在持久化边界统一裁剪与限制反馈正文。"""
    normalized = reason.strip() if reason is not None else ""
    maximum = 2000 if source == "user" else 4000
    if len(normalized) > maximum or (source == "agent" and not normalized):
        raise HTTPException(status_code=422, detail=f"反馈原因{'须非空且' if source == 'agent' else ''}不能超过 {maximum} 字符")
    return normalized or None
