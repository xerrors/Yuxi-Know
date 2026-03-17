"""Agent run repository."""

from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.storage.postgres.models_business import AgentRun
from yuxi.utils.datetime_utils import utc_now_naive

TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled", "interrupted"}


class AgentRunRepository:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def get_run(self, run_id: str) -> AgentRun | None:
        result = await self.db.execute(select(AgentRun).where(AgentRun.id == run_id))
        return result.scalar_one_or_none()

    async def get_run_by_request_id(self, request_id: str) -> AgentRun | None:
        result = await self.db.execute(select(AgentRun).where(AgentRun.request_id == request_id))
        return result.scalar_one_or_none()

    async def get_run_for_user(self, run_id: str, user_id: str) -> AgentRun | None:
        result = await self.db.execute(
            select(AgentRun).where(and_(AgentRun.id == run_id, AgentRun.user_id == str(user_id)))
        )
        return result.scalar_one_or_none()

    async def create_run(
        self,
        *,
        run_id: str,
        thread_id: str,
        agent_id: str,
        user_id: str,
        request_id: str,
        input_payload: dict,
    ) -> AgentRun:
        run = AgentRun(
            id=run_id,
            thread_id=thread_id,
            agent_id=agent_id,
            user_id=str(user_id),
            request_id=request_id,
            input_payload=input_payload or {},
            status="pending",
        )
        self.db.add(run)
        await self.db.flush()
        return run

    async def mark_running(self, run_id: str) -> AgentRun | None:
        run = await self._lock_run(run_id)
        if not run:
            return None
        if run.status in TERMINAL_RUN_STATUSES:
            return run
        now = utc_now_naive()
        run.status = "running"
        run.started_at = run.started_at or now
        run.updated_at = now
        await self.db.flush()
        return run

    async def request_cancel(self, run_id: str) -> AgentRun | None:
        run = await self._lock_run(run_id)
        if not run:
            return None
        if run.status in TERMINAL_RUN_STATUSES:
            return run
        run.status = "cancel_requested"
        run.updated_at = utc_now_naive()
        await self.db.flush()
        return run

    async def set_terminal_status(
        self,
        run_id: str,
        *,
        status: str,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> AgentRun | None:
        run = await self._lock_run(run_id)
        if not run:
            return None
        if run.status in TERMINAL_RUN_STATUSES:
            return run
        run.status = status
        run.error_type = error_type
        run.error_message = error_message
        run.finished_at = utc_now_naive()
        run.updated_at = run.finished_at
        await self.db.flush()
        return run

    async def _lock_run(self, run_id: str) -> AgentRun | None:
        result = await self.db.execute(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
        return result.scalar_one_or_none()
