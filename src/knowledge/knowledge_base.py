import os
import json
import time
from abc import ABC, abstractmethod
from typing import Any
from collections.abc import AsyncGenerator
from pathlib import Path
from datetime import datetime

from src.utils import logger


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

        # 初始化类级别的锁
        if KnowledgeBase._processing_lock is None:
            KnowledgeBase._processing_lock = threading.Lock()

        os.makedirs(work_dir, exist_ok=True)

        # 自动加载元数据
        self._load_metadata()

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

    def create_database(self, database_name: str, description: str,
                       embed_info: dict | None = None, llm_info: dict | None = None, **kwargs) -> dict:
        """
        创建数据库

        Args:
            database_name: 数据库名称
            description: 数据库描述
            embed_info: 嵌入模型信息
            **kwargs: 其他配置参数

        Returns:
            数据库信息字典
        """
        from src.utils import hashstr

        db_id = f"kb_{hashstr(database_name, with_salt=True)}"

        # 创建数据库记录
        self.databases_meta[db_id] = {
            "name": database_name,
            "description": description,
            "kb_type": self.kb_type,
            "embed_info": embed_info,
            "llm_info": llm_info,
            "metadata": kwargs,
            "created_at": datetime.now().isoformat()
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
            files_to_delete = [fid for fid, finfo in self.files_meta.items()
                             if finfo.get("database_id") == db_id]
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

    @abstractmethod
    async def add_content(self, db_id: str, items: list[str],
                         params: dict | None = None) -> list[dict]:
        """
        添加内容（文件/URL）

        Args:
            db_id: 数据库ID
            items: 文件路径或URL列表
            params: 处理参数

        Returns:
            处理结果列表
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

    async def export_data(self, db_id: str, format: str = 'zip', **kwargs) -> str:
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
                db_files[file_id] = {
                    "file_id": file_id,
                    "filename": file_info.get("filename", ""),
                    "path": file_info.get("path", ""),
                    "type": file_info.get("file_type", ""),
                    "status": file_info.get("status", "done"),
                    "created_at": file_info.get("created_at", time.time())
                }

        # 按创建时间倒序排序文件列表
        sorted_files = dict(sorted(db_files.items(), key=lambda x: x[1].get("created_at", 0), reverse=True))

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
                    db_files[file_id] = {
                        "file_id": file_id,
                        "filename": file_info.get("filename", ""),
                        "path": file_info.get("path", ""),
                        "type": file_info.get("file_type", ""),
                        "status": file_info.get("status", "done"),
                        "created_at": file_info.get("created_at", time.time())
                    }

            # 按创建时间倒序排序文件列表
            sorted_files = dict(sorted(db_files.items(), key=lambda x: x[1].get("created_at", 0), reverse=True))

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
        检查并修复异常的processing状态
        如果文件状态为processing但实际不在处理队列中，则修改为error状态

        Args:
            db_id: 数据库ID
        """
        try:
            status_changed = False

            # 检查该数据库下所有processing状态的文件
            for file_id, file_info in self.files_meta.items():
                if (file_info.get("database_id") == db_id and
                    file_info.get("status") == "processing"):

                    # 检查文件是否真的在处理队列中
                    if not self._is_file_in_processing_queue(file_id):
                        logger.warning(f"File {file_id} has processing status but is not in processing queue, marking as error")
                        self.files_meta[file_id]["status"] = "error"
                        self.files_meta[file_id]["error"] = "Processing interrupted - file not found in processing queue"
                        status_changed = True

            # 如果有状态变更，保存元数据
            if status_changed:
                self._save_metadata()
                logger.info(f"Fixed processing status for database {db_id}")

        except Exception as e:
            logger.error(f"Error checking processing status for database {db_id}: {e}")

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
    async def get_file_info(self, db_id: str, file_id: str) -> dict:
        """
        获取文件信息和chunks

        Args:
            db_id: 数据库ID
            file_id: 文件ID

        Returns:
            文件信息和chunks
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

    def update_database(self, db_id: str, name: str, description: str) -> dict:
        """
        更新数据库

        Args:
            db_id: 数据库ID
            name: 新名称
            description: 新描述

        Returns:
            更新后的数据库信息
        """
        if db_id not in self.databases_meta:
            raise ValueError(f"数据库 {db_id} 不存在")

        self.databases_meta[db_id]["name"] = name
        self.databases_meta[db_id]["description"] = description
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
                async def retriever(query_text):
                    return await self.aquery(query_text, db_id)
                return retriever

            retrievers[db_id] = {
                "name": meta["name"],
                "description": meta["description"],
                "retriever": make_retriever(db_id),
                "metadata": meta
            }
        return retrievers

    def _load_metadata(self):
        """加载元数据"""
        meta_file = os.path.join(self.work_dir, f"metadata_{self.kb_type}.json")
        if os.path.exists(meta_file):
            try:
                with open(meta_file, encoding='utf-8') as f:
                    data = json.load(f)
                    self.databases_meta = data.get("databases", {})
                    self.files_meta = data.get("files", {})
                logger.info(f"Loaded {self.kb_type} metadata for {len(self.databases_meta)} databases")
            except Exception as e:
                logger.error(f"Failed to load {self.kb_type} metadata: {e}")

    def _save_metadata(self):
        """保存元数据"""
        meta_file = os.path.join(self.work_dir, f"metadata_{self.kb_type}.json")
        try:
            data = {
                "databases": self.databases_meta,
                "files": self.files_meta,
                "kb_type": self.kb_type,
                "updated_at": datetime.now().isoformat()
            }
            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save {self.kb_type} metadata: {e}")
