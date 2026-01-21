from __future__ import annotations

from typing import Any

from sqlalchemy import select

from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_knowledge import KnowledgeBase


class KnowledgeBaseRepository:
    async def get_all(self) -> list[KnowledgeBase]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(KnowledgeBase))
            return list(result.scalars().all())

    async def get_by_id(self, db_id: str) -> KnowledgeBase | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(KnowledgeBase).where(KnowledgeBase.db_id == db_id))
            return result.scalar_one_or_none()

    async def create(self, data: dict[str, Any]) -> KnowledgeBase:
        kb = KnowledgeBase(**data)
        async with pg_manager.get_async_session_context() as session:
            session.add(kb)
        return kb

    async def update(self, db_id: str, data: dict[str, Any]) -> KnowledgeBase | None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(KnowledgeBase).where(KnowledgeBase.db_id == db_id))
            kb = result.scalar_one_or_none()
            if kb is None:
                return None
            for key, value in data.items():
                setattr(kb, key, value)
        return kb

    async def delete(self, db_id: str) -> None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(KnowledgeBase).where(KnowledgeBase.db_id == db_id))
            kb = result.scalar_one_or_none()
            if kb is not None:
                await session.delete(kb)
