import os
import time
import traceback
import json
import asyncio
from pathlib import Path
from typing import Any
from datetime import datetime
from functools import partial

from pymilvus import (
    connections, utility, Collection, CollectionSchema,
    FieldSchema, DataType, db
)

from src import config
from src.models.embedding import OtherEmbedding
from src.knowledge.knowledge_base import KnowledgeBase
from src.knowledge.indexing import process_url_to_markdown, process_file_to_markdown
from src.knowledge.kb_utils import split_text_into_chunks, split_text_into_qa_chunks, prepare_item_metadata, get_embedding_config
from src.utils import logger, hashstr

MILVUS_AVAILABLE = True


class MilvusKB(KnowledgeBase):
    """基于 Milvus 的生产级向量知识库实现"""

    def __init__(self, work_dir: str, **kwargs):
        """
        初始化 Milvus 知识库

        Args:
            work_dir: 工作目录
            **kwargs: 其他配置参数
        """
        super().__init__(work_dir)

        if not MILVUS_AVAILABLE:
            raise ImportError("pymilvus is not installed. Please install it with: pip install pymilvus")

        # Milvus 配置
        # self.milvus_host = kwargs.get('milvus_host', os.getenv('MILVUS_HOST', 'localhost'))
        # self.milvus_port = kwargs.get('milvus_port', int(os.getenv('MILVUS_PORT', '19530')))
        self.milvus_token = kwargs.get('milvus_token', os.getenv('MILVUS_TOKEN', ''))
        self.milvus_uri = kwargs.get('milvus_uri', os.getenv('MILVUS_URI', 'http://localhost:19530'))
        self.milvus_db = kwargs.get('milvus_db', 'yuxi_know')

        # 连接名称
        self.connection_alias = f"milvus_{hashstr(work_dir, 6)}"

        # 存储集合映射 {db_id: Collection}
        self.collections: dict[str, Any] = {}

        # 分块配置
        self.chunk_size = kwargs.get('chunk_size', 1000)
        self.chunk_overlap = kwargs.get('chunk_overlap', 200)

        # 元数据锁
        self._metadata_lock = asyncio.Lock()

        # 初始化连接
        self._init_connection()

        logger.info("MilvusKB initialized")

    @property
    def kb_type(self) -> str:
        """知识库类型标识"""
        return "milvus"

    def _init_connection(self):
        """初始化 Milvus 连接"""
        try:
            # 连接到 Milvus
            connections.connect(
                alias=self.connection_alias,
                uri=self.milvus_uri,
                token=self.milvus_token
            )

            # 创建数据库（如果不存在）
            try:
                if self.milvus_db not in db.list_database():
                    db.create_database(self.milvus_db)
                db.using_database(self.milvus_db)
            except Exception as e:
                logger.warning(f"Database operation failed, using default: {e}")

            logger.info(f"Connected to Milvus at {self.milvus_uri}")

        except Exception as e:
            logger.error(f"Failed to connect to Milvus: {e}")
            raise

    async def _create_kb_instance(self, db_id: str, kb_config: dict) -> Any:
        """创建 Milvus 集合"""
        logger.info(f"Creating Milvus collection for {db_id}")

        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        embed_info = self.databases_meta[db_id].get("embed_info", {})
        collection_name = db_id

        try:
            # 检查集合是否存在
            if utility.has_collection(collection_name, using=self.connection_alias):
                collection = Collection(
                    name=collection_name,
                    using=self.connection_alias
                )

                # 检查嵌入模型是否匹配
                description = collection.description
                expected_model = embed_info.get("name") if embed_info else "default"

                if expected_model not in description:
                    logger.warning(f"Collection {collection_name} model mismatch, recreating...")
                    utility.drop_collection(collection_name, using=self.connection_alias)
                    raise Exception("Model mismatch, recreating collection")

                logger.info(f"Retrieved existing collection: {collection_name}")
            else:
                raise Exception("Collection not found, creating new one")

        except Exception:
            # 创建新集合
            embedding_dim = embed_info.get("dimension", 1024) if embed_info else 1024
            model_name = embed_info.get("name", "default") if embed_info else "default"

            # 定义集合Schema
            fields = [
                FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=100, is_primary=True),
                FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=500),
                FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=100),
                FieldSchema(name="file_id", dtype=DataType.VARCHAR, max_length=100),
                FieldSchema(name="chunk_index", dtype=DataType.INT64),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=embedding_dim)
            ]

            schema = CollectionSchema(
                fields=fields,
                description=f"Knowledge base collection for {db_id} using {model_name}"
            )

            # 创建集合
            collection = Collection(
                name=collection_name,
                schema=schema,
                using=self.connection_alias
            )

            # 创建索引
            index_params = {
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 1024}
            }
            collection.create_index("embedding", index_params)

            logger.info(f"Created new Milvus collection: {collection_name}")

        return collection

    async def _initialize_kb_instance(self, instance: Any) -> None:
        """初始化 Milvus 集合（加载到内存）"""
        try:
            instance.load()
            logger.info("Milvus collection loaded into memory")
        except Exception as e:
            logger.warning(f"Failed to load collection into memory: {e}")

    def _get_async_embedding_function(self, embed_info: dict):
        """获取 embedding 函数"""
        config_dict = get_embedding_config(embed_info)
        embedding_model = OtherEmbedding(
            model=config_dict.get("model"),
            base_url=config_dict.get("base_url"),
            api_key=config_dict.get("api_key"),
        )

        return partial(embedding_model.abatch_encode, batch_size=40)

    def _get_embedding_function(self, embed_info: dict):
        """获取 embedding 函数"""
        config_dict = get_embedding_config(embed_info)
        embedding_model = OtherEmbedding(
            model=config_dict.get("model"),
            base_url=config_dict.get("base_url"),
            api_key=config_dict.get("api_key"),
        )

        return partial(embedding_model.batch_encode, batch_size=40)

    async def _get_milvus_collection(self, db_id: str):
        """获取或创建 Milvus 集合"""
        if db_id in self.collections:
            return self.collections[db_id]

        if db_id not in self.databases_meta:
            return None

        try:
            # 创建集合
            collection = await self._create_kb_instance(db_id, {})
            await self._initialize_kb_instance(collection)

            self.collections[db_id] = collection
            return collection

        except Exception as e:
            logger.error(f"Failed to create Milvus collection for {db_id}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def _split_text_into_chunks(self, text: str, file_id: str, filename: str, params: dict) -> list[dict]:
        """将文本分割成块"""
        # 检查是否使用QA分割模式
        use_qa_split = params.get('use_qa_split', False)

        if use_qa_split:
            # 使用QA分割模式
            qa_separator = params.get('qa_separator', '\n\n\n')
            return split_text_into_qa_chunks(text, file_id, filename, qa_separator, params)
        else:
            # 使用传统分割模式
            return split_text_into_chunks(text, file_id, filename, params)

    async def add_content(self, db_id: str, items: list[str],
                         params: dict | None = {}) -> list[dict]:
        """添加内容（文件/URL）"""
        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        collection = await self._get_milvus_collection(db_id)
        if not collection:
            raise ValueError(f"Failed to get Milvus collection for {db_id}")

        embed_info = self.databases_meta[db_id].get("embed_info", {})
        embedding_function = self._get_async_embedding_function(embed_info)

        content_type = params.get('content_type', 'file') if params else 'file'
        processed_items_info = []

        for item in items:
            metadata = prepare_item_metadata(item, content_type, db_id)
            file_id = metadata["file_id"]
            filename = metadata["filename"]

            file_record = metadata.copy()
            del file_record["file_id"]
            async with self._metadata_lock:
                self.files_meta[file_id] = file_record
                self._save_metadata()

            file_record["file_id"] = file_id

            # 添加到处理队列
            self._add_to_processing_queue(file_id)

            try:
                if content_type == "file":
                    markdown_content = await process_file_to_markdown(item, params=params)
                else:
                    markdown_content = await process_url_to_markdown(item, params=params)

                chunks = self._split_text_into_chunks(markdown_content, file_id, filename, params)
                logger.info(f"Split {filename} into {len(chunks)} chunks")

                if chunks:
                    texts = [chunk["content"] for chunk in chunks]
                    embeddings = await embedding_function(texts)

                    entities = [
                        [chunk["id"] for chunk in chunks],
                        [chunk["content"] for chunk in chunks],
                        [chunk["source"] for chunk in chunks],
                        [chunk["chunk_id"] for chunk in chunks],
                        [chunk["file_id"] for chunk in chunks],
                        [chunk["chunk_index"] for chunk in chunks],
                        embeddings
                    ]

                    def _insert_and_flush():
                        collection.insert(entities)
                        collection.flush()

                    await asyncio.to_thread(_insert_and_flush)

                logger.info(f"Inserted {content_type} {item} into Milvus. Done.")

                async with self._metadata_lock:
                    self.files_meta[file_id]["status"] = "done"
                    self._save_metadata()
                file_record['status'] = "done"
                # 从处理队列中移除
                self._remove_from_processing_queue(file_id)

            except Exception as e:
                logger.error(f"处理{content_type} {item} 失败: {e}, {traceback.format_exc()}")
                async with self._metadata_lock:
                    self.files_meta[file_id]["status"] = "failed"
                    self._save_metadata()
                file_record['status'] = "failed"
                # 从处理队列中移除
                self._remove_from_processing_queue(file_id)
            finally:
                pass

            processed_items_info.append(file_record)

        return processed_items_info

    async def aquery(self, query_text: str, db_id: str, **kwargs) -> list[dict]:
        """异步查询知识库"""
        collection = await self._get_milvus_collection(db_id)
        if not collection:
            raise ValueError(f"Database {db_id} not found")

        try:
            top_k = kwargs.get("top_k", 30)
            similarity_threshold = kwargs.get("similarity_threshold", 0.2)
            metric_type = kwargs.get("metric_type", "COSINE")

            embed_info = self.databases_meta[db_id].get("embed_info", {})
            embedding_function = self._get_embedding_function(embed_info)
            query_embedding = embedding_function([query_text])

            search_params = {"metric_type": metric_type, "params": {"nprobe": 10}}
            results = collection.search(
                data=query_embedding,
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=["content", "source", "chunk_id", "file_id", "chunk_index"]
            )

            if not results or len(results) == 0 or len(results[0]) == 0:
                return []

            retrieved_chunks = []
            for hit in results[0]:
                similarity = hit.distance if metric_type == "COSINE" else 1 / (1 + hit.distance)

                if similarity < similarity_threshold:
                    continue

                entity = hit.entity
                metadata = {
                    "source": entity.get("source", "未知来源"),
                    "chunk_id": entity.get("chunk_id"),
                    "file_id": entity.get("file_id"),
                    "chunk_index": entity.get("chunk_index")
                }

                retrieved_chunks.append({
                    "content": entity.get("content", ""),
                    "metadata": metadata,
                    "score": similarity
                })

            logger.debug(f"Milvus query response: {len(retrieved_chunks)} chunks found (after similarity filtering)")
            return retrieved_chunks

        except Exception as e:
            logger.error(f"Milvus query error: {e}, {traceback.format_exc()}")
            return []

    async def delete_file(self, db_id: str, file_id: str) -> None:
        """删除文件"""
        collection = await self._get_milvus_collection(db_id)

        if collection:
            # 先查询文件是否存在，避免不必要的删除操作
            try:
                expr = f'file_id == "{file_id}"'
                results = collection.query(
                    expr=expr,
                    output_fields=["id"],
                    limit=1
                )

                if not results:
                    logger.info(f"File {file_id} not found in Milvus, skipping delete operation")
                else:
                    # 只有在文件确实存在时才执行删除
                    def _delete_from_milvus():
                        try:
                            collection.delete(expr)
                            collection.flush()
                            logger.info(f"Deleted chunks for file {file_id} from Milvus")
                        except Exception as e:
                            logger.error(f"Error deleting file {file_id} from Milvus: {e}")

                    await asyncio.to_thread(_delete_from_milvus)
            except Exception as e:
                logger.error(f"Error checking file existence in Milvus: {e}")
        # 使用锁确保元数据操作的原子性
        async with self._metadata_lock:
            if file_id in self.files_meta:
                del self.files_meta[file_id]
                self._save_metadata()

    async def get_file_info(self, db_id: str, file_id: str) -> dict:
        """获取文件信息和chunks"""
        if file_id not in self.files_meta:
            raise Exception(f"File not found: {file_id}")

        # 使用 Milvus 获取chunks
        collection = await self._get_milvus_collection(db_id)
        if collection:
            try:
                # 查询文档的所有chunks
                expr = f'file_id == "{file_id}"'
                results = collection.query(
                    expr=expr,
                    output_fields=["content", "chunk_id", "chunk_index"],
                    limit=10000  # 假设单个文件不会超过10000个chunks
                )

                # 构建chunks数据
                doc_chunks = []
                for result in results:
                    chunk_data = {
                        "id": result.get("chunk_id", ""),
                        "content": result.get("content", ""),
                        "chunk_order_index": result.get("chunk_index", 0)
                    }
                    doc_chunks.append(chunk_data)

                # 按 chunk_order_index 排序
                doc_chunks.sort(key=lambda x: x.get("chunk_order_index", 0))
                return {"lines": doc_chunks}

            except Exception as e:
                logger.error(f"Error getting chunks for file {file_id}: {e}")

        return {"lines": []}

    def delete_database(self, db_id: str) -> dict:
        """删除数据库，同时清除Milvus中的集合"""
        # Drop Milvus collection
        try:
            if utility.has_collection(db_id, using=self.connection_alias):
                utility.drop_collection(db_id, using=self.connection_alias)
                logger.info(f"Dropped Milvus collection for {db_id}")
            else:
                logger.info(f"Milvus collection {db_id} does not exist, skipping")
        except Exception as e:
            logger.error(f"Failed to drop Milvus collection {db_id}: {e}")

        # Call base method to delete local files and metadata
        return super().delete_database(db_id)

    def __del__(self):
        """清理连接"""
        try:
            if hasattr(self, 'connection_alias'):
                connections.disconnect(self.connection_alias)
        except Exception:  # noqa: S110
            pass
