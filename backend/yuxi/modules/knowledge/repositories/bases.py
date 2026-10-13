from __future__ import annotations

from typing import Any

from sqlalchemy import String, cast, func, literal, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.modules.identity.repositories.resource_grants import validate_shared_grants
from yuxi.modules.knowledge.base import KBNameConflictError
from yuxi.modules.knowledge.cache import cache_kb_config, delete_cached_kb_config, kb_config_cache_lock
from yuxi.modules.knowledge.models import KnowledgeBase, KnowledgeFile, KnowledgeProjectionOutbox
from yuxi.shared.datetime import utc_now


class KnowledgeBaseRepository:
    async def name_exists(self, name: str) -> bool:
        """按有效名称唯一索引检查重名，不读取知识库全表。"""
        async with pg_manager.get_async_session_context() as session:
            return bool(
                await session.scalar(
                    select(
                        select(KnowledgeBase.id)
                        .where(
                            func.lower(KnowledgeBase.name) == name.lower(),
                            KnowledgeBase.deleted_at.is_(None),
                        )
                        .exists()
                    )
                )
            )

    async def mark_deleted(self, kb_id: str) -> None:
        """原子隐藏知识库与文件，批量登记幂等外部清理意图。"""
        async with kb_config_cache_lock(kb_id):
            await delete_cached_kb_config(kb_id)
            async with pg_manager.get_async_session_context() as session:
                kb = await session.scalar(select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id).with_for_update())
                if kb is None:
                    return
                kb.deleted_at = kb.deleted_at or utc_now()
                await session.execute(
                    insert(KnowledgeProjectionOutbox)
                    .values(
                        event_key=f"knowledge_base:{kb_id}:deleted",
                        kb_id=kb_id,
                        aggregate_id=kb_id,
                        generation=1,
                        operation="knowledge_base_deleted",
                    )
                    .on_conflict_do_nothing(index_elements=["event_key"])
                )
                # UPDATE 的行锁保持到 outbox INSERT 完成；只有目标 KB 的文件参与事务。
                await session.execute(
                    update(KnowledgeFile)
                    .where(KnowledgeFile.kb_id == kb_id)
                    .values(
                        deleted_at=func.coalesce(KnowledgeFile.deleted_at, utc_now()),
                        status="deleted",
                        projection_status="pending",
                        projection_error=None,
                    )
                )
                generation = func.coalesce(KnowledgeFile.generation, 1)
                await session.execute(
                    insert(KnowledgeProjectionOutbox)
                    .from_select(
                        ["event_key", "kb_id", "aggregate_id", "generation", "operation"],
                        select(
                            literal("file:") + KnowledgeFile.file_id + ":g" + cast(generation, String) + ":deleted",
                            KnowledgeFile.kb_id,
                            KnowledgeFile.file_id,
                            generation,
                            literal("file_deleted"),
                        ).where(KnowledgeFile.kb_id == kb_id),
                    )
                    .on_conflict_do_nothing(index_elements=["event_key"])
                )

    async def count_by_type(self) -> list[tuple[str, int]]:
        """按知识库类型聚合数量。"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(KnowledgeBase.kb_type, func.count(KnowledgeBase.id)).group_by(KnowledgeBase.kb_type))
            return [(str(kb_type or "unknown"), int(count or 0)) for kb_type, count in result.all()]

    async def get_all(self) -> list[KnowledgeBase]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(KnowledgeBase).where(KnowledgeBase.deleted_at.is_(None)))
            return list(result.scalars().all())

    async def get_by_kb_id(self, kb_id: str, *, include_deleted: bool = False) -> KnowledgeBase | None:
        filters = [KnowledgeBase.kb_id == kb_id]
        if not include_deleted:
            filters.append(KnowledgeBase.deleted_at.is_(None))
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(KnowledgeBase).where(*filters))
            return result.scalar_one_or_none()

    async def create(self, data: dict[str, Any]) -> KnowledgeBase:
        kb = KnowledgeBase(**data)
        try:
            async with pg_manager.get_async_session_context() as session:
                kb.share_config = await validate_shared_grants(session, kb.share_config)
                session.add(kb)
        except IntegrityError as error:
            if getattr(error.orig.__cause__, "constraint_name", None) != "uq_knowledge_bases_active_name":
                raise
            raise KBNameConflictError(f"知识库名称 '{kb.name}' 已存在，请使用其他名称") from error
        await cache_kb_config(kb)
        return kb

    async def update(self, kb_id: str, data: dict[str, Any]) -> KnowledgeBase | None:
        async with kb_config_cache_lock(kb_id):
            # 先可靠清除旧值；失败时不进入数据库事务。
            await delete_cached_kb_config(kb_id)
            try:
                async with pg_manager.get_async_session_context() as session:
                    result = await session.execute(select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id))
                    kb = result.scalar_one_or_none()
                    if kb is None:
                        return None
                    if "share_config" in data:
                        data = {**data, "share_config": await validate_shared_grants(session, data["share_config"])}
                    for key, value in data.items():
                        setattr(kb, key, value)
            except IntegrityError as error:
                if getattr(error.orig.__cause__, "constraint_name", None) != "uq_knowledge_bases_active_name":
                    raise
                raise KBNameConflictError(f"知识库名称 '{data.get('name')}' 已存在，请使用其他名称") from error
            return kb

    async def merge_query_params_options(self, kb_id: str, params: dict[str, Any]) -> KnowledgeBase | None:
        """在行锁内合并知识库查询参数，避免并发部分更新互相覆盖。"""
        async with kb_config_cache_lock(kb_id):
            await delete_cached_kb_config(kb_id)
            async with pg_manager.get_async_session_context() as session:
                statement = select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id).with_for_update()
                result = await session.execute(statement)
                kb = result.scalar_one_or_none()
                if kb is None:
                    return None

                query_params = dict(kb.query_params or {})
                options = dict(query_params.get("options") or {})
                options.update(params)
                query_params["options"] = options
                kb.query_params = query_params
            return kb

    async def refresh_stats(self, kb_id: str) -> KnowledgeBase | None:
        """在行锁内从文件聚合刷新统计，保留其他附加参数。"""
        from yuxi.modules.knowledge.repositories.files import KnowledgeFileRepository

        async with kb_config_cache_lock(kb_id):
            async with pg_manager.get_async_session_context() as session:
                statement = select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id).with_for_update()
                result = await session.execute(statement)
                kb = result.scalar_one_or_none()
                if kb is None:
                    return None

                # 聚合必须在取得行锁后执行，避免较早的快照晚写覆盖新结果。
                stats = await KnowledgeFileRepository().query_kb_file_stats(kb_id, session=session)
                additional_params = dict(kb.additional_params or {})
                additional_params["stats"] = stats
                kb.additional_params = additional_params
            return kb

    async def purge(self, kb_id: str) -> None:
        async with kb_config_cache_lock(kb_id):
            await delete_cached_kb_config(kb_id)
            async with pg_manager.get_async_session_context() as session:
                result = await session.execute(select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id))
                kb = result.scalar_one_or_none()
                if kb is not None:
                    await session.delete(kb)
