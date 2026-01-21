from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import TaskRecord


class TaskRepository:
    async def get_by_id(self, task_id: str) -> TaskRecord | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(TaskRecord).where(TaskRecord.id == task_id))
            return result.scalar_one_or_none()

    async def list(self, status: str | None = None, limit: int = 100) -> list[TaskRecord]:
        async with pg_manager.get_async_session_context() as session:
            stmt = select(TaskRecord)
            if status:
                stmt = stmt.where(TaskRecord.status == status)
            stmt = stmt.order_by(TaskRecord.created_at.desc()).limit(max(limit, 0))
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list_all(self) -> list[TaskRecord]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(TaskRecord).order_by(TaskRecord.created_at.desc()))
            return list(result.scalars().all())

    async def upsert(self, task_id: str, data: dict[str, Any]) -> TaskRecord:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(TaskRecord).where(TaskRecord.id == task_id))
            record = result.scalar_one_or_none()
            if record is None:
                record = TaskRecord(id=task_id, **data)
                session.add(record)
                return record
            for key, value in data.items():
                setattr(record, key, value)
            return record

    async def delete_all(self) -> None:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(delete(TaskRecord))

