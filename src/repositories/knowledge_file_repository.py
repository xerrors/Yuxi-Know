from __future__ import annotations

from typing import Any

from sqlalchemy import select

from src.storage.postgres.manager import pg_manager
from src.storage.db.models_knowledge import KnowledgeFile


class KnowledgeFileRepository:
    async def get_all(self) -> list[KnowledgeFile]:
        """获取所有文件记录"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(KnowledgeFile))
            return list(result.scalars().all())

    async def get_by_file_id(self, file_id: str) -> KnowledgeFile | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(KnowledgeFile).where(KnowledgeFile.file_id == file_id))
            return result.scalar_one_or_none()

    async def list_by_db_id(self, db_id: str) -> list[KnowledgeFile]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(KnowledgeFile).where(KnowledgeFile.db_id == db_id))
            return list(result.scalars().all())

    async def upsert(self, file_id: str, data: dict[str, Any]) -> KnowledgeFile:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(KnowledgeFile).where(KnowledgeFile.file_id == file_id))
            existing = result.scalar_one_or_none()
            if existing is None:
                record = KnowledgeFile(file_id=file_id, **data)
                session.add(record)
                return record
            for key, value in data.items():
                setattr(existing, key, value)
            return existing

    async def delete(self, file_id: str) -> None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(KnowledgeFile).where(KnowledgeFile.file_id == file_id))
            record = result.scalar_one_or_none()
            if record is not None:
                await session.delete(record)

    async def delete_by_db_id(self, db_id: str) -> None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(KnowledgeFile).where(KnowledgeFile.db_id == db_id))
            for record in result.scalars().all():
                await session.delete(record)
