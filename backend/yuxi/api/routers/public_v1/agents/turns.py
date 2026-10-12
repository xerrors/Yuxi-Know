"""Public Input、Turn 与消息查询。"""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.api.dependencies.auth import get_db
from yuxi.api.routers.public_v1.agents.auth import PublicAgentContext, require_public_context
from yuxi.api.routers.public_v1.agents.responses import PUBLIC_ERRORS
from yuxi.api.routers.public_v1.agents.schemas import (
    EventAccepted,
    InputResponse,
    ItemList,
    PublicError,
    TurnList,
    TurnResponse,
)
from yuxi.modules.agents.services.inputs import get_input_snapshot, get_receipt_snapshot
from yuxi.modules.agents.services.message_audits import get_thread_audits
from yuxi.modules.agents.services.public_items import list_session_items
from yuxi.modules.agents.services.public_resources import event_receipt
from yuxi.modules.agents.services.runs import get_run_snapshot
from yuxi.modules.agents.services.turns import get_turn_snapshot, list_turn_page

router = APIRouter(dependencies=[Depends(require_public_context)], responses=PUBLIC_ERRORS)


@router.get(
    "/sessions/{session_id}/items",
    summary="分页读取会话公开内容",
    response_model=ItemList,
    responses={400: {"model": PublicError, "description": "after 不属于当前 Session 的公开 item。"}},
)
async def list_public_session_items(
    session_id: str,
    after: str | None = Query(default=None, description="上一页 last_id；必须属于当前 Session，在所选排序下读取其后内容。"),
    limit: int = Query(default=20, ge=1, le=100, description="每页最多 item 数量。"),
    order: Literal["asc", "desc"] = Query(default="desc", description="持久消息及消息内公开投影顺序；desc 为最新优先。"),
    context: PublicAgentContext = Depends(require_public_context),
    db: AsyncSession = Depends(get_db),
):
    """读取当前会话的用户消息、公开助手正文、函数调用与结果。

    未消费及取消的输入不进入正式历史；内部 prompt、checkpoint 和完整审计不会返回。
    用 last_id 作为下一页 after；has_more=false 表示当前快照已读完。
    Items 用于持久历史和断线恢复，最终输出仍按 Turn 的 result_run_id 确认。
    """
    return await list_session_items(db=db, scope=context.scope, thread_id=session_id, after=after, limit=limit, order=order)


@router.get("/sessions/{session_id}/receipt", summary="按幂等键恢复接收回执", response_model=EventAccepted)
async def retrieve_public_receipt(
    session_id: str,
    idempotency_key: str = Query(min_length=1, description="原请求的 Idempotency-Key；不存在返回 404，可重放原请求。"),
    context: PublicAgentContext = Depends(require_public_context),
    db: AsyncSession = Depends(get_db),
):
    """回执仅证明持久接收；排队时通过 Input 找到固定 Turn 归属。"""
    return event_receipt(await get_receipt_snapshot(db=db, scope=context.scope, thread_id=session_id, idempotency_key=idempotency_key))


@router.get("/sessions/{session_id}/turns", summary="分页读取轮次", response_model=TurnList)
async def list_public_turns(
    session_id: str,
    after: str | None = Query(default=None, description="上一页 last_id；必须属于当前 Session。"),
    limit: int = Query(default=20, ge=1, le=100),
    order: Literal["asc", "desc"] = Query(default="desc"),
    context: PublicAgentContext = Depends(require_public_context),
    db: AsyncSession = Depends(get_db),
):
    """返回轮次摘要；按具体 ID 读取详情与最终输出。"""
    return await list_turn_page(db=db, scope=context.scope, thread_id=session_id, after=after, limit=limit, order=order)


@router.get("/sessions/{session_id}/audits")
async def retrieve_public_audits(
    session_id: str,
    context: PublicAgentContext = Depends(require_public_context),
    db: AsyncSession = Depends(get_db),
):
    """读取当前 Thread 的有界模型与工具审计。"""
    return await get_thread_audits(db=db, scope=context.scope, thread_id=session_id)


@router.get("/sessions/{session_id}/runs/{run_id}")
async def retrieve_public_run(
    session_id: str,
    run_id: str,
    context: PublicAgentContext = Depends(require_public_context),
    db: AsyncSession = Depends(get_db),
):
    """按 Thread 作用域读取指定执行段。"""
    return await get_run_snapshot(db=db, scope=context.scope, thread_id=session_id, run_id=run_id)


@router.get("/sessions/{session_id}/inputs/{input_id}", summary="读取输入消费归属", response_model=InputResponse)
async def retrieve_public_input(
    session_id: str,
    input_id: str,
    context: PublicAgentContext = Depends(require_public_context),
    db: AsyncSession = Depends(get_db),
):
    """断线后按 Input ID 查询固定消费归属。"""
    return await get_input_snapshot(db=db, scope=context.scope, thread_id=session_id, input_id=input_id)


@router.get("/sessions/{session_id}/turns/{turn_id}", summary="读取本轮状态与最终结果", response_model=TurnResponse)
async def retrieve_public_turn(
    session_id: str,
    turn_id: str,
    context: PublicAgentContext = Depends(require_public_context),
    db: AsyncSession = Depends(get_db),
):
    """读取持久 Turn 的状态、等待点、执行段和明确输出。

    completed/failed/cancelled 是整轮终态；requires_action 表示需要人工响应。
    协作 waitpoint 的状态为 in_progress。
    output 只来自 result_run_id 指向的顶层 Run。模型正文 done 或 Run interrupted/yielded 不证明完成。
    """
    result = await get_turn_snapshot(db=db, scope=context.scope, thread_id=session_id, turn_id=turn_id)
    return {
        **result["core"],
        "yuxi": {key: result[key] for key in ("current_run_id", "result_run_id", "waitpoint", "runs", "output", "usage")},
    }


@router.get("/sessions/{session_id}/turns/{turn_id}/items", summary="分页读取本轮公开内容", response_model=ItemList)
async def list_public_turn_items(
    session_id: str,
    turn_id: str,
    after: str | None = Query(default=None, description="上一页 last_id；必须属于当前 Turn。"),
    limit: int = Query(default=20, ge=1, le=100),
    order: Literal["asc", "desc"] = Query(default="desc"),
    context: PublicAgentContext = Depends(require_public_context),
    db: AsyncSession = Depends(get_db),
):
    """按稳定 item ID 分页读取本轮的公开输入和输出。"""
    return await list_session_items(
        db=db,
        scope=context.scope,
        thread_id=session_id,
        turn_id=turn_id,
        after=after,
        limit=limit,
        order=order,
    )
