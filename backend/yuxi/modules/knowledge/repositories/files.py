from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

from sqlalchemy import DateTime, String, case, cast, func, literal, or_, select, union_all, update
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.infrastructure.observability.logging import logger
from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.modules.background_jobs.models import BackgroundJobRecord
from yuxi.modules.knowledge.models import KnowledgeBase, KnowledgeFile, KnowledgeProjectionOutbox
from yuxi.shared.datetime import utc_now

# asyncpg 单条 SQL 参数上限为 32767；按 file_id 批量查询时统一分批。
SQL_IN_BATCH_SIZE = 10_000

# 文件统计聚合缓存 TTL：列表页高频请求时避免反复全表聚合；文件增删后最多延迟该时长更新
KB_FILE_STATS_CACHE_TTL = 10


class KnowledgeFileRepository:
    @staticmethod
    def normalize_path_prefix(path_prefix: str | None) -> str:
        """规范化文档目录前缀，拒绝绝对路径和父目录引用。"""
        if not path_prefix:
            return ""
        normalized = path_prefix.strip().replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        if normalized.startswith("/"):
            raise ValueError("path_prefix must be relative")

        parts = [part for part in normalized.split("/") if part and part != "."]
        if any(part == ".." for part in parts):
            raise ValueError("path_prefix must not contain parent directory references")
        if not parts:
            return ""
        return "/".join(parts) + "/"

    @asynccontextmanager
    async def lock_file_tree(self, kb_id: str) -> AsyncIterator[None]:
        """按知识库串行化目录树结构修改。"""
        async with pg_manager.get_async_session_context() as session:
            await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(kb_id))))
            yield

    async def aggregate_dashboard_stats(self) -> list[tuple[str, int, int, int]]:
        """按文件类型聚合真实文件数、大小与 Chunk 数。"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(
                    KnowledgeFile.file_type,
                    func.count(KnowledgeFile.file_id),
                    func.coalesce(func.sum(KnowledgeFile.file_size), 0),
                    func.coalesce(func.sum(KnowledgeFile.chunk_count), 0),
                )
                .where(
                    KnowledgeFile.deleted_at.is_(None),
                    or_(KnowledgeFile.is_folder.is_(False), KnowledgeFile.is_folder.is_(None)),
                )
                .group_by(KnowledgeFile.file_type)
            )
            return [
                (str(file_type or "unknown"), int(count or 0), int(size or 0), int(nodes or 0))
                for file_type, count, size, nodes in result.all()
            ]

    _writable_fields = {
        "kb_id",
        "parent_id",
        "filename",
        "original_filename",
        "file_type",
        "path",
        "minio_url",
        "markdown_file",
        "status",
        "content_hash",
        "file_size",
        "chunk_count",
        "token_count",
        "content_type",
        "processing_params",
        "is_folder",
        "error_message",
        "processing_job_id",
        "processing_owner",
        "created_by",
        "updated_by",
        "generation",
        "active_generation",
        "building_generation",
        "deleted_at",
        "projection_status",
        "projection_error",
    }

    @staticmethod
    def _iter_batches(items: list[str], batch_size: int = SQL_IN_BATCH_SIZE) -> Iterator[list[str]]:
        for index in range(0, len(items), batch_size):
            yield items[index : index + batch_size]

    @classmethod
    def _sanitize_data(cls, data: dict[str, Any]) -> dict[str, Any]:
        sanitized = {key: value for key, value in data.items() if key in cls._writable_fields}
        if sanitized:
            sanitized["updated_at"] = utc_now()
        return sanitized

    async def get_by_file_id(self, file_id: str, *, include_deleted: bool = False) -> KnowledgeFile | None:
        filters = [KnowledgeFile.file_id == file_id]
        if not include_deleted:
            filters.append(KnowledgeFile.deleted_at.is_(None))
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(KnowledgeFile).where(*filters))
            return result.scalar_one_or_none()

    async def list_active_generations(self, kb_id: str) -> list[tuple[str, int]]:
        """只读取可见文件的 active 代次，供向量库在截取 top-k 前过滤。"""
        async with pg_manager.get_async_session_context() as session:
            rows = await session.execute(
                select(KnowledgeFile.file_id, KnowledgeFile.active_generation)
                .join(KnowledgeBase, KnowledgeBase.kb_id == KnowledgeFile.kb_id)
                .where(
                    KnowledgeFile.kb_id == kb_id,
                    KnowledgeFile.deleted_at.is_(None),
                    KnowledgeBase.deleted_at.is_(None),
                    KnowledgeFile.is_folder.is_(False),
                )
            )
            return [(row.file_id, int(row.active_generation)) for row in rows]

    async def list_by_kb_id(self, kb_id: str) -> list[KnowledgeFile]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(KnowledgeFile).where(KnowledgeFile.kb_id == kb_id, KnowledgeFile.deleted_at.is_(None)))
            return list(result.scalars().all())

    async def search_files(
        self,
        *,
        kb_id: str,
        filename_query: str | None = None,
        statuses: set[str] | None = None,
        offset: int = 0,
        limit: int = 100,
        files_only: bool = True,
    ) -> tuple[list[KnowledgeFile], int]:
        filters = [KnowledgeFile.kb_id == kb_id, KnowledgeFile.deleted_at.is_(None)]
        if files_only:
            filters.append(KnowledgeFile.is_folder.is_(False))
        if statuses is not None:
            filters.append(KnowledgeFile.status.in_(statuses))

        normalized_query = (filename_query or "").strip().lower()
        if normalized_query:
            escaped_query = normalized_query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            filters.append(func.lower(KnowledgeFile.filename).like(f"%{escaped_query}%", escape="\\"))

        normalized_offset = max(int(offset or 0), 0)
        normalized_limit = min(max(int(limit or 100), 1), 10_000)

        async with pg_manager.get_async_session_context() as session:
            total_result = await session.execute(select(func.count()).select_from(KnowledgeFile).where(*filters))
            total = int(total_result.scalar_one() or 0)
            result = await session.execute(
                select(KnowledgeFile)
                .where(*filters)
                .order_by(KnowledgeFile.updated_at.desc(), KnowledgeFile.file_id.asc())
                .offset(normalized_offset)
                .limit(normalized_limit)
            )
            return list(result.scalars().all()), total

    async def get_chunk_sources_by_file_ids(self, *, kb_id: str, file_ids: list[str]) -> dict[str, dict]:
        """批量读取检索分片的文件来源与总分片数。"""
        normalized_ids = [file_id for file_id in file_ids if file_id]
        if not normalized_ids:
            return {}

        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(
                    KnowledgeFile.file_id,
                    KnowledgeFile.filename,
                    KnowledgeFile.chunk_count,
                    KnowledgeFile.active_generation,
                ).where(
                    KnowledgeFile.kb_id == kb_id,
                    KnowledgeFile.deleted_at.is_(None),
                    KnowledgeFile.file_id.in_(normalized_ids),
                )
            )
            return {
                str(file_id): {
                    "source": str(filename or ""),
                    "chunk_count": int(chunk_count or 0),
                    "active_generation": int(active_generation or 1),
                }
                for file_id, filename, chunk_count, active_generation in result.all()
            }

    async def list_children(self, *, kb_id: str, parent_id: str | None) -> list[KnowledgeFile]:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(KnowledgeFile)
                .where(
                    KnowledgeFile.kb_id == kb_id,
                    KnowledgeFile.deleted_at.is_(None),
                    self._parent_condition(parent_id),
                )
                .order_by(KnowledgeFile.is_folder.desc(), func.lower(KnowledgeFile.filename).asc())
            )
            return list(result.scalars().all())

    async def list_same_name_files(self, *, kb_id: str, filename: str) -> list[KnowledgeFile]:
        normalized_filename = filename.strip()
        if not normalized_filename:
            return []

        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(KnowledgeFile)
                .where(
                    KnowledgeFile.kb_id == kb_id,
                    KnowledgeFile.is_folder.is_(False),
                    KnowledgeFile.deleted_at.is_(None),
                    func.lower(KnowledgeFile.filename) == normalized_filename.lower(),
                    or_(KnowledgeFile.status.is_(None), KnowledgeFile.status != "failed"),
                )
                .order_by(KnowledgeFile.created_at.desc())
            )
            return list(result.scalars().all())

    async def list_file_ids_by_filename_contains(
        self,
        *,
        kb_id: str,
        filename_pattern: str,
        limit: int = 10_000,
    ) -> list[str]:
        normalized_pattern = filename_pattern.replace("%", "").strip().lower()
        if not normalized_pattern:
            return []

        escaped_pattern = normalized_pattern.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(KnowledgeFile.file_id)
                .where(
                    KnowledgeFile.kb_id == kb_id,
                    KnowledgeFile.is_folder.is_(False),
                    KnowledgeFile.deleted_at.is_(None),
                    func.lower(KnowledgeFile.filename).like(f"%{escaped_pattern}%", escape="\\"),
                )
                .order_by(KnowledgeFile.file_id.asc())
                .limit(min(max(int(limit or 100), 1), 10_000))
            )
            return [str(file_id) for file_id in result.scalars().all()]

    async def exists_by_content_hash(self, *, kb_id: str, content_hash: str) -> bool:
        normalized_hash = content_hash.strip()
        if not normalized_hash:
            return False

        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(KnowledgeFile.file_id)
                .where(
                    KnowledgeFile.kb_id == kb_id,
                    KnowledgeFile.is_folder.is_(False),
                    KnowledgeFile.content_hash == normalized_hash,
                    KnowledgeFile.deleted_at.is_(None),
                    or_(KnowledgeFile.status.is_(None), KnowledgeFile.status != "failed"),
                )
                .limit(1)
            )
            return result.scalar_one_or_none() is not None

    async def count_all(self) -> int:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(func.count()).select_from(KnowledgeFile).where(KnowledgeFile.deleted_at.is_(None)))
            return int(result.scalar() or 0)

    async def list_file_ids_by_exact_statuses(
        self,
        *,
        kb_id: str,
        statuses: list[str],
        after_file_id: str | None = None,
        limit: int = 500,
    ) -> list[str]:
        normalized_statuses = [status for status in statuses if status]
        if not normalized_statuses:
            return []

        normalized_limit = min(max(int(limit or 100), 1), 500)
        filters = [
            KnowledgeFile.kb_id == kb_id,
            KnowledgeFile.is_folder.is_(False),
            KnowledgeFile.status.in_(normalized_statuses),
        ]
        if after_file_id:
            filters.append(KnowledgeFile.file_id > after_file_id)

        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(KnowledgeFile.file_id).where(*filters).order_by(KnowledgeFile.file_id.asc()).limit(normalized_limit)
            )
            return [str(file_id) for file_id in result.scalars().all()]

    async def exists_by_filename(self, *, kb_id: str, filename: str) -> bool:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(KnowledgeFile.file_id)
                .where(
                    KnowledgeFile.kb_id == kb_id,
                    KnowledgeFile.filename == filename,
                    KnowledgeFile.deleted_at.is_(None),
                    KnowledgeFile.is_folder.is_not(True),
                    or_(KnowledgeFile.status.is_(None), KnowledgeFile.status != "failed"),
                )
                .limit(1)
            )
            return result.scalar_one_or_none() is not None

    @staticmethod
    def _status_condition(status: str | None):
        if not status or status == "all":
            return None
        if status == "indexed":
            return KnowledgeFile.status.in_(["indexed", "done"])
        if status == "error_indexing":
            return KnowledgeFile.status.in_(["error_indexing", "failed"])
        return KnowledgeFile.status == status

    @staticmethod
    def _parent_condition(parent_id: str | None):
        if parent_id:
            return KnowledgeFile.parent_id == parent_id
        return KnowledgeFile.parent_id.is_(None)

    @staticmethod
    def _like_prefix(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"{escaped}%"

    def _document_filters(
        self,
        *,
        kb_id: str,
        parent_id: str | None,
        status: str | None,
        recursive: bool,
        files_only: bool,
    ) -> list:
        filters = [KnowledgeFile.kb_id == kb_id, KnowledgeFile.deleted_at.is_(None)]
        if not recursive:
            filters.append(self._parent_condition(parent_id))
        if files_only:
            filters.append(KnowledgeFile.is_folder.is_(False))

        status_condition = self._status_condition(status)
        if status_condition is not None:
            filters.append(KnowledgeFile.is_folder.is_(False))
            filters.append(status_condition)

        return filters

    async def _list_directory_documents(
        self,
        *,
        kb_id: str,
        parent_id: str | None,
        path_prefix: str,
        page: int,
        page_size: int,
        files_only: bool,
    ) -> tuple[list[Any], int]:
        offset = (page - 1) * page_size
        parent_condition = self._parent_condition(parent_id)
        base_filters = [
            KnowledgeFile.kb_id == kb_id,
            KnowledgeFile.deleted_at.is_(None),
            parent_condition,
            KnowledgeFile.filename.is_not(None),
        ]
        if path_prefix:
            base_filters.append(KnowledgeFile.filename.like(self._like_prefix(path_prefix), escape="\\"))
            remainder = func.substr(KnowledgeFile.filename, len(path_prefix) + 1)
        else:
            # 根目录直接使用 filename 表达式，匹配部分索引 idx_kf_kb_parent_segment/idx_kf_kb_parent_flat
            remainder = KnowledgeFile.filename
        immediate_name = remainder.label("filename")
        segment = func.split_part(remainder, "/", 1)
        virtual_path_prefix = (literal(path_prefix) + segment + literal("/")).label("path_prefix")
        virtual_file_id = (literal("__virtual_folder__:") + literal(parent_id or "root") + literal(":") + virtual_path_prefix).label(
            "file_id"
        )

        real_select = select(
            KnowledgeFile.file_id.label("file_id"),
            immediate_name,
            KnowledgeFile.file_type.label("file_type"),
            KnowledgeFile.status.label("status"),
            KnowledgeFile.created_at.label("created_at"),
            KnowledgeFile.updated_at.label("updated_at"),
            KnowledgeFile.file_size.label("file_size"),
            KnowledgeFile.chunk_count.label("chunk_count"),
            KnowledgeFile.token_count.label("token_count"),
            KnowledgeFile.created_by.label("created_by"),
            KnowledgeFile.is_folder.label("is_folder"),
            KnowledgeFile.parent_id.label("parent_id"),
            KnowledgeFile.path.label("path"),
            KnowledgeFile.minio_url.label("minio_url"),
            KnowledgeFile.markdown_file.label("markdown_file"),
            literal(False).label("is_virtual_folder"),
            cast(literal(None), String).label("path_prefix"),
            literal(0).label("virtual_children_count"),
        ).where(*base_filters, remainder != "", func.strpos(remainder, "/") == 0)

        virtual_select = (
            select(
                virtual_file_id,
                segment.label("filename"),
                literal("folder").label("file_type"),
                literal("done").label("status"),
                cast(literal(None), DateTime(timezone=True)).label("created_at"),
                cast(literal(None), DateTime(timezone=True)).label("updated_at"),
                literal(0).label("file_size"),
                literal(0).label("chunk_count"),
                literal(0).label("token_count"),
                cast(literal(None), String).label("created_by"),
                literal(True).label("is_folder"),
                cast(literal(parent_id), String).label("parent_id"),
                cast(literal(None), String).label("path"),
                cast(literal(None), String).label("minio_url"),
                cast(literal(None), String).label("markdown_file"),
                literal(True).label("is_virtual_folder"),
                virtual_path_prefix,
                func.count().label("virtual_children_count"),
            )
            .where(*base_filters, remainder != "", func.strpos(remainder, "/") > 0)
            .group_by(segment)
        )

        if files_only:
            directory_query = real_select.where(KnowledgeFile.is_folder.is_(False)).subquery()
        else:
            directory_query = union_all(real_select, virtual_select).subquery()

        async with pg_manager.get_async_session_context() as session:
            total_result = await session.execute(select(func.count()).select_from(directory_query))
            total = int(total_result.scalar_one() or 0)
            result = await session.execute(
                select(directory_query)
                .order_by(
                    directory_query.c.is_folder.desc(),
                    func.lower(directory_query.c.filename).asc(),
                    directory_query.c.created_at.desc().nullslast(),
                    directory_query.c.file_id.asc(),
                )
                .offset(offset)
                .limit(page_size)
            )
            return [SimpleNamespace(**dict(row)) for row in result.mappings().all()], total

    async def list_documents(
        self,
        *,
        kb_id: str,
        parent_id: str | None = None,
        path_prefix: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 100,
        recursive: bool = False,
        files_only: bool = False,
    ) -> tuple[list[KnowledgeFile], int]:
        page = max(int(page or 1), 1)
        page_size = min(max(int(page_size or 100), 1), 500)
        offset = (page - 1) * page_size
        normalized_path_prefix = self.normalize_path_prefix(path_prefix)
        has_status_filter = self._status_condition(status) is not None
        effective_recursive = recursive and has_status_filter
        if not effective_recursive and not has_status_filter:
            return await self._list_directory_documents(
                kb_id=kb_id,
                parent_id=parent_id,
                path_prefix=normalized_path_prefix,
                page=page,
                page_size=page_size,
                files_only=files_only,
            )

        filters = self._document_filters(
            kb_id=kb_id,
            parent_id=parent_id,
            status=status,
            recursive=effective_recursive,
            files_only=files_only,
        )

        async with pg_manager.get_async_session_context() as session:
            total_result = await session.execute(select(func.count()).select_from(KnowledgeFile).where(*filters))
            total = int(total_result.scalar_one() or 0)

            result = await session.execute(
                select(KnowledgeFile)
                .where(*filters)
                .order_by(
                    KnowledgeFile.is_folder.desc(),
                    func.lower(KnowledgeFile.filename).asc(),
                    KnowledgeFile.created_at.desc(),
                    KnowledgeFile.file_id.asc(),
                )
                .offset(offset)
                .limit(page_size)
            )
            return list(result.scalars().all()), total

    async def count_children_by_parent_ids(self, *, kb_id: str, parent_ids: list[str]) -> dict[str, int]:
        if not parent_ids:
            return {}

        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(KnowledgeFile.parent_id, func.count())
                .where(
                    KnowledgeFile.kb_id == kb_id,
                    KnowledgeFile.deleted_at.is_(None),
                    KnowledgeFile.parent_id.in_(parent_ids),
                )
                .group_by(KnowledgeFile.parent_id)
            )
            return {str(parent_id): int(count or 0) for parent_id, count in result.all() if parent_id}

    async def get_kb_file_stats(self, kb_id: str) -> dict[str, int]:
        """获取知识库文件统计；结果带短 TTL 缓存，避免高频列表请求反复全表聚合。"""
        from yuxi.infrastructure.redis import get_async_redis_client

        cache_key = f"yuxi:kb_file_stats:{kb_id}"
        redis_client = await get_async_redis_client()
        try:
            cached = await redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as exc:
            logger.warning(f"Failed to load kb file stats cache {cache_key}: {exc}")

        async with pg_manager.get_async_session_context() as session:
            stats = await self.query_kb_file_stats(kb_id, session=session)
        try:
            await redis_client.set(cache_key, json.dumps(stats), ex=KB_FILE_STATS_CACHE_TTL)
        except Exception as exc:
            logger.warning(f"Failed to store kb file stats cache {cache_key}: {exc}")
        return stats

    async def query_kb_file_stats(self, kb_id: str, *, session: AsyncSession) -> dict[str, int]:
        """在调用方事务中直接聚合文件统计，绕过读取缓存。"""
        non_folder = KnowledgeFile.is_folder.is_(False)
        result = await session.execute(
            select(
                func.count(KnowledgeFile.file_id).label("row_count"),
                func.sum(case((non_folder, 1), else_=0)).label("file_count"),
                func.sum(case((KnowledgeFile.is_folder.is_(True), 1), else_=0)).label("folder_count"),
                func.coalesce(func.sum(case((non_folder, KnowledgeFile.file_size), else_=0)), 0).label("total_size"),
                func.coalesce(func.sum(case((non_folder, KnowledgeFile.chunk_count), else_=0)), 0).label("chunk_count"),
                func.coalesce(func.sum(case((non_folder, KnowledgeFile.token_count), else_=0)), 0).label("token_count"),
                func.sum(case((non_folder & (KnowledgeFile.status == "uploaded"), 1), else_=0)).label("pending_parse_count"),
                func.sum(case((non_folder & KnowledgeFile.status.in_(["parsed", "error_indexing"]), 1), else_=0)).label(
                    "pending_index_count"
                ),
                func.sum(
                    case(
                        (
                            non_folder & KnowledgeFile.status.in_(["processing", "waiting", "parsing", "indexing"]),
                            1,
                        ),
                        else_=0,
                    )
                ).label("processing_count"),
            ).where(KnowledgeFile.kb_id == kb_id, KnowledgeFile.deleted_at.is_(None))
        )
        row = result.one()

        return {
            "row_count": int(row.row_count or 0),
            "file_count": int(row.file_count or 0),
            "folder_count": int(row.folder_count or 0),
            "total_size": int(row.total_size or 0),
            "chunk_count": int(row.chunk_count or 0),
            "token_count": int(row.token_count or 0),
            "pending_parse_count": int(row.pending_parse_count or 0),
            "pending_index_count": int(row.pending_index_count or 0),
            "processing_count": int(row.processing_count or 0),
        }

    async def upsert(self, file_id: str, data: dict[str, Any]) -> KnowledgeFile:
        """写入文件事实。"""
        sanitized_data = self._sanitize_data(data)
        async with pg_manager.get_async_session_context() as session:
            kb = await session.scalar(
                select(KnowledgeBase)
                .where(
                    KnowledgeBase.kb_id == sanitized_data["kb_id"],
                )
                .with_for_update()
            )
            if kb is None or kb.deleted_at is not None:
                raise ValueError("Knowledge base not found or deleted")
            result = await session.execute(select(KnowledgeFile).where(KnowledgeFile.file_id == file_id).with_for_update())
            record = result.scalar_one_or_none()
            if record is None:
                record = KnowledgeFile(file_id=file_id, **sanitized_data)
                session.add(record)
                await session.flush()
            else:
                for key, value in sanitized_data.items():
                    setattr(record, key, value)
                await session.flush()

            return record

    async def update_fields(
        self,
        *,
        file_id: str,
        data: dict[str, Any],
        kb_id: str | None = None,
    ) -> KnowledgeFile | None:
        sanitized_data = self._sanitize_data(data)
        if not sanitized_data:
            return await self.get_by_file_id(file_id)

        filters = [KnowledgeFile.file_id == file_id]
        if kb_id:
            filters.append(KnowledgeFile.kb_id == kb_id)

        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(KnowledgeFile).where(*filters))
            record = result.scalar_one_or_none()
            if record is None:
                return None
            for key, value in sanitized_data.items():
                setattr(record, key, value)
            return record

    async def begin_index_generation(
        self, *, kb_id: str, file_id: str, processing_job_id: str | None = None, processing_owner: str | None = None
    ) -> int:
        """每次尝试申请单调新代次，旧 owner 的晚写不能污染重试结果。"""
        async with pg_manager.get_async_session_context() as session:
            record = await self._lock_index_owner(
                session,
                kb_id=kb_id,
                file_id=file_id,
                processing_job_id=processing_job_id,
                processing_owner=processing_owner,
            )
            if record.building_generation is not None:
                self._enqueue_generation_cleanup(session, record, int(record.building_generation))
            generation = int(record.generation or 1) + 1
            record.generation = generation
            record.building_generation = generation
            record.projection_status = "building"
            return generation

    async def finish_index_generation(
        self,
        *,
        kb_id: str,
        file_id: str,
        generation: int,
        chunk_count: int,
        token_count: int,
        processing_job_id: str | None = None,
        processing_owner: str | None = None,
    ) -> KnowledgeFile:
        """当前 owner 在同一事务切换版本、终态和旧代次清理意图。"""
        async with pg_manager.get_async_session_context() as session:
            record = await self._lock_index_owner(
                session,
                kb_id=kb_id,
                file_id=file_id,
                processing_job_id=processing_job_id,
                processing_owner=processing_owner,
            )
            if record.building_generation != generation:
                raise ValueError(f"File {file_id} generation {generation} is not the current build")
            self._enqueue_generation_cleanup(session, record, int(record.active_generation))
            record.active_generation = generation
            record.building_generation = None
            record.status = "indexed"
            record.chunk_count = chunk_count
            record.token_count = token_count
            record.projection_status = "ready"
            record.projection_error = None
            record.error_message = None
            record.processing_job_id = None
            record.processing_owner = None
            return record

    @staticmethod
    async def _lock_index_owner(session, *, kb_id, file_id, processing_job_id, processing_owner):
        """在文件自身的锁与版本事实下拒绝删除和替换后的旧完成回调。"""
        record = await session.scalar(
            select(KnowledgeFile)
            .where(
                KnowledgeFile.kb_id == kb_id,
                KnowledgeFile.file_id == file_id,
            )
            .with_for_update()
        )
        if record is None or record.deleted_at is not None:
            raise ValueError(f"File {file_id} not found or deleted")
        if record.status != "indexing" or (record.processing_job_id, record.processing_owner) != (
            processing_job_id,
            processing_owner,
        ):
            raise ValueError("File indexing owner was lost")
        return record

    @staticmethod
    def _enqueue_generation_cleanup(session, record, generation):
        """切换事务持有 File 锁时保存唯一旧代次清理意图。"""
        session.add(
            KnowledgeProjectionOutbox(
                event_key=f"file:{record.file_id}:g{generation}:generation_cleanup",
                kb_id=record.kb_id,
                aggregate_id=record.file_id,
                generation=generation,
                operation="generation_cleanup",
            )
        )

    async def update_fields_if_status(
        self,
        *,
        kb_id: str,
        file_id: str,
        allowed_statuses: set[str],
        data: dict[str, Any],
        processing_job_id: str | None = None,
        processing_owner: str | None = None,
    ) -> KnowledgeFile | None:
        lease_job_id = processing_job_id or data.get("processing_job_id")
        lease_owner = processing_owner or data.get("processing_owner")
        sanitized_data = self._sanitize_data(data)
        if not sanitized_data:
            return await self.get_by_file_id(file_id)

        filters = [
            KnowledgeFile.kb_id == kb_id,
            KnowledgeFile.file_id == file_id,
            KnowledgeFile.status.in_(sorted(allowed_statuses)),
        ]
        if processing_job_id is not None:
            filters.append(KnowledgeFile.processing_job_id == processing_job_id)
        if processing_owner is not None:
            filters.append(KnowledgeFile.processing_owner == processing_owner)
        async with pg_manager.get_async_session_context() as session:
            if lease_job_id is not None and lease_owner is not None:
                job_record = await session.scalar(
                    select(BackgroundJobRecord)
                    .where(
                        BackgroundJobRecord.id == lease_job_id,
                        BackgroundJobRecord.status == "running",
                        BackgroundJobRecord.worker_id == lease_owner,
                    )
                    .with_for_update()
                )
                if job_record is None:
                    return None
                file_record = await session.scalar(select(KnowledgeFile).where(*filters).with_for_update())
                if file_record is None:
                    return None
                database_now = await session.scalar(select(func.clock_timestamp()))
                if job_record.lease_expires_at is None or job_record.lease_expires_at <= database_now:
                    return None
                for key, value in sanitized_data.items():
                    setattr(file_record, key, value)
                await session.flush()
                return file_record

            result = await session.execute(update(KnowledgeFile).where(*filters).values(**sanitized_data).returning(KnowledgeFile))
            return result.scalar_one_or_none()

    @staticmethod
    async def fail_job_processing_in_session(session, *, job_id: str, error: str) -> int:
        """同事务收敛指定作业拥有的文件中间态与知识库统计。"""
        owned_files = select(KnowledgeFile.kb_id).where(
            KnowledgeFile.processing_job_id == job_id,
            KnowledgeFile.status.in_(["parsing", "indexing"]),
        )
        # 与文件写入保持 KB → File 锁序，统计在持有 KB 行锁后重新聚合。
        kb_result = await session.scalars(
            select(KnowledgeBase)
            .where(KnowledgeBase.kb_id.in_(owned_files))
            .order_by(KnowledgeBase.kb_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        knowledge_bases = list(kb_result.all())
        result = await session.execute(
            update(KnowledgeFile)
            .where(
                KnowledgeFile.processing_job_id == job_id,
                KnowledgeFile.status.in_(["parsing", "indexing"]),
            )
            .values(
                status=case(
                    (KnowledgeFile.status == "parsing", "error_parsing"),
                    else_="error_indexing",
                ),
                error_message=error,
                processing_job_id=None,
                processing_owner=None,
                projection_status="failed",
                projection_error=error,
                updated_at=func.now(),
            )
            .returning(KnowledgeFile.kb_id)
        )
        affected = list(result.scalars().all())
        affected_kb_ids = set(affected)
        for kb in knowledge_bases:
            if kb.kb_id in affected_kb_ids:
                stats = await KnowledgeFileRepository().query_kb_file_stats(kb.kb_id, session=session)
                kb.additional_params = {**(kb.additional_params or {}), "stats": stats}
        await session.flush()
        return len(affected)

    async def mark_deleted(self, *, kb_id: str, file_id: str) -> str | None:
        """先提交 PostgreSQL 删除事实，再由投影任务清理外部索引。"""
        event_key: str | None = None
        async with pg_manager.get_async_session_context() as session:
            record = await session.scalar(
                select(KnowledgeFile).where(KnowledgeFile.kb_id == kb_id, KnowledgeFile.file_id == file_id).with_for_update()
            )
            if record is None:
                return None
            generation = int(record.generation or 1)
            event_key = f"file:{file_id}:g{generation}:deleted"
            record.deleted_at = utc_now()
            record.status = "deleted"
            record.projection_status = "pending"
            record.projection_error = None
            existing = await session.scalar(select(KnowledgeProjectionOutbox).where(KnowledgeProjectionOutbox.event_key == event_key))
            if existing is None:
                session.add(
                    KnowledgeProjectionOutbox(
                        event_key=event_key,
                        kb_id=kb_id,
                        aggregate_id=file_id,
                        generation=generation,
                        operation="file_deleted",
                    )
                )
        return event_key

    async def delete(self, file_id: str) -> None:
        """禁止绕过删除语义；调用方必须提供知识库并走 mark_deleted。"""
        record = await self.get_by_file_id(file_id, include_deleted=True)
        if record is not None:
            await self.mark_deleted(kb_id=record.kb_id, file_id=file_id)

    async def mark_deleted_by_kb_id(self, kb_id: str) -> list[str]:
        """在缓存锁内隐藏知识库及全部文件，并登记可重试清理意图。"""
        from yuxi.modules.knowledge.cache import delete_cached_kb_config, kb_config_cache_lock

        async with kb_config_cache_lock(kb_id):
            await delete_cached_kb_config(kb_id)
            return await self._mark_knowledge_base_deleted(kb_id)

    async def _mark_knowledge_base_deleted(self, kb_id: str) -> list[str]:
        """在同一事务提交 KB、File tombstone 和外部清理意图。"""
        event_keys: list[str] = []
        async with pg_manager.get_async_session_context() as session:
            kb = await session.scalar(select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id).with_for_update())
            if kb is None:
                return []
            kb.deleted_at = kb.deleted_at or utc_now()
            knowledge_base_key = f"knowledge_base:{kb_id}:deleted"
            existing = await session.scalar(
                select(KnowledgeProjectionOutbox).where(KnowledgeProjectionOutbox.event_key == knowledge_base_key)
            )
            if existing is None:
                session.add(
                    KnowledgeProjectionOutbox(
                        event_key=knowledge_base_key,
                        kb_id=kb_id,
                        aggregate_id=kb_id,
                        generation=1,
                        operation="knowledge_base_deleted",
                    )
                )
            event_keys.append(knowledge_base_key)
            result = await session.execute(select(KnowledgeFile).where(KnowledgeFile.kb_id == kb_id).with_for_update())
            for record in result.scalars().all():
                generation = int(record.generation or 1)
                event_key = f"file:{record.file_id}:g{generation}:deleted"
                record.deleted_at = utc_now()
                record.status = "deleted"
                record.projection_status = "pending"
                record.projection_error = None
                existing = await session.scalar(select(KnowledgeProjectionOutbox).where(KnowledgeProjectionOutbox.event_key == event_key))
                if existing is None:
                    session.add(
                        KnowledgeProjectionOutbox(
                            event_key=event_key,
                            kb_id=kb_id,
                            aggregate_id=record.file_id,
                            generation=generation,
                            operation="file_deleted",
                        )
                    )
                event_keys.append(event_key)
        return event_keys

    async def delete_by_kb_id(self, kb_id: str) -> None:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(KnowledgeFile).where(KnowledgeFile.kb_id == kb_id))
            for record in result.scalars().all():
                await session.delete(record)
