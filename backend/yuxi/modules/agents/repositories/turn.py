"""Turn 状态、执行关联与结果查询。"""

from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from yuxi.modules.agents.models.inputs import AgentInput
from yuxi.modules.agents.models.messages import MODEL_AUDIT_MESSAGE_TYPE, Message
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.shared.datetime import utc_now


class AgentTurnRepository:
    """在调用方事务内维护整轮状态。"""

    def __init__(self, db: AsyncSession):
        """绑定调用方持有的事务。"""
        self.db = db

    async def create(self, *, turn_id: str, thread_id: str, uid: str, app_id: str | None) -> AgentTurn:
        """领取 follow-up 时建立 running Turn。"""
        turn = AgentTurn(id=turn_id, thread_id=thread_id, uid=uid, app_id=app_id, status="running")
        self.db.add(turn)
        await self.db.flush()
        return turn

    async def get(self, turn_id: str) -> AgentTurn | None:
        """按 ID 读取 Turn。"""
        return await self.db.get(AgentTurn, turn_id)

    async def list_current_views(self, *, thread_ids: list[str], uid: str, app_id: str | None) -> dict:
        """批量读取最新 Turn、当前 Run 与队列数量，供完整资源投影。"""
        latest = (
            select(AgentTurn)
            .where(AgentTurn.thread_id.in_(thread_ids), AgentTurn.uid == uid, AgentTurn.app_id == app_id)
            .distinct(AgentTurn.thread_id)
            .order_by(AgentTurn.thread_id, AgentTurn.created_at.desc(), AgentTurn.id.desc())
            .subquery()
        )
        from sqlalchemy.orm import aliased

        turn = aliased(AgentTurn, latest)
        pending = (
            select(AgentInput.thread_id, func.count().label("count"))
            .where(
                AgentInput.thread_id.in_(thread_ids),
                AgentInput.uid == uid,
                AgentInput.app_id == app_id,
                AgentInput.status == "pending",
            )
            .group_by(AgentInput.thread_id)
            .subquery()
        )
        rows = (
            await self.db.execute(
                select(Session.thread_id, turn, AgentRun, func.coalesce(pending.c.count, 0))
                .options(defer(AgentRun.input_payload), defer(AgentRun.manifest), defer(AgentRun.origin_metadata))
                .outerjoin(turn, turn.thread_id == Session.thread_id)
                .outerjoin(AgentRun, AgentRun.id == turn.current_run_id)
                .outerjoin(pending, pending.c.thread_id == Session.thread_id)
                .where(Session.thread_id.in_(thread_ids), Session.uid == uid, Session.app_id == app_id)
            )
        ).all()
        return {thread_id: (item, run, count) for thread_id, item, run, count in rows}

    async def get_start_times(self, *, turn_ids: list[str], uid: str, app_id: str | None) -> dict:
        """批量读取每轮第一次执行时间，恢复 Run 不改变轮次起点。"""
        rows = await self.db.execute(
            select(AgentRun.turn_id, func.min(AgentRun.started_at))
            .where(AgentRun.turn_id.in_(turn_ids), AgentRun.uid == uid, AgentRun.app_id == app_id)
            .group_by(AgentRun.turn_id)
        )
        return dict(rows.all())

    async def get_for_scope(
        self, *, turn_id: str, thread_id: str, uid: str, app_id: str | None, for_update: bool = False
    ) -> AgentTurn | None:
        """按完整线程作用域读取或锁定 Turn。"""
        statement = select(AgentTurn).where(
            AgentTurn.id == turn_id,
            AgentTurn.thread_id == thread_id,
            AgentTurn.uid == uid,
            AgentTurn.app_id == app_id,
        )
        if for_update:
            statement = statement.with_for_update(key_share=True)
        result = await self.db.execute(statement.execution_options(populate_existing=for_update))
        return result.scalar_one_or_none()

    async def list_for_scope(self, *, turn_ids: list[str], thread_id: str, uid: str, app_id: str | None) -> dict:
        """批量读取订阅执行段所属轮次，避免逐执行段往返查询。"""
        turns = (
            await self.db.scalars(
                select(AgentTurn).where(
                    AgentTurn.id.in_(turn_ids),
                    AgentTurn.thread_id == thread_id,
                    AgentTurn.uid == uid,
                    AgentTurn.app_id == app_id,
                )
            )
        ).all()
        return {turn.id: turn for turn in turns}

    async def lock_active_for_thread(self, *, thread_id: str, uid: str, app_id: str | None) -> AgentTurn | None:
        """按 Thread→Turn 锁顺序锁定唯一活跃轮次。"""
        result = await self.db.execute(
            select(AgentTurn)
            .where(
                AgentTurn.thread_id == thread_id,
                AgentTurn.uid == uid,
                AgentTurn.app_id == app_id,
                AgentTurn.status.in_(("running", "waiting", "cancelling")),
            )
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_active_for_thread(self, *, thread_id: str, uid: str, app_id: str | None) -> AgentTurn | None:
        """只读当前活跃 Turn，不取得调度锁。"""
        result = await self.db.execute(
            select(AgentTurn).where(
                AgentTurn.thread_id == thread_id,
                AgentTurn.uid == uid,
                AgentTurn.app_id == app_id,
                AgentTurn.status.in_(("running", "waiting", "cancelling")),
            )
        )
        return result.scalar_one_or_none()

    async def list_page(
        self,
        *,
        thread_id: str,
        uid: str,
        app_id: str | None,
        after: str | None,
        limit: int,
        order: str,
    ) -> list:
        """按创建时间与 ID 分页轮次，同时读取当前执行段。"""
        from sqlalchemy import tuple_

        statement = (
            select(AgentTurn, AgentRun)
            .options(defer(AgentRun.input_payload), defer(AgentRun.manifest), defer(AgentRun.origin_metadata))
            .outerjoin(AgentRun, AgentRun.id == AgentTurn.current_run_id)
            .where(
                AgentTurn.thread_id == thread_id,
                AgentTurn.uid == uid,
                AgentTurn.app_id == app_id,
            )
        )
        if after is not None:
            cursor = await self.get_for_scope(turn_id=after, thread_id=thread_id, uid=uid, app_id=app_id)
            if cursor is None:
                raise ValueError("after 不是当前 Session 的 Turn")
            position = tuple_(AgentTurn.created_at, AgentTurn.id)
            boundary = tuple_(cursor.created_at, cursor.id)
            statement = statement.where(position > boundary if order == "asc" else position < boundary)
        sorting = (AgentTurn.created_at.asc(), AgentTurn.id.asc()) if order == "asc" else (AgentTurn.created_at.desc(), AgentTurn.id.desc())
        return list((await self.db.execute(statement.order_by(*sorting).limit(limit + 1))).all())

    async def set_current(self, turn: AgentTurn, *, run_id: str) -> AgentTurn:
        """将同一 Turn 的新顶层 Run 设为当前执行。"""
        run = await self.db.get(AgentRun, run_id)
        if run is None or run.turn_id != turn.id:
            raise ValueError("当前 Run 不属于目标 Turn")
        if turn.status not in {"running", "waiting"}:
            raise ValueError("Turn 当前状态不能接续执行")
        turn.current_run_id = run_id
        turn.waitpoint = None
        turn.status = "running"
        await self.db.flush()
        return turn

    async def set_waiting(self, turn: AgentTurn, *, run_id: str, waitpoint: dict) -> AgentTurn:
        """记录明确等待点及其 interrupted Run。"""
        if turn.status != "running" or turn.current_run_id != run_id or not waitpoint:
            raise ValueError("Turn 的等待目标与当前执行不一致")
        turn.status = "waiting"
        turn.waitpoint = waitpoint
        await self.db.flush()
        return turn

    async def set_cancelling(self, turn: AgentTurn) -> AgentTurn:
        """保留执行清理期间的占用状态。"""
        if turn.status not in {"running", "waiting", "cancelling"}:
            raise ValueError("Turn 已经结束")
        turn.status = "cancelling"
        await self.db.flush()
        return turn

    async def set_terminal(self, turn: AgentTurn, *, status: str, result_run_id: str | None = None) -> AgentTurn:
        """在 owning transaction 内固定最终状态及顶层结果 Run。"""
        if status not in {"completed", "failed", "cancelled"}:
            raise ValueError("不支持的 Turn 终态")
        if turn.status not in {"running", "waiting", "cancelling"}:
            raise ValueError("Turn 已经结束")
        if status == "completed":
            run = await self.db.get(AgentRun, result_run_id)
            if run is None or run.turn_id != turn.id or run.status != "completed":
                raise ValueError("Turn 结果必须来自已完成的本轮顶层 Run")
        elif result_run_id is not None:
            raise ValueError("非完成 Turn 不能指定结果 Run")
        now = utc_now()
        turn.status = status
        turn.result_run_id = result_run_id
        turn.waitpoint = None
        turn.finished_at = now
        if status == "cancelled":
            turn.cancelled_at = now
        await self.db.flush()
        return turn

    async def set_langfuse_root_observation_id(self, turn: AgentTurn, observation_id: str) -> AgentTurn:
        """仅首次固化跨 Run 共用的根观察 ID。"""
        if turn.langfuse_root_observation_id not in (None, observation_id):
            raise ValueError("Turn 已绑定不同的根观察 ID")
        turn.langfuse_root_observation_id = observation_id
        await self.db.flush()
        return turn

    async def list_runs(self, turn_id: str) -> list[AgentRun]:
        """只读取明确绑定的顶层执行段。"""
        result = await self.db.execute(select(AgentRun).where(AgentRun.turn_id == turn_id).order_by(AgentRun.execution_seq, AgentRun.id))
        return list(result.scalars())

    async def list_model_usage_audits(self, turn_id: str) -> list[Message]:
        """合并 Model 审计与显式绑定的最终输出，每个操作只保留最新事实。"""
        bound_output = (
            select(AgentRun.id)
            .where(
                AgentRun.turn_id == turn_id,
                AgentRun.output_message_id == Message.id,
                AgentRun.id == Message.run_id,
                AgentRun.session_record_id == Message.session_record_id,
            )
            .exists()
        )
        result = await self.db.execute(
            select(Message)
            .where(
                Message.turn_id == turn_id,
                Message.role == "assistant",
                or_(
                    Message.message_type == MODEL_AUDIT_MESSAGE_TYPE,
                    and_(Message.operation_id.is_not(None), bound_output),
                ),
            )
            .order_by(Message.id.desc())
        )
        latest = {}
        for message in result.scalars():
            key = (message.run_id, message.operation_id) if message.operation_id else (message.run_id, message.id)
            latest.setdefault(key, message)
        return list(reversed(latest.values()))
