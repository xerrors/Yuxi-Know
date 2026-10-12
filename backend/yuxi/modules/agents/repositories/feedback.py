"""反馈的作用域查询与当前值写入。"""

from yuxi.modules.agents.repositories.pagination import order_page

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.modules.agents.models.definitions import Agent
from yuxi.modules.agents.models.feedback import AgentFeedbackRecord
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.agents.scope import ActorScope
from yuxi.shared.datetime import utc_now


class AgentFeedbackRepository:
    """在 service 持有的事务与 Session/Run 锁内操作反馈。"""

    def __init__(self, db: AsyncSession):
        """绑定用例事务。"""
        self.db = db

    async def get(self, *, run_id: str, source: str, tool_call_id: str | None = None) -> AgentFeedbackRecord | None:
        """读取已经通过用例授权的目标记录。"""
        return await self.db.scalar(
            select(AgentFeedbackRecord).where(
                AgentFeedbackRecord.run_id == run_id,
                AgentFeedbackRecord.source == source,
                AgentFeedbackRecord.tool_call_id == tool_call_id,
            )
        )

    async def save_user(self, *, run_id: str, rating: str, reason: str | None) -> AgentFeedbackRecord:
        """同一 Session 锁内更新当前评价，重复完整状态保持原时间。"""
        record = await self.get(run_id=run_id, source="user")
        if record is None:
            record = AgentFeedbackRecord(run_id=run_id, source="user", rating=rating, reason=reason)
            self.db.add(record)
        elif (record.rating, record.reason) != (rating, reason):
            record.rating = rating
            record.reason = reason
            record.updated_at = utc_now()
        await self.db.flush()
        return record

    async def remove_user(self, run_id: str) -> None:
        """撤销当前用户评价，保留工具标记。"""
        await self.db.execute(delete(AgentFeedbackRecord).where(AgentFeedbackRecord.run_id == run_id, AgentFeedbackRecord.source == "user"))

    async def add_mark(self, *, run_id: str, tool_call_id: str, reason: str) -> AgentFeedbackRecord:
        """在执行锁内新增一条已经校验的工具标记。"""
        record = AgentFeedbackRecord(run_id=run_id, source="agent", tool_call_id=tool_call_id, reason=reason)
        self.db.add(record)
        await self.db.flush()
        return record

    async def list_page(
        self,
        *,
        scope: ActorScope,
        platform: bool = False,
        thread_id: str | None = None,
        agent_id: str | None = None,
        source: str | None = None,
        rating: str | None = None,
        run_ids: list[str] | None = None,
        after: str | None = None,
        limit: int = 50,
    ) -> dict:
        """以受限关联查询分页，游标必须属于完全相同的查询作用域。"""
        if platform and (not scope.is_superadmin or scope.api_key_id is not None or scope.app_id is not None):
            raise PermissionError("仅平台管理员可查询集中反馈")
        statement = (
            select(AgentFeedbackRecord, AgentRun.agent_slug, Agent.name, AgentRun.thread_id, AgentRun.turn_id, AgentRun.status)
            .join(AgentRun, AgentRun.id == AgentFeedbackRecord.run_id)
            .join(Session, Session.id == AgentRun.session_record_id)
            .outerjoin(Agent, Agent.slug == AgentRun.agent_slug)
            .where(Session.status.in_(("active", "archived")))
        )
        if not platform:
            statement = statement.where(
                Session.uid == scope.uid,
                Session.app_id == scope.app_id,
                AgentRun.uid == scope.uid,
                AgentRun.app_id == scope.app_id,
            )
        for column, value in (
            (Session.thread_id, thread_id),
            (AgentRun.agent_slug, agent_id),
            (AgentFeedbackRecord.source, source),
            (AgentFeedbackRecord.rating, rating),
        ):
            if value is not None:
                statement = statement.where(column == value)
        if run_ids is not None:
            statement = statement.where(AgentFeedbackRecord.run_id.in_(run_ids))
        anchor = None
        if after is not None:
            cursor = (await self.db.execute(statement.where(AgentFeedbackRecord.id == after))).first()
            if cursor is None:
                raise ValueError("after 不属于当前反馈查询")
            anchor = (cursor[0].created_at, cursor[0].id)
        statement = order_page(statement, columns=(AgentFeedbackRecord.created_at, AgentFeedbackRecord.id), anchor=anchor)
        rows = (await self.db.execute(statement.limit(limit + 1))).all()
        items = [
            {**record.to_dict(), "agent_id": slug, "agent_name": name, "session_id": thread, "turn_id": turn, "run_status": status}
            for record, slug, name, thread, turn, status in rows[:limit]
        ]
        return {"items": items, "has_more": len(rows) > limit, "last_id": items[-1]["id"] if items else None}
