import asyncio
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from uuid import uuid4

from yuxi.infrastructure.filesystem import await_io
from yuxi.infrastructure.observability.logging import logger
from yuxi.modules.knowledge.chunking.presets import ensure_chunk_defaults_in_additional_params
from yuxi.modules.knowledge.file_status import FileStatus
from yuxi.modules.knowledge.read_models import KnowledgeBaseConfig
from yuxi.modules.knowledge.schemas import FindOutputSchema, FindWindowSchema, SearchOutputSchema, SearchResultSchema
from yuxi.modules.knowledge.utils import resolve_processing_params, sanitize_processing_params
from yuxi.shared.datetime import utc_isoformat
from yuxi.shared.files import detect_media_type


class KnowledgeBaseException(Exception):
    """知识库统一异常基类"""

    pass


class KBNotFoundError(KnowledgeBaseException):
    """知识库不存在错误"""

    pass


class KBNameConflictError(KnowledgeBaseException):
    """知识库名称冲突错误。"""

    pass


class KnowledgeExecutor(ABC):
    """知识库抽象基类，定义统一接口"""

    kb_type = ""
    name = ""
    description = ""
    requires_embedding_model = True
    supports_documents = True
    supports_document_read = True
    apply_chunk_defaults = True

    def __init__(self, work_dir: str):
        """
        初始化知识库

        Args:
            work_dir: 工作目录
        """
        self.work_dir = work_dir
        os.makedirs(work_dir, exist_ok=True)

    def _file_record_to_meta(self, record: Any) -> dict:
        return {
            "file_id": record.file_id,
            "kb_id": record.kb_id,
            "parent_id": record.parent_id,
            "filename": record.filename,
            "file_type": record.file_type,
            "path": record.path,
            "markdown_file": record.markdown_file,
            "status": record.status,
            "content_hash": record.content_hash,
            "size": record.file_size,
            "chunk_count": int(getattr(record, "chunk_count", 0) or 0),
            "token_count": int(getattr(record, "token_count", 0) or 0),
            "content_type": record.content_type,
            "processing_params": sanitize_processing_params(record.processing_params),
            "is_folder": record.is_folder,
            "error": record.error_message,
            "created_by": record.created_by,
            "updated_by": record.updated_by,
            "created_at": utc_isoformat(record.created_at) if record.created_at else None,
            "updated_at": utc_isoformat(record.updated_at) if record.updated_at else None,
            "original_filename": record.original_filename,
            "minio_url": record.minio_url,
            "generation": int(getattr(record, "generation", 1) or 1),
            "active_generation": int(getattr(record, "active_generation", 1) or 1),
            "building_generation": getattr(record, "building_generation", None),
        }

    @staticmethod
    def _file_meta_to_record_data(meta: dict) -> dict[str, Any]:
        return {
            "kb_id": meta.get("kb_id"),
            "parent_id": meta.get("parent_id"),
            "filename": meta.get("filename") or "",
            "original_filename": meta.get("original_filename"),
            "file_type": meta.get("file_type"),
            "path": meta.get("path"),
            "minio_url": meta.get("minio_url"),
            "markdown_file": meta.get("markdown_file"),
            "status": meta.get("status"),
            "content_hash": meta.get("content_hash"),
            "file_size": meta.get("size"),
            "chunk_count": int(meta.get("chunk_count") or 0),
            "token_count": int(meta.get("token_count") or 0),
            "content_type": meta.get("content_type"),
            "processing_params": sanitize_processing_params(meta.get("processing_params")),
            "is_folder": meta.get("is_folder", False),
            "error_message": meta.get("error"),
            "created_by": str(meta.get("created_by")) if meta.get("created_by") else None,
            "updated_by": str(meta.get("updated_by")) if meta.get("updated_by") else None,
        }

    async def _load_file_meta(self, kb_id: str, file_id: str) -> dict:
        from yuxi.modules.knowledge.repositories.files import KnowledgeFileRepository

        record = await KnowledgeFileRepository().get_by_file_id(file_id)
        if record is None or record.kb_id != kb_id:
            raise ValueError(f"File {file_id} not found")

        return self._file_record_to_meta(record)

    @classmethod
    def get_create_params_config(cls) -> dict[str, Any]:
        """获取创建知识库时的类型特定参数配置。"""
        return {"options": []}

    @classmethod
    def validate_additional_params(cls, additional_params: dict | None) -> dict:
        """校验并规范化类型特定配置。"""
        return dict(additional_params or {})

    @classmethod
    def normalize_additional_params(cls, additional_params: dict | None) -> dict:
        """规范化 additional_params，仅文档型知识库补充分块默认值。"""
        params = cls.validate_additional_params(additional_params)
        if cls.apply_chunk_defaults:
            return ensure_chunk_defaults_in_additional_params(params)
        return params

    async def add_file_record(
        self,
        kb_id: str,
        item: str,
        params: dict | None = None,
        operator_id: str | None = None,
        *,
        additional_params: dict[str, Any],
    ) -> dict:
        """
        Add a file record to metadata (Status: UPLOADED)

        Args:
            kb_id: Knowledge base ID
            item: File path or URL
            params: Parameters
            operator_id: Operator ID who created the file

        Returns:
            File metadata record
        """
        from yuxi.modules.knowledge.utils.kb_utils import prepare_item_metadata

        params = params or {}
        content_type = params.get("content_type", "file")

        # Prepare metadata
        metadata = await prepare_item_metadata(item, content_type, kb_id, params=params)
        file_id = metadata["file_id"]
        metadata["processing_params"] = resolve_processing_params(
            kb_additional_params=additional_params,
            file_processing_params=metadata.get("processing_params"),
        )

        # Fallback: fetch file size from MinIO if not provided
        if metadata.get("size") is None and content_type == "file":
            try:
                from yuxi.infrastructure.minio import get_minio_client
                from yuxi.infrastructure.minio.object_urls import is_minio_url, parse_minio_url

                file_path = metadata.get("path") or item
                if is_minio_url(file_path):
                    bucket_name, obj_name = parse_minio_url(file_path)
                    minio_client = get_minio_client()
                    file_size = await minio_client.astat_file(bucket_name, obj_name)
                    if file_size is not None:
                        metadata["size"] = file_size
            except Exception as exc:
                logger.warning(f"Failed to stat file size from MinIO for {item}: {exc}")

        # Initial status
        metadata["status"] = FileStatus.UPLOADED
        metadata["created_at"] = utc_isoformat()
        if operator_id:
            metadata["created_by"] = operator_id

        await self._persist_file_meta(file_id, metadata)

        return metadata

    async def parse_file(
        self,
        kb_id: str,
        file_id: str,
        operator_id: str | None = None,
        *,
        additional_params: dict[str, Any],
        processing_job_id: str | None = None,
        processing_owner: str | None = None,
    ) -> dict:
        """
        Parse file to Markdown and save to MinIO (Status: PARSING -> PARSED/ERROR_PARSING)

        Args:
            kb_id: Knowledge base ID
            file_id: File ID
            operator_id: ID of the user performing the operation

        Returns:
            Updated file metadata
        """
        # Validate current status - only allow parsing from these states
        allowed_statuses = {
            FileStatus.UPLOADED,
            FileStatus.ERROR_PARSING,
        }

        from yuxi.modules.knowledge.repositories.files import KnowledgeFileRepository

        file_repo = KnowledgeFileRepository()
        owner_filter = (
            {"processing_job_id": processing_job_id, "processing_owner": processing_owner}
            if processing_job_id is not None and processing_owner is not None
            else {}
        )
        claim_data = {
            "status": FileStatus.PARSING,
            "error_message": None,
            "processing_job_id": processing_job_id,
            "processing_owner": processing_owner,
        }
        if operator_id:
            claim_data["updated_by"] = operator_id
        claimed_record = await file_repo.update_fields_if_status(
            kb_id=kb_id,
            file_id=file_id,
            allowed_statuses=allowed_statuses,
            data=claim_data,
        )
        if claimed_record is None:
            current_meta = await self._load_file_meta(kb_id, file_id)
            current_status = current_meta.get("status")
            raise ValueError(
                f"Cannot parse file with status '{current_status}'. File must be in one of these states: {', '.join(allowed_statuses)}"
            )

        file_meta = self._file_record_to_meta(claimed_record)
        file_path = file_meta.get("path")
        if not file_path:
            message = f"File {file_id} has no valid path in metadata"
            update_data = {"status": FileStatus.ERROR_PARSING, "error_message": message}
            if operator_id:
                update_data["updated_by"] = operator_id
            update_data.update({"processing_job_id": None, "processing_owner": None})
            updated_record = await file_repo.update_fields_if_status(
                file_id=file_id,
                kb_id=kb_id,
                allowed_statuses={FileStatus.PARSING},
                data=update_data,
                **owner_filter,
            )
            if updated_record is None and processing_owner is not None:
                raise asyncio.CancelledError("File processing owner was lost")
            raise ValueError(message)

        attempt_id = uuid4().hex
        previous_markdown = file_meta.get("markdown_file")
        try:
            from yuxi.modules.documents.service import parse_to_hosted_markdown
            from yuxi.modules.knowledge.utils.kb_utils import build_kb_image_proxy_url

            # Prepare params
            params = resolve_processing_params(
                kb_additional_params=additional_params,
                file_processing_params=file_meta.get("processing_params"),
            )
            from yuxi.infrastructure.minio import get_minio_client

            markdown_content = await parse_to_hosted_markdown(
                source=file_path,
                params=params,
                image_bucket=get_minio_client().KB_BUCKETS["images"],
                image_prefix=f"{kb_id}/kb-images/{file_id}/{attempt_id}/",
                url_builder=build_kb_image_proxy_url,
            )

            # Save Markdown to MinIO
            markdown_file_path = await self._save_markdown_to_minio(kb_id, file_id, attempt_id, markdown_content)

            # Update metadata
            file_meta["status"] = FileStatus.PARSED
            file_meta["markdown_file"] = markdown_file_path
            file_meta["error"] = None
            file_meta["updated_at"] = utc_isoformat()
            if operator_id:
                file_meta["updated_by"] = operator_id
            update_data = {
                "status": FileStatus.PARSED,
                "markdown_file": markdown_file_path,
                "error_message": None,
                "processing_job_id": None,
                "processing_owner": None,
            }
            if operator_id:
                update_data["updated_by"] = operator_id
            updated_record = await file_repo.update_fields_if_status(
                file_id=file_id,
                kb_id=kb_id,
                allowed_statuses={FileStatus.PARSING},
                data=update_data,
                **owner_filter,
            )
            if updated_record is None:
                raise asyncio.CancelledError("File processing owner was lost")

        except (Exception, asyncio.CancelledError) as e:
            if isinstance(e, asyncio.CancelledError):
                current_task = asyncio.current_task()
                if current_task is not None and current_task.cancelling():
                    current_task.uncancel()
            await self._cleanup_parse_attempt(kb_id, file_id, attempt_id)
            error_msg = "File parsing was cancelled" if isinstance(e, asyncio.CancelledError) else str(e)
            logger.error(f"Failed to parse file {file_id}: {error_msg}")

            file_meta["status"] = FileStatus.ERROR_PARSING
            file_meta["error"] = error_msg
            file_meta["updated_at"] = utc_isoformat()
            if operator_id:
                file_meta["updated_by"] = operator_id
            update_data = {
                "status": FileStatus.ERROR_PARSING,
                "error_message": error_msg,
                "processing_job_id": None,
                "processing_owner": None,
            }
            if operator_id:
                update_data["updated_by"] = operator_id
            updated_record = await file_repo.update_fields_if_status(
                file_id=file_id,
                kb_id=kb_id,
                allowed_statuses={FileStatus.PARSING},
                data=update_data,
                **owner_filter,
            )
            if updated_record is None and processing_owner is not None:
                raise asyncio.CancelledError("File processing owner was lost")

            raise

        if previous_markdown:
            from yuxi.infrastructure.minio.object_urls import parse_minio_url

            _, previous_object = parse_minio_url(previous_markdown)
            previous_attempt = Path(previous_object).parent.name
            await self._cleanup_parse_attempt(kb_id, file_id, previous_attempt)
        return file_meta

    async def update_file_params(
        self,
        kb_id: str,
        file_id: str,
        params: dict,
        operator_id: str | None = None,
        *,
        additional_params: dict[str, Any],
    ) -> None:
        """Update file processing params"""
        # Skip if no params to update
        if not params:
            return

        file_meta = await self._load_file_meta(kb_id, file_id)
        current_params = file_meta.get("processing_params", {}) or {}
        logger.debug(f"[update_file_params] file_id={file_id}, current_params={current_params}, new_params={params}")

        current_params = resolve_processing_params(
            kb_additional_params=additional_params,
            file_processing_params=current_params,
            request_params=params,
        )

        file_meta["processing_params"] = current_params
        file_meta["updated_at"] = utc_isoformat()
        if operator_id:
            file_meta["updated_by"] = operator_id

        logger.debug(f"[update_file_params] file_id={file_id}, updated_params={current_params}")

        from yuxi.modules.knowledge.repositories.files import KnowledgeFileRepository

        update_data = {"processing_params": sanitize_processing_params(current_params)}
        if operator_id:
            update_data["updated_by"] = operator_id
        record = await KnowledgeFileRepository().update_fields(file_id=file_id, kb_id=kb_id, data=update_data)
        if record is None:
            raise ValueError(f"File {file_id} not found")

    async def cleanup_file_resources(self, kb_id: str, file_id: str) -> None:
        """删除单个文档拥有的全部解析产物。"""
        from yuxi.infrastructure.minio import get_minio_client
        from yuxi.infrastructure.minio.object_urls import is_minio_url, parse_minio_url
        from yuxi.modules.knowledge.repositories.files import KnowledgeFileRepository

        client = get_minio_client()
        record = await KnowledgeFileRepository().get_by_file_id(file_id, include_deleted=True)
        if record is not None and record.kb_id != kb_id:
            raise ValueError("File cleanup cannot cross knowledge bases")
        if record is not None:
            source = record.minio_url or record.path
            if source and is_minio_url(source):
                bucket, key = parse_minio_url(source)
                if bucket != client.KB_BUCKETS["documents"] or not key.startswith(f"{kb_id}/"):
                    raise ValueError("File source is outside the owning knowledge base")
                await client.adelete_file(bucket, key)
        await asyncio.gather(
            client.adelete_objects_by_prefix(client.KB_BUCKETS["images"], f"{kb_id}/kb-images/{file_id}/"),
            client.adelete_objects_by_prefix(client.KB_BUCKETS["parsed"], f"{kb_id}/parsed/{file_id}/"),
        )

    async def _save_markdown_to_minio(self, kb_id: str, file_id: str, attempt_id: str, content: str) -> str:
        """Save markdown content to MinIO and return HTTP URL"""
        from yuxi.infrastructure.minio import get_minio_client

        minio_client = get_minio_client()
        bucket_name = minio_client.KB_BUCKETS["parsed"]
        await asyncio.to_thread(minio_client.ensure_bucket_exists, bucket_name)

        object_name = f"{kb_id}/parsed/{file_id}/{attempt_id}/document.md"
        data = content.encode("utf-8")

        # Return standard HTTP URL from UploadResult
        upload_result = await await_io(
            minio_client.aupload_file(
                bucket_name=bucket_name,
                object_name=object_name,
                data=data,
            )
        )

        return upload_result.url

    async def _cleanup_parse_attempt(self, kb_id: str, file_id: str, attempt_id: str) -> None:
        """尽力回收指定解析尝试，清理失败形成可观察日志。"""
        from yuxi.infrastructure.minio import get_minio_client

        client = get_minio_client()
        results = await asyncio.gather(
            client.adelete_objects_by_prefix(client.KB_BUCKETS["images"], f"{kb_id}/kb-images/{file_id}/{attempt_id}/"),
            client.adelete_objects_by_prefix(client.KB_BUCKETS["parsed"], f"{kb_id}/parsed/{file_id}/{attempt_id}/"),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.warning("解析产物清理失败: kb=%s file=%s attempt=%s error=%s", kb_id, file_id, attempt_id, result)

    async def _read_minio_bytes(self, file_path: str) -> bytes:
        from yuxi.infrastructure.minio import get_minio_client
        from yuxi.infrastructure.minio.object_urls import is_minio_url, parse_minio_url

        if not file_path or not is_minio_url(file_path):
            raise ValueError(f"Invalid MinIO path format: {file_path}")

        bucket_name, object_name = parse_minio_url(file_path)
        minio_client = get_minio_client()
        return await minio_client.adownload_file(bucket_name, object_name)

    async def _read_markdown_from_minio(self, file_path: str) -> str:
        """Read markdown content from MinIO"""
        content_bytes = await self._read_minio_bytes(file_path)
        return content_bytes.decode("utf-8")

    @staticmethod
    def _original_file_path(file_meta: dict) -> str | None:
        return file_meta.get("minio_url") or file_meta.get("path")

    async def get_file_download(self, kb_id: str, file_id: str, variant: str = "original") -> dict:
        file_meta = await self._load_file_meta(kb_id, file_id)
        if file_meta.get("is_folder"):
            raise ValueError("Cannot download a folder")
        if variant not in {"original", "parsed"}:
            raise ValueError("Unsupported download variant")

        filename = file_meta.get("filename") or file_meta.get("original_filename") or file_id
        if variant == "parsed":
            markdown_file = file_meta.get("markdown_file")
            if not markdown_file:
                raise ValueError("文件尚未生成解析结果")
            return {
                "filename": f"{filename}.parsed.md",
                "content": await self._read_minio_bytes(markdown_file),
                "media_type": "text/markdown; charset=utf-8",
            }

        original_path = self._original_file_path(file_meta)
        if not original_path:
            raise ValueError("文件没有可下载的原始内容")
        media_type = file_meta.get("content_type") or detect_media_type(filename)
        return {
            "filename": filename,
            "content": await self._read_minio_bytes(original_path),
            "media_type": media_type,
        }

    def _build_open_file_window(self, content: str, *, offset: int = 0, limit: int = 800) -> dict[str, Any]:
        lines = content.splitlines()
        total_lines = len(lines)
        start = min(max(int(offset), 0), total_lines)
        window_size = min(max(int(limit), 1), 2000)
        selected = lines[start : start + window_size]
        end = start + len(selected)

        return {
            "start_line": start + 1 if selected else 0,
            "end_line": end,
            "total_lines": total_lines,
            "offset": start,
            "window_size": window_size,
            "has_more_before": start > 0,
            "has_more_after": end < total_lines,
            "next_offset": end if end < total_lines else None,
            "content": "\n".join(f"{start + idx + 1:6d}\t{line}" for idx, line in enumerate(selected)),
        }

    @staticmethod
    def build_search_output(kb_id: str, retrieval_results: Any) -> dict[str, Any] | Any:
        if not isinstance(retrieval_results, list):
            return retrieval_results

        results = []
        for index, chunk in enumerate(retrieval_results):
            if not isinstance(chunk, dict):
                continue

            metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
            metadata = {key: value for key, value in metadata.items() if key not in {"filepath", "parsed_path", "path", "markdown_file"}}
            file_id = metadata.get("file_id") or chunk.get("file_id") or chunk.get("full_doc_id") or ""
            chunk_id = metadata.get("chunk_id") or chunk.get("chunk_id") or chunk.get("id")
            chunk_index = metadata.get("chunk_index")
            if chunk_index is None:
                chunk_index = chunk.get("chunk_index")
            if chunk_index is not None:
                metadata.setdefault("chunk_index", chunk_index)
            for field in ("score", "score_type", "distance", "rerank_score", "highlights"):
                if chunk.get(field) is not None:
                    metadata.setdefault(field, chunk[field])

            results.append(
                SearchResultSchema(
                    id=str(chunk_id or f"{file_id}:{index + 1}"),
                    kb_id=str(kb_id),
                    file_id=str(file_id or ""),
                    content=str(chunk.get("content") or ""),
                    metadata=metadata,
                )
            )

        return SearchOutputSchema(kb_id=str(kb_id), results=results).model_dump()

    @staticmethod
    def _build_find_file_windows(
        content: str,
        *,
        patterns: list[str],
        use_regex: bool = False,
        case_sensitive: bool = False,
        max_windows: int = 5,
        window_size: int = 80,
    ) -> dict[str, Any]:
        patterns = [pattern for pattern in patterns if pattern]
        if not patterns:
            raise ValueError("请提供至少一个 pattern")

        lines = content.splitlines()
        flags = 0 if case_sensitive else re.IGNORECASE
        if use_regex:
            try:
                matchers = [re.compile(pattern, flags) for pattern in patterns]
            except re.error as exc:
                raise ValueError(f"无效正则表达式: {exc}") from exc

            def line_matches(line: str) -> bool:
                return any(matcher.search(line) for matcher in matchers)

        else:
            normalized_patterns = patterns if case_sensitive else [pattern.lower() for pattern in patterns]

            def line_matches(line: str) -> bool:
                haystack = line if case_sensitive else line.lower()
                return any(pattern in haystack for pattern in normalized_patterns)

        matched_indexes = [index for index, line in enumerate(lines) if line_matches(line)]
        windows: list[FindWindowSchema] = []
        covered_until = -1
        normalized_window_size = min(max(int(window_size), 1), 200)
        half_window = normalized_window_size // 2

        for matched_index in matched_indexes:
            if matched_index < covered_until:
                continue
            start = max(matched_index - half_window, 0)
            end = min(start + normalized_window_size, len(lines))
            start = max(end - normalized_window_size, 0)
            matched_lines = [index + 1 for index in matched_indexes if start <= index < end]
            selected = lines[start:end]
            windows.append(
                FindWindowSchema(
                    start_line=start + 1 if selected else 0,
                    end_line=end,
                    matched_lines=matched_lines,
                    content="\n".join(f"{start + idx + 1:6d}\t{line}" for idx, line in enumerate(selected)),
                )
            )
            covered_until = end
            if len(windows) >= max_windows:
                break

        return FindOutputSchema(
            kb_id="",
            file_id="",
            semantic=False,
            match_mode="regex" if use_regex else "keyword",
            total_matches=len(matched_indexes),
            windows=windows,
        ).model_dump(exclude={"kb_id", "file_id"})

    async def open_document(
        self,
        kb_id: str,
        file_id: str,
        *,
        config: KnowledgeBaseConfig,
        offset: int = 0,
        limit: int = 800,
    ) -> dict:
        """按本次连接配置打开正文；本地文档复用既有窗口读取。"""
        del config
        return await self.open_file_content(kb_id, file_id, offset=offset, limit=limit)

    async def open_file_content(self, kb_id: str, file_id: str, offset: int = 0, limit: int = 800) -> dict:
        """按行窗口打开文件解析后的 Markdown 内容"""
        try:
            file_meta = await self._load_file_meta(kb_id, file_id)
        except ValueError as exc:
            raise ValueError(f"文件不存在: {file_id}") from exc
        if file_meta.get("is_folder"):
            raise ValueError(f"文件 {file_id} 是文件夹")

        markdown_file = file_meta.get("markdown_file")
        if not markdown_file:
            raise ValueError(f"文件 {file_id} 没有解析后的 Markdown 内容")

        content = await self._read_markdown_from_minio(markdown_file)
        return self._build_open_file_window(content, offset=offset, limit=limit)

    async def find_file_content(
        self,
        kb_id: str,
        file_id: str,
        patterns: list[str],
        *,
        use_regex: bool = False,
        case_sensitive: bool = False,
        max_windows: int = 5,
        window_size: int = 80,
    ) -> dict:
        try:
            file_meta = await self._load_file_meta(kb_id, file_id)
        except ValueError as exc:
            raise ValueError(f"文件不存在: {file_id}") from exc
        if file_meta.get("is_folder"):
            raise ValueError(f"文件 {file_id} 是文件夹")

        markdown_file = file_meta.get("markdown_file")
        if not markdown_file:
            raise ValueError(f"文件 {file_id} 没有解析后的 Markdown 内容")

        content = await self._read_markdown_from_minio(markdown_file)
        return self._build_find_file_windows(
            content,
            patterns=patterns,
            use_regex=use_regex,
            case_sensitive=case_sensitive,
            max_windows=max_windows,
            window_size=window_size,
        )

    @abstractmethod
    async def index_file(
        self,
        kb_id: str,
        file_id: str,
        operator_id: str | None = None,
        *,
        embedding_model_spec: str | None,
        additional_params: dict[str, Any],
        processing_job_id: str | None = None,
        processing_owner: str | None = None,
    ) -> dict:
        """
        Index parsed file (Status: INDEXING -> INDEXED/ERROR_INDEXING)

        Args:
            kb_id: Knowledge base ID
            file_id: File ID
            operator_id: ID of the user performing the operation

        Returns:
            Updated file metadata
        """
        pass

    async def cleanup_knowledge_base_resources(self, kb_id: str) -> dict:
        """
        清理知识库关联的文件与存储资源。

        Args:
            kb_id: 知识库ID

        Returns:
            操作结果
        """
        from yuxi.infrastructure.minio import get_minio_client
        from yuxi.modules.knowledge.repositories.files import KnowledgeFileRepository

        minio_client = get_minio_client()
        file_repo = KnowledgeFileRepository()

        # 调用方已经提交 KB/File tombstone；失败必须阻止 PG 硬删除。
        prefix = f"{kb_id}/"
        cleanup_buckets = {
            minio_client.KB_BUCKETS["parsed"],
            minio_client.KB_BUCKETS["documents"],
            minio_client.KB_BUCKETS["images"],
        }
        cleanup_tasks = [minio_client.adelete_objects_by_prefix(bucket_name, prefix) for bucket_name in cleanup_buckets]
        await asyncio.gather(*cleanup_tasks)

        # 删除知识库的文件记录；知识库主记录由 Manager 统一删除。
        await file_repo.delete_by_kb_id(kb_id)

        # 删除工作目录
        working_dir = os.path.join(self.work_dir, kb_id)
        if os.path.exists(working_dir):
            import shutil

            try:
                shutil.rmtree(working_dir)
            except Exception as e:
                logger.error(f"Error deleting working directory {working_dir}: {e}")

        return {"message": "删除成功"}

    async def detect_data_inconsistencies(
        self,
        known_kb_ids: set[str],
        managed_kb_ids: set[str],
    ) -> dict[str, list[dict]]:
        """检测当前知识库类型管理的外部资源不一致。"""
        return {"missing_collections": [], "missing_files": []}

    async def create_folder(
        self,
        kb_id: str,
        folder_name: str,
        parent_id: str | None = None,
        operator_id: str | None = None,
    ) -> dict:
        """创建文件夹并记录操作者。"""
        import uuid

        if parent_id:
            parent_meta = await self._load_file_meta(kb_id, parent_id)
            if not parent_meta.get("is_folder"):
                raise ValueError("Parent is not a folder")

        folder_id = f"folder-{uuid.uuid4()}"

        folder_meta = {
            "file_id": folder_id,
            "filename": folder_name,
            "is_folder": True,
            "parent_id": parent_id,
            "kb_id": kb_id,
            "created_at": utc_isoformat(),
            "status": FileStatus.FOLDER_READY,
            "path": folder_name,
            "file_type": "folder",
            "created_by": operator_id,
        }
        await self._persist_file_meta(folder_id, folder_meta)
        return folder_meta

    async def rename_folder(self, kb_id: str, folder_id: str, folder_name: str) -> dict:
        """重命名真实文件夹，不改写其子记录。"""
        normalized_name = folder_name.strip()
        if not normalized_name:
            raise ValueError("Folder name cannot be empty")
        if "/" in normalized_name or "\\" in normalized_name:
            raise ValueError("Folder name cannot contain path separators")

        meta = await self._load_file_meta(kb_id, folder_id)
        if not meta.get("is_folder"):
            raise ValueError("Document is not a folder")

        from yuxi.modules.knowledge.repositories.files import KnowledgeFileRepository

        record = await KnowledgeFileRepository().update_fields(
            file_id=folder_id,
            kb_id=kb_id,
            data={"filename": normalized_name, "path": normalized_name},
        )
        if record is None:
            raise ValueError(f"File {folder_id} not found")
        return self._file_record_to_meta(record)

    @abstractmethod
    async def aquery(
        self,
        query_text: str,
        kb_id: str,
        *,
        config: KnowledgeBaseConfig,
        **kwargs,
    ) -> list[dict]:
        """
        异步查询知识库

        Args:
            query_text: 查询文本
            kb_id: 知识库ID
            **kwargs: 查询参数

        Returns:
            一个包含字典的列表，每个字典代表一个检索到的文档块。
        """
        pass

    @abstractmethod
    def get_query_params_config(self, kb_id: str, **kwargs) -> dict:
        """
        获取知识库类型的查询参数配置

        Args:
            kb_id: 知识库ID
            **kwargs: 额外参数

        Returns:
            dict: {
                "type": "kb_type",
                "options": [
                    {
                        "key": "param_name",
                        "label": "参数名称",
                        "type": "select|number|boolean",
                        "default": default_value,
                        "options": [...],  # 对于 select 类型
                        "description": "参数描述",
                        "min": 1,  # 对于 number 类型
                        "max": 100,
                        "step": 0.1
                    },
                    ...
                ]
            }
        """
        pass

    async def export_data(self, kb_id: str, format: str = "zip", **kwargs) -> str:
        """导出知识库数据；具体 backend 未实现时显式拒绝。"""
        del kb_id, format, kwargs
        raise NotImplementedError("当前知识库类型不支持数据导出")

    def get_default_query_params(self, kb_id: str) -> dict[str, Any]:
        """从 get_query_params_config 中提取所有参数的默认值，返回 {"options": {...}}"""
        config = self.get_query_params_config(kb_id)
        defaults = {}
        for opt in config.get("options", []):
            if "default" in opt:
                defaults[opt["key"]] = opt["default"]
        return {"options": defaults}

    async def delete_folder(self, kb_id: str, folder_id: str) -> None:
        """
        Recursively delete a folder and its content.

        Args:
            kb_id: Knowledge base ID
            folder_id: Folder ID to delete
        """
        from yuxi.modules.knowledge.repositories.files import KnowledgeFileRepository

        children = await KnowledgeFileRepository().list_children(kb_id=kb_id, parent_id=folder_id)
        for child in children:
            child_id = child.file_id
            if child.is_folder:
                await self.delete_folder(kb_id, child_id)
            else:
                await self.delete_file(kb_id, child_id)

        # Delete the folder itself
        # We call delete_file which should handle the actual removal.
        # Implementations should ensure they handle folder deletion gracefully (e.g. skip vector deletion)
        await self.delete_file(kb_id, folder_id)

    async def move_file(self, kb_id: str, file_id: str, new_parent_id: str | None) -> dict:
        """
        Move a file or folder to a new parent folder.

        Args:
            kb_id: Knowledge base ID
            file_id: File/Folder ID to move
            new_parent_id: New parent folder ID (None for root)

        Returns:
            dict: Updated metadata
        """
        from yuxi.modules.knowledge.repositories.files import KnowledgeFileRepository

        async with KnowledgeFileRepository().lock_file_tree(kb_id):
            meta = await self._load_file_meta(kb_id, file_id)

            if meta.get("is_folder") and new_parent_id:
                if new_parent_id == file_id:
                    raise ValueError("Cannot move a folder into itself")

                current = new_parent_id
                while current:
                    parent_meta = await self._load_file_meta(kb_id, current)
                    if current == new_parent_id and not parent_meta.get("is_folder"):
                        raise ValueError("Parent is not a folder")
                    if current == file_id:
                        raise ValueError("Cannot move a folder into its own subfolder")
                    current = parent_meta.get("parent_id")
            elif new_parent_id:
                parent_meta = await self._load_file_meta(kb_id, new_parent_id)
                if not parent_meta.get("is_folder"):
                    raise ValueError("Parent is not a folder")

            record = await KnowledgeFileRepository().update_fields(
                file_id=file_id,
                kb_id=kb_id,
                data={"parent_id": new_parent_id},
            )
            if record is None:
                raise ValueError(f"File {file_id} not found")
            return self._file_record_to_meta(record)

    async def delete_file(self, kb_id: str, file_id: str) -> None:
        """先提交删除事实，再清理派生存储；失败时保留可重试 outbox。"""
        from yuxi.modules.knowledge.repositories.files import KnowledgeFileRepository

        await KnowledgeFileRepository().mark_deleted(kb_id=kb_id, file_id=file_id)

    async def get_file_basic_info(self, kb_id: str, file_id: str) -> dict:
        """获取文件基本信息（仅元数据）"""
        return {"meta": await self._load_file_meta(kb_id, file_id)}

    async def get_file_content(self, kb_id: str, file_id: str) -> dict:
        """获取文件内容信息（chunks和lines）"""
        file_meta = await self._load_file_meta(kb_id, file_id)
        return await self._get_file_content_from_meta(file_id, file_meta)

    async def get_file_info(self, kb_id: str, file_id: str) -> dict:
        """获取文件完整信息（基本信息+内容信息）"""
        file_meta = await self._load_file_meta(kb_id, file_id)
        content_info = await self._get_file_content_from_meta(file_id, file_meta)
        return {"meta": file_meta, **content_info}

    async def _get_file_content_from_meta(self, file_id: str, file_meta: dict) -> dict:
        """读取完整解析文本，并校验片段行号与文件快照属于同一入库代次。"""
        from yuxi.modules.knowledge.repositories.chunks import KnowledgeChunkRepository

        content_info = {"lines": [], "line_location": {"available": False, "reason": "content_unavailable"}}
        location_reason = "document_not_indexed" if file_meta.get("status") not in {"indexed", "done"} else ""
        try:
            chunks = await KnowledgeChunkRepository().list_by_file_id(file_id)
            if not location_reason and any(chunk.generation != file_meta.get("active_generation") for chunk in chunks):
                location_reason = "index_changed"
            content_info["lines"] = [
                {
                    "id": chunk.chunk_id,
                    "content": chunk.content,
                    "chunk_order_index": chunk.chunk_index,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "start_char_pos": chunk.start_char_pos,
                    "end_char_pos": chunk.end_char_pos,
                    "start_token_pos": chunk.start_token_pos,
                    "end_token_pos": chunk.end_token_pos,
                    "graph_indexed": chunk.graph_indexed,
                    "ent_ids": chunk.ent_ids,
                    "tags": chunk.tags,
                    "extraction_result": chunk.extraction_result,
                }
                for chunk in chunks
            ]
        except Exception as e:
            location_reason = "chunks_unavailable"
            logger.error(f"Failed to get file content from PostgreSQL: {e}")

        if not content_info["lines"]:
            logger.warning(f"No chunks found in PostgreSQL for file {file_id}, file may not have been indexed")

        # Try to read markdown content if available
        if file_meta.get("markdown_file"):
            try:
                content = await self._read_markdown_from_minio(file_meta["markdown_file"])
                content_info["content"] = content
            except Exception as e:
                logger.error(f"Failed to read markdown file for {file_id}: {e}")

        if content_info.get("content"):
            content_info["line_location"] = {"available": not location_reason, "reason": location_reason or None}
        return content_info

    async def _persist_file_meta(self, file_id: str, meta: dict) -> None:
        """Persist one file metadata record without storing it on the KB instance."""
        from yuxi.modules.knowledge.repositories.files import KnowledgeFileRepository

        data = self._file_meta_to_record_data(meta)
        if not data.get("kb_id"):
            return
        await KnowledgeFileRepository().upsert(file_id=file_id, data=data)
