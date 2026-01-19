import asyncio
import json
import os
import shutil
import tempfile
from abc import ABC, abstractmethod
from typing import Any

from src.utils import logger
from src.utils.datetime_utils import coerce_any_to_utc_datetime, utc_isoformat


class FileStatus:
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    ERROR_PARSING = "error_parsing"
    INDEXING = "indexing"
    INDEXED = "indexed"
    ERROR_INDEXING = "error_indexing"
    # Legacy status mapping
    DONE = "done"  # Map to INDEXED
    FAILED = "failed"  # Generic failure


class KnowledgeBaseException(Exception):
    """知识库统一异常基类"""

    pass


class KBNotFoundError(KnowledgeBaseException):
    """知识库不存在错误"""

    pass


class KBOperationError(KnowledgeBaseException):
    """知识库操作错误"""

    pass


class KnowledgeBase(ABC):
    """知识库抽象基类，定义统一接口"""

    # 类级别的处理队列，跟踪所有正在处理的文件
    _processing_files = set()
    _processing_lock = None

    def __init__(self, work_dir: str):
        """
        初始化知识库

        Args:
            work_dir: 工作目录
        """
        import threading

        self.work_dir = work_dir
        self.databases_meta: dict[str, dict] = {}
        self.files_meta: dict[str, dict] = {}
        self.benchmarks_meta: dict[str, dict] = {}

        # 初始化类级别的锁
        if KnowledgeBase._processing_lock is None:
            KnowledgeBase._processing_lock = threading.Lock()

        os.makedirs(work_dir, exist_ok=True)

        # 自动加载元数据
        self._load_metadata()
        self._normalize_metadata_state()

    @staticmethod
    def _normalize_timestamp(value: Any) -> str | None:
        """Convert persisted timestamps to a normalized UTC ISO string."""
        try:
            dt_value = coerce_any_to_utc_datetime(value)
        except (TypeError, ValueError) as exc:  # noqa: BLE001
            logger.warning(f"Invalid timestamp encountered: {value!r} ({exc})")
            return None

        if not dt_value:
            return None
        return utc_isoformat(dt_value)

    def _normalize_metadata_state(self) -> None:
        """Ensure in-memory metadata uses normalized timestamp formats."""
        for meta in self.databases_meta.values():
            if "created_at" in meta:
                normalized = self._normalize_timestamp(meta.get("created_at"))
                if normalized:
                    meta["created_at"] = normalized

        for file_info in self.files_meta.values():
            if "created_at" in file_info:
                normalized = self._normalize_timestamp(file_info.get("created_at"))
                if normalized:
                    file_info["created_at"] = normalized

        for db_benchmarks in self.benchmarks_meta.values():
            for b in db_benchmarks.values():
                if "created_at" in b:
                    normalized = self._normalize_timestamp(b.get("created_at"))
                    if normalized:
                        b["created_at"] = normalized
                if "updated_at" in b:
                    normalized = self._normalize_timestamp(b.get("updated_at"))
                    if normalized:
                        b["updated_at"] = normalized

    @property
    @abstractmethod
    def kb_type(self) -> str:
        """知识库类型标识"""
        pass

    @abstractmethod
    async def _create_kb_instance(self, db_id: str, config: dict) -> Any:
        """
        创建底层知识库实例

        Args:
            db_id: 数据库ID
            config: 配置信息

        Returns:
            底层知识库实例
        """
        pass

    @abstractmethod
    async def _initialize_kb_instance(self, instance: Any) -> None:
        """
        初始化底层知识库实例

        Args:
            instance: 底层知识库实例
        """
        pass

    async def add_file_record(
        self, db_id: str, item: str, params: dict | None = None, operator_id: str | None = None
    ) -> dict:
        """
        Add a file record to metadata (Status: UPLOADED)

        Args:
            db_id: Database ID
            item: File path or URL
            params: Parameters
            operator_id: Operator ID who created the file

        Returns:
            File metadata record
        """
        from src.knowledge.utils.kb_utils import prepare_item_metadata

        params = params or {}
        content_type = params.get("content_type", "file")

        # Prepare metadata
        metadata = await prepare_item_metadata(item, content_type, db_id, params=params)
        file_id = metadata["file_id"]

        # Initial status
        metadata["status"] = FileStatus.UPLOADED
        metadata["created_at"] = utc_isoformat()
        if operator_id:
            metadata["created_by"] = operator_id

        # Save to metadata
        self.files_meta[file_id] = metadata
        self._save_metadata()

        return metadata

    async def parse_file(self, db_id: str, file_id: str, operator_id: str | None = None) -> dict:
        """
        Parse file to Markdown and save to MinIO (Status: PARSING -> PARSED/ERROR_PARSING)

        Args:
            db_id: Database ID
            file_id: File ID
            operator_id: ID of the user performing the operation

        Returns:
            Updated file metadata
        """
        if file_id not in self.files_meta:
            raise ValueError(f"File {file_id} not found")

        file_meta = self.files_meta[file_id]
        current_status = file_meta.get("status")

        # Validate current status - only allow parsing from these states
        allowed_statuses = {
            FileStatus.UPLOADED,
            FileStatus.ERROR_PARSING,
            "failed",  # Legacy status
        }

        if current_status not in allowed_statuses:
            raise ValueError(
                f"Cannot parse file with status '{current_status}'. "
                f"File must be in one of these states: {', '.join(allowed_statuses)}"
            )

        file_path = file_meta.get("path")
        if not file_path:
            raise ValueError(f"File {file_id} has no valid path in metadata")

        # Clear previous error if any
        if "error" in file_meta:
            self.files_meta[file_id].pop("error", None)

        # Update status to PARSING and add to processing queue
        self.files_meta[file_id]["status"] = FileStatus.PARSING
        self.files_meta[file_id]["updated_at"] = utc_isoformat()
        if operator_id:
            self.files_meta[file_id]["updated_by"] = operator_id
        self._save_metadata()

        # Add to processing queue
        self._add_to_processing_queue(file_id)

        try:
            from src.knowledge.indexing import process_file_to_markdown

            # Prepare params
            params = file_meta.get("processing_params", {}) or {}
            params["db_id"] = db_id

            # Process to Markdown
            markdown_content = await process_file_to_markdown(file_path, params=params)

            # Save Markdown to MinIO
            markdown_file_path = await self._save_markdown_to_minio(db_id, file_id, markdown_content)

            # Update metadata
            self.files_meta[file_id]["status"] = FileStatus.PARSED
            self.files_meta[file_id]["markdown_file"] = markdown_file_path
            self.files_meta[file_id]["updated_at"] = utc_isoformat()
            if operator_id:
                self.files_meta[file_id]["updated_by"] = operator_id
            self._save_metadata()

            return self.files_meta[file_id]

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to parse file {file_id}: {error_msg}")

            self.files_meta[file_id]["status"] = FileStatus.ERROR_PARSING
            self.files_meta[file_id]["error"] = error_msg
            self.files_meta[file_id]["updated_at"] = utc_isoformat()
            if operator_id:
                self.files_meta[file_id]["updated_by"] = operator_id
            self._save_metadata()

            raise

        finally:
            # Remove from processing queue
            self._remove_from_processing_queue(file_id)

    async def update_file_params(self, db_id: str, file_id: str, params: dict, operator_id: str | None = None) -> None:
        """Update file processing params"""
        if file_id not in self.files_meta:
            raise ValueError(f"File {file_id} not found")

        # Skip if no params to update
        if not params:
            return

        # Merge or overwrite? Usually merge is safer, or replace.
        # User might want to change chunk size.
        current_params = self.files_meta[file_id].get("processing_params", {}) or {}

        logger.debug(f"[update_file_params] file_id={file_id}, current_params={current_params}, new_params={params}")

        current_params.update(params)

        self.files_meta[file_id]["processing_params"] = current_params
        self.files_meta[file_id]["updated_at"] = utc_isoformat()
        if operator_id:
            self.files_meta[file_id]["updated_by"] = operator_id

        logger.debug(f"[update_file_params] file_id={file_id}, updated_params={current_params}")

        self._save_metadata()

    async def _save_markdown_to_minio(self, db_id: str, file_id: str, content: str) -> str:
        """Save markdown content to MinIO and return HTTP URL"""
        from src.storage.minio import get_minio_client

        minio_client = get_minio_client()
        bucket_name = "kb-documents"  # Or reuse existing bucket strategy?
        # Maybe store in 'kb-files' or 'kb-markdowns'
        # Current uploads go to 'kb-files' usually?
        # Let's use 'kb-parsed'
        bucket_name = "kb-parsed"
        await asyncio.to_thread(minio_client.ensure_bucket_exists, bucket_name)

        object_name = f"{db_id}/{file_id}/parsed.md"
        data = content.encode("utf-8")

        # Return standard HTTP URL from UploadResult
        upload_result = await minio_client.aupload_file(
            bucket_name=bucket_name, object_name=object_name, data=data, content_type="text/markdown"
        )

        return upload_result.url

    async def _read_markdown_from_minio(self, file_path: str) -> str:
        """Read markdown content from MinIO"""
        from src.knowledge.utils.kb_utils import parse_minio_url
        from src.storage.minio import get_minio_client

        if not file_path.startswith(("http://", "https://")):
            raise ValueError(f"Invalid MinIO path format: {file_path}")

        bucket_name, object_name = parse_minio_url(file_path)
        minio_client = get_minio_client()

        content_bytes = await minio_client.adownload_file(bucket_name, object_name)
        return content_bytes.decode("utf-8")

    @abstractmethod
    async def index_file(self, db_id: str, file_id: str, operator_id: str | None = None) -> dict:
        """
        Index parsed file (Status: INDEXING -> INDEXED/ERROR_INDEXING)

        Args:
            db_id: Database ID
            file_id: File ID
            operator_id: ID of the user performing the operation

        Returns:
            Updated file metadata
        """
        pass

    def create_database(
        self,
        database_name: str,
        description: str,
        embed_info: dict | None = None,
        llm_info: dict | None = None,
        **kwargs,
    ) -> dict:
        """
        创建数据库

        Args:
            database_name: 数据库名称
            description: 数据库描述
            embed_info: 嵌入模型信息
            llm_info: LLM配置信息
            **kwargs: 其他配置参数

        Returns:
            数据库信息字典
        """
        from src.utils import hashstr

        # 从 kwargs 中获取 is_private 配置
        is_private = kwargs.get("is_private", False)
        prefix = "kb_private_" if is_private else "kb_"
        db_id = f"{prefix}{hashstr(database_name, with_salt=True)}"

        # 创建数据库记录
        # 确保 Pydantic 模型被转换为字典，以便 JSON 序列化
        embed_info_dump = embed_info.model_dump() if hasattr(embed_info, "model_dump") else embed_info
        self.databases_meta[db_id] = {
            "name": database_name,
            "description": description,
            "kb_type": self.kb_type,
            "embed_info": embed_info_dump,
            "llm_info": llm_info.model_dump() if hasattr(llm_info, "model_dump") else llm_info,
            "metadata": kwargs,
            "created_at": utc_isoformat(),
        }
        self._save_metadata()

        # 创建工作目录
        working_dir = os.path.join(self.work_dir, db_id)
        os.makedirs(working_dir, exist_ok=True)

        # 返回数据库信息
        db_dict = self.databases_meta[db_id].copy()
        db_dict["db_id"] = db_id
        db_dict["files"] = {}

        return db_dict

    def delete_database(self, db_id: str) -> dict:
        """
        删除数据库

        Args:
            db_id: 数据库ID

        Returns:
            操作结果
        """
        if db_id in self.databases_meta:
            # 删除相关文件记录
            files_to_delete = [fid for fid, finfo in self.files_meta.items() if finfo.get("database_id") == db_id]
            for file_id in files_to_delete:
                del self.files_meta[file_id]

            # 删除数据库记录
            del self.databases_meta[db_id]
            self._save_metadata()

        # 删除工作目录
        working_dir = os.path.join(self.work_dir, db_id)
        if os.path.exists(working_dir):
            import shutil

            try:
                shutil.rmtree(working_dir)
            except Exception as e:
                logger.error(f"Error deleting working directory {working_dir}: {e}")

        return {"message": "删除成功"}

    def create_folder(self, db_id: str, folder_name: str, parent_id: str | None = None) -> dict:
        """Create a folder in the database."""
        import uuid

        folder_id = f"folder-{uuid.uuid4()}"

        self.files_meta[folder_id] = {
            "file_id": folder_id,
            "filename": folder_name,
            "is_folder": True,
            "parent_id": parent_id,
            "database_id": db_id,
            "created_at": utc_isoformat(),
            "status": "done",
            "path": folder_name,
            "file_type": "folder",
        }
        self._save_metadata()
        return self.files_meta[folder_id]

    @abstractmethod
    async def update_content(self, db_id: str, file_ids: list[str], params: dict | None = None) -> list[dict]:
        """
        更新内容 - 根据file_ids重新解析文件并更新向量库

        Args:
            db_id: 数据库ID
            file_ids: 文件ID列表
            params: 处理参数

        Returns:
            更新结果列表
        """
        pass

    @abstractmethod
    async def aquery(self, query_text: str, db_id: str, **kwargs) -> list[dict]:
        """
        异步查询知识库

        Args:
            query_text: 查询文本
            db_id: 数据库ID
            **kwargs: 查询参数

        Returns:
            一个包含字典的列表，每个字典代表一个检索到的文档块。
        """
        pass

    @abstractmethod
    def get_query_params_config(self, db_id: str, **kwargs) -> dict:
        """
        获取知识库类型的查询参数配置

        Args:
            db_id: 数据库ID
            **kwargs: 额外参数(如 reranker_names 等)

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

    async def export_data(self, db_id: str, format: str = "zip", **kwargs) -> str:
        pass

    def query(self, query_text: str, db_id: str, **kwargs) -> list[dict]:
        """
        同步查询知识库（兼容性方法）

        Args:
            query_text: 查询文本
            db_id: 数据库ID
            **kwargs: 查询参数

        Returns:
            一个包含字典的列表，每个字典代表一个检索到的文档块。
        """
        import asyncio

        logger.warning("query is deprecated, use aquery instead")
        return asyncio.run(self.aquery(query_text, db_id, **kwargs))

    def _get_query_params(self, db_id: str) -> dict:
        """从实例元数据中加载查询参数"""
        if db_id in self.databases_meta:
            query_params_meta = self.databases_meta[db_id].get("query_params", {})
            return query_params_meta.get("options", {})
        return {}

    def get_database_info(self, db_id: str) -> dict | None:
        """
        获取数据库详细信息

        Args:
            db_id: 数据库ID

        Returns:
            数据库信息或None
        """
        if db_id not in self.databases_meta:
            return None

        meta = self.databases_meta[db_id].copy()
        meta["db_id"] = db_id

        # 检查并修复异常的processing状态
        self._check_and_fix_processing_status(db_id)

        # 获取文件信息
        db_files = {}
        for file_id, file_info in self.files_meta.items():
            if file_info.get("database_id") == db_id:
                created_at = self._normalize_timestamp(file_info.get("created_at"))
                db_files[file_id] = {
                    "file_id": file_id,
                    "filename": file_info.get("filename", ""),
                    "path": file_info.get("path", ""),
                    "markdown_file": file_info.get("markdown_file", ""),
                    "type": file_info.get("file_type", ""),
                    "status": file_info.get("status", "done"),
                    "created_at": created_at,
                    "processing_params": file_info.get("processing_params", None),
                    "is_folder": file_info.get("is_folder", False),
                    "parent_id": file_info.get("parent_id", None),
                }

        # 按创建时间倒序排序文件列表
        sorted_files = dict(
            sorted(
                db_files.items(),
                key=lambda item: item[1].get("created_at") or "",
                reverse=True,
            )
        )

        meta["files"] = sorted_files
        meta["row_count"] = len(sorted_files)
        meta["status"] = "已连接"
        return meta

    def get_databases(self) -> dict:
        """
        获取所有数据库信息

        Returns:
            数据库列表
        """
        databases = []
        for db_id, meta in self.databases_meta.items():
            # 检查并修复异常的processing状态
            self._check_and_fix_processing_status(db_id)

            db_dict = meta.copy()
            db_dict["db_id"] = db_id

            # 获取文件信息
            db_files = {}
            for file_id, file_info in self.files_meta.items():
                if file_info.get("database_id") == db_id:
                    created_at = self._normalize_timestamp(file_info.get("created_at"))
                    db_files[file_id] = {
                        "file_id": file_id,
                        "filename": file_info.get("filename", ""),
                        "path": file_info.get("path", ""),
                        "markdown_file": file_info.get("markdown_file", ""),
                        "type": file_info.get("file_type", ""),
                        "status": file_info.get("status", "done"),
                        "created_at": created_at,
                        "is_folder": file_info.get("is_folder", False),
                        "parent_id": file_info.get("parent_id", None),
                    }

            # 按创建时间倒序排序文件列表
            sorted_files = dict(
                sorted(
                    db_files.items(),
                    key=lambda item: item[1].get("created_at") or "",
                    reverse=True,
                )
            )

            db_dict["files"] = sorted_files
            db_dict["row_count"] = len(sorted_files)
            db_dict["status"] = "已连接"
            databases.append(db_dict)

        return {"databases": databases}

    @classmethod
    def _add_to_processing_queue(cls, file_id: str) -> None:
        """
        将文件添加到处理队列

        Args:
            file_id: 文件ID
        """
        with cls._processing_lock:
            cls._processing_files.add(file_id)
            logger.debug(f"Added file {file_id} to processing queue")

    @classmethod
    def _remove_from_processing_queue(cls, file_id: str) -> None:
        """
        从处理队列中移除文件

        Args:
            file_id: 文件ID
        """
        with cls._processing_lock:
            cls._processing_files.discard(file_id)
            logger.debug(f"Removed file {file_id} from processing queue")

    @classmethod
    def _is_file_in_processing_queue(cls, file_id: str) -> bool:
        """
        检查文件是否在处理队列中

        Args:
            file_id: 文件ID

        Returns:
            bool: 文件是否在处理队列中
        """
        with cls._processing_lock:
            return file_id in cls._processing_files

    def _check_and_fix_processing_status(self, db_id: str) -> None:
        """
        检查并修复异常的处理中状态
        如果文件状态为处理中但实际不在处理队列中，则修改为相应的错误状态

        Args:
            db_id: 数据库ID
        """
        try:
            status_changed = False

            # 定义需要检查的中间状态及其对应的错误状态
            intermediate_states = {
                FileStatus.PARSING: FileStatus.ERROR_PARSING,
                FileStatus.INDEXING: FileStatus.ERROR_INDEXING,
                "processing": "failed",  # 兼容旧状态
            }

            # 检查该数据库下所有中间状态的文件
            for file_id, file_info in self.files_meta.items():
                if file_info.get("database_id") == db_id:
                    current_status = file_info.get("status")

                    if current_status in intermediate_states:
                        # 检查文件是否真的在处理队列中
                        if not self._is_file_in_processing_queue(file_id):
                            error_status = intermediate_states[current_status]
                            logger.warning(
                                f"File {file_id} has {current_status} status but is not in processing queue, "
                                f"marking as {error_status}"
                            )
                            self.files_meta[file_id]["status"] = error_status
                            self.files_meta[file_id]["error"] = (
                                f"{current_status.capitalize()} interrupted - process not found in queue"
                            )
                            self.files_meta[file_id]["updated_at"] = utc_isoformat()
                            status_changed = True

            # 如果有状态变更，保存元数据
            if status_changed:
                self._save_metadata()
                logger.info(f"Fixed interrupted processing status for database {db_id}")

        except Exception as e:
            logger.error(f"Error checking processing status for database {db_id}: {e}")

    async def delete_folder(self, db_id: str, folder_id: str) -> None:
        """
        Recursively delete a folder and its content.

        Args:
            db_id: Database ID
            folder_id: Folder ID to delete
        """
        # Find all children
        children = [
            fid
            for fid, meta in self.files_meta.items()
            if meta.get("database_id") == db_id and meta.get("parent_id") == folder_id
        ]

        for child_id in children:
            child_meta = self.files_meta.get(child_id)
            if child_meta and child_meta.get("is_folder"):
                await self.delete_folder(db_id, child_id)
            else:
                await self.delete_file(db_id, child_id)

        # Delete the folder itself
        # We call delete_file which should handle the actual removal.
        # Implementations should ensure they handle folder deletion gracefully (e.g. skip vector deletion)
        await self.delete_file(db_id, folder_id)

    async def move_file(self, db_id: str, file_id: str, new_parent_id: str | None) -> dict:
        """
        Move a file or folder to a new parent folder.

        Args:
            db_id: Database ID
            file_id: File/Folder ID to move
            new_parent_id: New parent folder ID (None for root)

        Returns:
            dict: Updated metadata
        """
        if file_id not in self.files_meta:
            raise ValueError(f"File {file_id} not found")

        meta = self.files_meta[file_id]
        if meta.get("database_id") != db_id:
            raise ValueError(f"File {file_id} does not belong to database {db_id}")

        # Basic cycle detection for folders
        if meta.get("is_folder") and new_parent_id:
            # Check if new_parent_id is a child of file_id (or is file_id itself)
            if new_parent_id == file_id:
                raise ValueError("Cannot move a folder into itself")

            # Walk up the tree from new_parent_id
            current = new_parent_id
            while current:
                parent_meta = self.files_meta.get(current)
                if not parent_meta:
                    break  # Should not happen if integrity is maintained
                if current == file_id:
                    raise ValueError("Cannot move a folder into its own subfolder")
                current = parent_meta.get("parent_id")

        meta["parent_id"] = new_parent_id
        self._save_metadata()
        return meta

    @abstractmethod
    async def delete_file(self, db_id: str, file_id: str) -> None:
        """
        删除文件

        Args:
            db_id: 数据库ID
            file_id: 文件ID
        """
        pass

    @abstractmethod
    async def get_file_basic_info(self, db_id: str, file_id: str) -> dict:
        """
        获取文件基本信息（仅元数据）

        Args:
            db_id: 数据库ID
            file_id: 文件ID

        Returns:
            dict: 包含文件基本信息的字典
        """
        pass

    @abstractmethod
    async def get_file_content(self, db_id: str, file_id: str) -> dict:
        """
        获取文件内容信息（chunks和lines）

        Args:
            db_id: 数据库ID
            file_id: 文件ID

        Returns:
            dict: 包含文件内容信息的字典
        """
        pass

    @abstractmethod
    async def get_file_info(self, db_id: str, file_id: str) -> dict:
        """
        获取文件完整信息（基本信息+内容信息）- 保持向后兼容

        Args:
            db_id: 数据库ID
            file_id: 文件ID

        Returns:
            dict: 包含文件信息和chunks的字典
        """
        pass

    def get_db_upload_path(self, db_id: str | None = None) -> str:
        """
        获取数据库上传路径

        Args:
            db_id: 数据库ID，可选

        Returns:
            上传路径
        """
        if db_id:
            uploads_folder = os.path.join(self.work_dir, db_id, "uploads")
            os.makedirs(uploads_folder, exist_ok=True)
            return uploads_folder

        general_uploads = os.path.join(self.work_dir, "uploads")
        os.makedirs(general_uploads, exist_ok=True)
        return general_uploads

    def update_database(self, db_id: str, name: str, description: str, llm_info: dict = None) -> dict:
        """
        更新数据库

        Args:
            db_id: 数据库ID
            name: 新名称
            description: 新描述
            llm_info: LLM配置信息（可选，仅用于 LightRAG 类型知识库）

        Returns:
            更新后的数据库信息
        """
        if db_id not in self.databases_meta:
            raise ValueError(f"数据库 {db_id} 不存在")

        self.databases_meta[db_id]["name"] = name
        self.databases_meta[db_id]["description"] = description

        # 如果提供了 llm_info，则更新（仅针对 LightRAG 类型）
        if llm_info is not None:
            self.databases_meta[db_id]["llm_info"] = llm_info

        self._save_metadata()

        return self.get_database_info(db_id)

    def get_retrievers(self) -> dict[str, dict]:
        """
        获取所有检索器

        Returns:
            检索器字典
        """
        retrievers = {}
        for db_id, meta in self.databases_meta.items():

            def make_retriever(db_id):
                async def retriever(query_text, **kwargs):
                    return await self.aquery(query_text, db_id, agent_call=True, **kwargs)

                return retriever

            retrievers[db_id] = {
                "name": meta["name"],
                "description": meta["description"],
                "retriever": make_retriever(db_id),
                "metadata": meta,
            }
        return retrievers

    def _load_metadata(self):
        """加载元数据"""
        meta_file = os.path.join(self.work_dir, f"metadata_{self.kb_type}.json")

        if os.path.exists(meta_file):
            try:
                with open(meta_file, encoding="utf-8") as f:
                    data = json.load(f)
                    self.databases_meta = data.get("databases", {})
                    self.files_meta = data.get("files", {})
                    self.benchmarks_meta = data.get("benchmarks", {})
                logger.info(f"Loaded {self.kb_type} metadata for {len(self.databases_meta)} databases")
            except Exception as e:
                logger.error(f"Failed to load {self.kb_type} metadata: {e}")
                # 尝试从备份恢复
                backup_file = f"{meta_file}.backup"
                if os.path.exists(backup_file):
                    try:
                        with open(backup_file, encoding="utf-8") as f:
                            data = json.load(f)
                            self.databases_meta = data.get("databases", {})
                            self.files_meta = data.get("files", {})
                            self.benchmarks_meta = data.get("benchmarks", {})
                        logger.info(f"Loaded {self.kb_type} metadata from backup")
                        # 恢复备份文件
                        shutil.copy2(backup_file, meta_file)
                        return
                    except Exception as backup_e:
                        logger.error(f"Failed to load backup: {backup_e}")

                # 如果加载失败，初始化为空状态
                logger.warning(f"Initializing empty {self.kb_type} metadata")
                self.databases_meta = {}
                self.files_meta = {}
                self.benchmarks_meta = {}

    def _serialize_metadata(self, obj):
        """递归序列化元数据中的 Pydantic 模型"""
        if hasattr(obj, "dict"):
            return obj.dict()
        elif isinstance(obj, dict):
            return {k: self._serialize_metadata(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._serialize_metadata(item) for item in obj]
        else:
            return obj

    def _save_metadata(self):
        """保存元数据"""
        self._normalize_metadata_state()
        meta_file = os.path.join(self.work_dir, f"metadata_{self.kb_type}.json")
        backup_file = f"{meta_file}.backup"

        try:
            # 创建简单备份
            if os.path.exists(meta_file):
                shutil.copy2(meta_file, backup_file)

            # 准备数据并序列化 Pydantic 模型
            data = {
                "databases": self._serialize_metadata(self.databases_meta),
                "files": self._serialize_metadata(self.files_meta),
                "benchmarks": self._serialize_metadata(self.benchmarks_meta),
                "kb_type": self.kb_type,
                "updated_at": utc_isoformat(),
            }

            # 原子性写入（使用临时文件）
            with tempfile.NamedTemporaryFile(
                mode="w", dir=os.path.dirname(meta_file), prefix=".tmp_", suffix=".json", delete=False
            ) as tmp_file:
                json.dump(data, tmp_file, ensure_ascii=False, indent=2)
                temp_path = tmp_file.name

            os.replace(temp_path, meta_file)
            logger.debug(f"Saved {self.kb_type} metadata")

        except Exception as e:
            logger.error(f"Failed to save {self.kb_type} metadata: {e}")
            # 尝试恢复备份
            if os.path.exists(backup_file):
                try:
                    shutil.copy2(backup_file, meta_file)
                    logger.info("Restored metadata from backup")
                except Exception as restore_e:
                    logger.error(f"Failed to restore backup: {restore_e}")
            raise e
