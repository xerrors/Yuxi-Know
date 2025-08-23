import os
import json
import time
import asyncio
from typing import Any
from datetime import datetime

from src.knowledge.knowledge_base import KnowledgeBase, KBNotFoundError, KBOperationError
from src.knowledge.kb_factory import KnowledgeBaseFactory
from src.utils import logger


class KnowledgeBaseManager:
    """
    知识库管理器

    统一管理多种类型的知识库实例，提供统一的外部接口
    """

    def __init__(self, work_dir: str):
        """
        初始化知识库管理器

        Args:
            work_dir: 工作目录
        """
        self.work_dir = work_dir
        os.makedirs(work_dir, exist_ok=True)

        # 知识库实例缓存 {kb_type: kb_instance}
        self.kb_instances: dict[str, KnowledgeBase] = {}

        # 全局数据库元信息 {db_id: metadata_with_kb_type}
        self.global_databases_meta: dict[str, dict] = {}

        # 元数据锁
        self._metadata_lock = asyncio.Lock()

        # 加载全局元数据
        self._load_global_metadata()

        # 初始化已存在的知识库实例
        self._initialize_existing_kbs()

        logger.info("KnowledgeBaseManager initialized")

    def _load_global_metadata(self):
        """加载全局元数据"""
        meta_file = os.path.join(self.work_dir, "global_metadata.json")
        if os.path.exists(meta_file):
            try:
                with open(meta_file, encoding='utf-8') as f:
                    data = json.load(f)
                    self.global_databases_meta = data.get("databases", {})
                logger.info(f"Loaded global metadata for {len(self.global_databases_meta)} databases")
            except Exception as e:
                logger.error(f"Failed to load global metadata: {e}")

    def _save_global_metadata(self):
        """保存全局元数据"""
        meta_file = os.path.join(self.work_dir, "global_metadata.json")
        data = {
            "databases": self.global_databases_meta,
            "updated_at": datetime.now().isoformat(),
            "version": "2.0"
        }
        with open(meta_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _initialize_existing_kbs(self):
        """初始化已存在的知识库实例"""
        kb_types_in_use = set()
        for db_meta in self.global_databases_meta.values():
            kb_type = db_meta.get("kb_type", "lightrag")  # 默认为lightrag
            kb_types_in_use.add(kb_type)

        # 为每种使用中的知识库类型创建实例
        for kb_type in kb_types_in_use:
            try:
                self._get_or_create_kb_instance(kb_type)
            except Exception as e:
                logger.error(f"Failed to initialize {kb_type} knowledge base: {e}")

    def _get_or_create_kb_instance(self, kb_type: str) -> KnowledgeBase:
        """
        获取或创建知识库实例

        Args:
            kb_type: 知识库类型

        Returns:
            知识库实例
        """
        if kb_type in self.kb_instances:
            return self.kb_instances[kb_type]

        # 创建新的知识库实例
        kb_work_dir = os.path.join(self.work_dir, f"{kb_type}_data")
        kb_instance = KnowledgeBaseFactory.create(kb_type, kb_work_dir)

        self.kb_instances[kb_type] = kb_instance
        logger.info(f"Created {kb_type} knowledge base instance")
        return kb_instance

    def _get_kb_for_database(self, db_id: str) -> KnowledgeBase:
        """
        根据数据库ID获取对应的知识库实例

        Args:
            db_id: 数据库ID

        Returns:
            知识库实例

        Raises:
            KBNotFoundError: 数据库不存在或知识库类型不支持
        """
        if db_id not in self.global_databases_meta:
            raise KBNotFoundError(f"Database {db_id} not found")

        kb_type = self.global_databases_meta[db_id].get("kb_type", "lightrag")

        if not KnowledgeBaseFactory.is_type_supported(kb_type):
            raise KBNotFoundError(f"Unsupported knowledge base type: {kb_type}")

        return self._get_or_create_kb_instance(kb_type)

    # =============================================================================
    # 统一的外部接口 - 与原始 LightRagBasedKB 兼容
    # =============================================================================

    def get_databases(self) -> dict:
        """获取所有数据库信息"""
        all_databases = []

        # 收集所有知识库的数据库信息
        for kb_type, kb_instance in self.kb_instances.items():
            kb_databases = kb_instance.get_databases()["databases"]
            all_databases.extend(kb_databases)

        return {"databases": all_databases}

    async def create_database(self, database_name: str, description: str, kb_type: str, embed_info: dict | None = None, **kwargs) -> dict:
        """
        创建数据库

        Args:
            database_name: 数据库名称
            description: 数据库描述
            kb_type: 知识库类型，默认为lightrag
            embed_info: 嵌入模型信息
            **kwargs: 其他配置参数，包括chunk_size和chunk_overlap

        Returns:
            数据库信息字典
        """
        if not KnowledgeBaseFactory.is_type_supported(kb_type):
            available_types = list(KnowledgeBaseFactory.get_available_types().keys())
            raise ValueError(f"Unsupported knowledge base type: {kb_type}. Available types: {available_types}")

        kb_instance = self._get_or_create_kb_instance(kb_type)

        db_info = kb_instance.create_database(database_name, description,
                                            embed_info, **kwargs)
        db_id = db_info["db_id"]

        async with self._metadata_lock:
            self.global_databases_meta[db_id] = {
                "name": database_name,
                "description": description,
                "kb_type": kb_type,
                "created_at": datetime.now().isoformat(),
                "additional_params": kwargs.copy()
            }
            self._save_global_metadata()

        logger.info(f"Created {kb_type} database: {database_name} ({db_id}) with {kwargs}")
        return db_info

    async def delete_database(self, db_id: str) -> dict:
        """删除数据库"""
        try:
            kb_instance = self._get_kb_for_database(db_id)
            result = kb_instance.delete_database(db_id)

            async with self._metadata_lock:
                if db_id in self.global_databases_meta:
                    del self.global_databases_meta[db_id]
                    self._save_global_metadata()

            return result
        except KBNotFoundError as e:
            logger.warning(f"Database {db_id} not found during deletion: {e}")
            return {"message": "删除成功"}

    async def add_content(self, db_id: str, items: list[str], params: dict | None = None) -> list[dict]:
        """添加内容（文件/URL）"""
        kb_instance = self._get_kb_for_database(db_id)
        return await kb_instance.add_content(db_id, items, params or {})

    async def aquery(self, query_text: str, db_id: str, **kwargs) -> str:
        """异步查询知识库"""
        kb_instance = self._get_kb_for_database(db_id)
        return await kb_instance.aquery(query_text, db_id, **kwargs)

    async def export_data(self, db_id: str, format: str = 'zip', **kwargs) -> str:
        """导出知识库数据"""
        kb_instance = self._get_kb_for_database(db_id)
        return await kb_instance.export_data(db_id, format=format, **kwargs)

    def query(self, query_text: str, db_id: str, **kwargs) -> str:
        """同步查询知识库（兼容性方法）"""
        kb_instance = self._get_kb_for_database(db_id)
        return kb_instance.query(query_text, db_id, **kwargs)

    def get_database_info(self, db_id: str) -> dict | None:
        """获取数据库详细信息"""
        try:
            kb_instance = self._get_kb_for_database(db_id)
            db_info = kb_instance.get_database_info(db_id)

            # 添加全局元数据中的additional_params信息
            if db_info and db_id in self.global_databases_meta:
                global_meta = self.global_databases_meta[db_id]
                additional_params = global_meta.get("additional_params", {})
                if additional_params:
                    db_info["additional_params"] = additional_params

            return db_info
        except KBNotFoundError:
            return None

    async def delete_file(self, db_id: str, file_id: str) -> None:
        """删除文件"""
        kb_instance = self._get_kb_for_database(db_id)
        await kb_instance.delete_file(db_id, file_id)

    async def get_file_info(self, db_id: str, file_id: str) -> dict:
        """获取文件信息"""
        kb_instance = self._get_kb_for_database(db_id)
        return await kb_instance.get_file_info(db_id, file_id)

    def get_db_upload_path(self, db_id: str | None = None) -> str:
        """获取数据库上传路径"""
        if db_id:
            try:
                kb_instance = self._get_kb_for_database(db_id)
                return kb_instance.get_db_upload_path(db_id)
            except KBNotFoundError:
                # 如果数据库不存在，创建通用上传路径
                pass

        # 通用上传路径
        general_uploads = os.path.join(self.work_dir, "uploads")
        os.makedirs(general_uploads, exist_ok=True)
        return general_uploads

    async def update_database(self, db_id: str, name: str, description: str) -> dict:
        """更新数据库"""
        kb_instance = self._get_kb_for_database(db_id)
        result = kb_instance.update_database(db_id, name, description)

        async with self._metadata_lock:
            if db_id in self.global_databases_meta:
                self.global_databases_meta[db_id]["name"] = name
                self.global_databases_meta[db_id]["description"] = description
                self._save_global_metadata()

        return result

    def get_retrievers(self) -> dict[str, dict]:
        """获取所有检索器"""
        all_retrievers = {}

        # 收集所有知识库的检索器
        for kb_instance in self.kb_instances.values():
            retrievers = kb_instance.get_retrievers()
            all_retrievers.update(retrievers)

        return all_retrievers

    # =============================================================================
    # 管理器特有的方法
    # =============================================================================

    def get_supported_kb_types(self) -> dict[str, dict]:
        """获取支持的知识库类型"""
        return KnowledgeBaseFactory.get_available_types()

    def get_kb_instance_info(self) -> dict[str, dict]:
        """获取知识库实例信息"""
        info = {}
        for kb_type, kb_instance in self.kb_instances.items():
            info[kb_type] = {
                "work_dir": kb_instance.work_dir,
                "database_count": len(kb_instance.databases_meta),
                "file_count": len(kb_instance.files_meta)
            }
        return info

    def get_statistics(self) -> dict:
        """获取统计信息"""
        stats = {
            "total_databases": len(self.global_databases_meta),
            "kb_types": {},
            "total_files": 0
        }

        # 按知识库类型统计
        for db_meta in self.global_databases_meta.values():
            kb_type = db_meta.get("kb_type", "lightrag")
            if kb_type not in stats["kb_types"]:
                stats["kb_types"][kb_type] = 0
            stats["kb_types"][kb_type] += 1

        # 统计文件总数
        for kb_instance in self.kb_instances.values():
            stats["total_files"] += len(kb_instance.files_meta)

        return stats

    # =============================================================================
    # 兼容性方法 - 为了支持现有的 graph_router.py
    # =============================================================================

    async def _get_lightrag_instance(self, db_id: str):
        """
        获取 LightRAG 实例（兼容性方法）

        Args:
            db_id: 数据库ID

        Returns:
            LightRAG 实例，如果数据库不是 lightrag 类型则返回 None

        Raises:
            ValueError: 如果数据库不存在或不是 lightrag 类型
        """
        try:
            # 检查数据库是否存在
            if db_id not in self.global_databases_meta:
                logger.error(f"Database {db_id} not found in global metadata")
                return None

            # 检查是否是 LightRAG 类型
            kb_type = self.global_databases_meta[db_id].get("kb_type", "lightrag")
            if kb_type != "lightrag":
                logger.error(f"Database {db_id} is not a LightRAG type (actual type: {kb_type})")
                raise ValueError(f"Database {db_id} is not a LightRAG knowledge base")

            # 获取 LightRAG 知识库实例
            kb_instance = self._get_kb_for_database(db_id)

            # 如果不是 LightRagKB 实例，返回错误
            if not hasattr(kb_instance, '_get_lightrag_instance'):
                logger.error(f"Knowledge base instance for {db_id} is not LightRagKB")
                return None

            # 调用 LightRagKB 的方法获取 LightRAG 实例
            return await kb_instance._get_lightrag_instance(db_id)

        except Exception as e:
            logger.error(f"Failed to get LightRAG instance for {db_id}: {e}")
            return None

    def is_lightrag_database(self, db_id: str) -> bool:
        """
        检查数据库是否是 LightRAG 类型

        Args:
            db_id: 数据库ID

        Returns:
            是否是 LightRAG 类型的数据库
        """
        if db_id not in self.global_databases_meta:
            return False

        kb_type = self.global_databases_meta[db_id].get("kb_type", "lightrag")
        return kb_type == "lightrag"

    def get_lightrag_databases(self) -> list[dict]:
        """
        获取所有 LightRAG 类型的数据库

        Returns:
            LightRAG 数据库列表
        """
        lightrag_databases = []

        all_databases = self.get_databases()["databases"]
        for db in all_databases:
            if db.get("kb_type", "lightrag") == "lightrag":
                lightrag_databases.append(db)

        return lightrag_databases
