import asyncio
import os
import time
import traceback
from functools import partial
from typing import Any

from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, db, utility

from src import config
from src.knowledge.base import KnowledgeBase
from src.knowledge.indexing import process_file_to_markdown
from src.knowledge.utils.kb_utils import (
    get_embedding_config,
    prepare_item_metadata,
    split_text_into_chunks,
    split_text_into_qa_chunks,
)
from src.models.embed import OtherEmbedding
from src.utils import hashstr, logger

MILVUS_AVAILABLE = True


class MilvusKB(KnowledgeBase):
    """基于 Milvus 的生产级向量库"""

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
        self.milvus_token = kwargs.get("milvus_token", os.getenv("MILVUS_TOKEN") or "")
        self.milvus_uri = kwargs.get("milvus_uri", os.getenv("MILVUS_URI") or "http://localhost:19530")
        self.milvus_db = kwargs.get("milvus_db") or "yuxi_know"

        # 连接名称
        self.connection_alias = f"milvus_{hashstr(work_dir, 6)}"

        # 存储集合映射 {db_id: Collection}
        self.collections: dict[str, Any] = {}

        # 分块配置
        self.chunk_size = kwargs.get("chunk_size", 1000)
        self.chunk_overlap = kwargs.get("chunk_overlap", 200)

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
            connections.connect(alias=self.connection_alias, uri=self.milvus_uri, token=self.milvus_token)

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

        if not (metadata := self.databases_meta.get(db_id)):
            raise ValueError(f"Database {db_id} not found")

        # embed_info = metadata.get("embed_info", {})
        if not (embed_info := metadata.get("embed_info")):
            logger.error(f"Embedding info not found for database {db_id}, using default model")
            embed_info = config.embed_model_names[config.embed_model]

        collection_name = db_id

        try:
            # 检查集合是否存在
            if utility.has_collection(collection_name, using=self.connection_alias):
                collection = Collection(name=collection_name, using=self.connection_alias)

                # 检查嵌入模型是否匹配
                description = collection.description
                expected_model = getattr(embed_info, "name", "default") if embed_info else "default"

                if expected_model not in description:
                    logger.warning(f"Collection {collection_name} model mismatch, recreating...")
                    utility.drop_collection(collection_name, using=self.connection_alias)
                    raise Exception("Model mismatch, recreating collection")

                logger.info(f"Retrieved existing collection: {collection_name}")
            else:
                raise Exception("Collection not found, creating new one")

        except Exception:
            # 创建新集合
            embedding_dim = embed_info.get("dimension", 1024)
            model_name = embed_info.get("name", "default")

            # 定义集合Schema
            fields = [
                FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=100, is_primary=True),
                FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=500),
                FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=100),
                FieldSchema(name="file_id", dtype=DataType.VARCHAR, max_length=100),
                FieldSchema(name="chunk_index", dtype=DataType.INT64),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=embedding_dim),
            ]

            schema = CollectionSchema(
                fields=fields, description=f"Knowledge base collection for {db_id} using {model_name}"
            )

            # 创建集合
            collection = Collection(name=collection_name, schema=schema, using=self.connection_alias)

            # 创建索引
            index_params = {"metric_type": "COSINE", "index_type": "IVF_FLAT", "params": {"nlist": 1024}}
            collection.create_index("embedding", index_params)

            logger.info(f"Created new Milvus collection: {collection_name}: {model_name=}, {embedding_dim=}")

        return collection

    async def _initialize_kb_instance(self, instance: Any) -> None:
        """初始化 Milvus 集合（加载到内存）"""
        try:
            instance.load()
            logger.info("Milvus collection loaded into memory")
        except Exception as e:
            logger.warning(f"Failed to load collection into memory: {e}")

    def _get_async_embedding(self, embed_info: dict):
        """获取 embedding 函数"""
        # 检查是否有 model_id 字段，优先使用 select_embedding_model
        if embed_info and "model_id" in embed_info:
            from src.models.embed import select_embedding_model

            return select_embedding_model(embed_info["model_id"])

        # 使用原有的逻辑（兼容模式））
        config_dict = get_embedding_config(embed_info)
        return OtherEmbedding(
            model=config_dict.get("model"),
            base_url=config_dict.get("base_url"),
            api_key=config_dict.get("api_key"),
        )

    def _get_async_embedding_function(self, embed_info: dict):
        """获取 embedding 函数"""
        embedding_model = self._get_async_embedding(embed_info)
        return partial(embedding_model.abatch_encode, batch_size=40)

    def _get_embedding_function(self, embed_info: dict):
        """获取 embedding 函数"""
        embedding_model = self._get_async_embedding(embed_info)

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
        use_qa_split = params.get("use_qa_split", False)

        if use_qa_split:
            # 使用QA分割模式
            qa_separator = params.get("qa_separator", "\n\n\n")
            return split_text_into_qa_chunks(text, file_id, filename, qa_separator, params)
        else:
            # 使用传统分割模式
            return split_text_into_chunks(text, file_id, filename, params)

    async def add_content(self, db_id: str, items: list[str], params: dict | None = {}) -> list[dict]:
        """添加内容（文件/URL）"""
        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        collection = await self._get_milvus_collection(db_id)
        if not collection:
            raise ValueError(f"Failed to get Milvus collection for {db_id}")

        embed_info = self.databases_meta[db_id].get("embed_info", {})
        embedding_function = self._get_async_embedding_function(embed_info)

        content_type = params.get("content_type", "file") if params else "file"
        processed_items_info = []

        for item in items:
            metadata = await prepare_item_metadata(item, content_type, db_id, params=params)
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
                # 确保params中包含db_id（ZIP文件处理需要）
                if params is None:
                    params = {}
                params["db_id"] = db_id

                if content_type != "file":
                    raise ValueError("URL 内容解析已禁用")
                markdown_content = await process_file_to_markdown(item, params=params)

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
                        embeddings,
                    ]

                    def _insert_records():
                        collection.insert(entities)

                    await asyncio.to_thread(_insert_records)

                logger.info(f"Inserted {content_type} {item} into Milvus. Done.")

                async with self._metadata_lock:
                    self.files_meta[file_id]["status"] = "done"
                    self._save_metadata()
                file_record["status"] = "done"
                # 从处理队列中移除
                self._remove_from_processing_queue(file_id)

            except Exception as e:
                logger.error(f"处理{content_type} {item} 失败: {e}, {traceback.format_exc()}")
                async with self._metadata_lock:
                    self.files_meta[file_id]["status"] = "failed"
                    self._save_metadata()
                file_record["status"] = "failed"
                # 从处理队列中移除
                self._remove_from_processing_queue(file_id)
            finally:
                pass

            processed_items_info.append(file_record)

        return processed_items_info

    async def update_content(self, db_id: str, file_ids: list[str], params: dict | None = None) -> list[dict]:
        """更新内容 - 根据file_ids重新解析文件并更新向量库"""
        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        collection = await self._get_milvus_collection(db_id)
        if not collection:
            raise ValueError(f"Failed to get Milvus collection for {db_id}")

        embed_info = self.databases_meta[db_id].get("embed_info", {})
        embedding_function = self._get_async_embedding_function(embed_info)

        # 处理默认参数
        if params is None:
            params = {}
        content_type = params.get("content_type", "file")
        processed_items_info = []

        for file_id in file_ids:
            # 从元数据中获取文件信息
            async with self._metadata_lock:
                if file_id not in self.files_meta:
                    logger.warning(f"File {file_id} not found in metadata, skipping")
                    continue

                file_meta = self.files_meta[file_id]
                file_path = file_meta.get("path")
                filename = file_meta.get("filename")

                if not file_path:
                    logger.warning(f"File path not found for {file_id}, skipping")
                    continue

            # 添加到处理队列
            self._add_to_processing_queue(file_id)

            try:
                # 更新状态为处理中
                async with self._metadata_lock:
                    self.files_meta[file_id]["processing_params"] = params.copy()
                    self.files_meta[file_id]["status"] = "processing"
                    self._save_metadata()

                # 重新解析文件为 markdown
                if content_type != "file":
                    raise ValueError("URL 内容解析已禁用")
                markdown_content = await process_file_to_markdown(file_path, params=params)

                # 先删除现有的 Milvus 数据（仅删除chunks，保留元数据）
                await self.delete_file_chunks_only(db_id, file_id)

                # 重新生成 chunks
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
                        embeddings,
                    ]

                    def _insert_records():
                        collection.insert(entities)

                    await asyncio.to_thread(_insert_records)

                logger.info(f"Updated {content_type} {file_path} in Milvus. Done.")

                # 更新元数据状态
                async with self._metadata_lock:
                    self.files_meta[file_id]["status"] = "done"
                    self._save_metadata()

                # 从处理队列中移除
                self._remove_from_processing_queue(file_id)

                # 返回更新后的文件信息
                updated_file_meta = file_meta.copy()
                updated_file_meta["status"] = "done"
                updated_file_meta["file_id"] = file_id
                processed_items_info.append(updated_file_meta)

            except Exception as e:
                logger.error(f"更新{content_type} {file_path} 失败: {e}, {traceback.format_exc()}")
                async with self._metadata_lock:
                    self.files_meta[file_id]["status"] = "failed"
                    self._save_metadata()

                # 从处理队列中移除
                self._remove_from_processing_queue(file_id)

                # 返回失败的文件信息
                failed_file_meta = file_meta.copy()
                failed_file_meta["status"] = "failed"
                failed_file_meta["file_id"] = file_id
                processed_items_info.append(failed_file_meta)

        return processed_items_info

    async def aquery(self, query_text: str, db_id: str, **kwargs) -> list[dict]:
        """异步查询知识库"""
        collection = await self._get_milvus_collection(db_id)
        if not collection:
            raise ValueError(f"Database {db_id} not found")

        try:
            db_meta = self.databases_meta.get(db_id, {})
            db_metadata = db_meta.get("metadata", {}) or {}
            reranker_config = db_metadata.get("reranker_config", {}) or {}

            requested_top_k = int(kwargs.get("top_k", reranker_config.get("final_top_k", 30)))
            requested_top_k = max(requested_top_k, 1)
            similarity_threshold = float(kwargs.get("similarity_threshold", 0.2))
            metric_type = kwargs.get("metric_type", "COSINE")
            include_distances = bool(kwargs.get("include_distances", True))

            use_reranker = bool(kwargs.get("use_reranker", reranker_config.get("enabled", False)))
            if use_reranker:
                recall_top_k = int(kwargs.get("recall_top_k", reranker_config.get("recall_top_k", 50)))
                recall_top_k = max(recall_top_k, requested_top_k)
                final_top_k = requested_top_k
            else:
                recall_top_k = requested_top_k
                final_top_k = requested_top_k

            embed_info = self.databases_meta[db_id].get("embed_info", {})
            embedding_function = self._get_embedding_function(embed_info)
            query_embedding = embedding_function([query_text])

            search_params = {"metric_type": metric_type, "params": {"nprobe": 10}}
            results = collection.search(
                data=query_embedding,
                anns_field="embedding",
                param=search_params,
                limit=recall_top_k,
                output_fields=["content", "source", "chunk_id", "file_id", "chunk_index"],
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
                    "chunk_index": entity.get("chunk_index"),
                }

                chunk = {"content": entity.get("content", ""), "metadata": metadata, "score": similarity}
                if include_distances:
                    chunk["distance"] = hit.distance
                retrieved_chunks.append(chunk)

            logger.debug(f"Milvus query response: {len(retrieved_chunks)} chunks found (after similarity filtering)")

            if use_reranker and retrieved_chunks:
                try:
                    reranker_model = kwargs.get("reranker_model", reranker_config.get("model"))
                    if not reranker_model:
                        logger.warning("Reranker enabled but no model specified, skipping reranking")
                    else:
                        from src.models.rerank import get_reranker

                        reranker = get_reranker(reranker_model)
                        try:
                            rerank_start = time.time()
                            documents_text = [chunk["content"] for chunk in retrieved_chunks]
                            rerank_scores = await reranker.acompute_score([query_text, documents_text], normalize=True)

                            for chunk, rerank_score in zip(retrieved_chunks, rerank_scores):
                                chunk["rerank_score"] = float(rerank_score)

                            retrieved_chunks.sort(
                                key=lambda item: item.get("rerank_score", item.get("score", 0.0)), reverse=True
                            )
                            elapsed = time.time() - rerank_start
                            logger.info(
                                f"Reranking completed for {db_id} in {elapsed:.3f}s with model {reranker_model}"
                            )
                        finally:
                            await reranker.aclose()
                except Exception as exc:  # noqa: BLE001
                    logger.error(f"Reranking failed: {exc}, falling back to vector scores")

            return retrieved_chunks[:final_top_k]

        except Exception as e:
            logger.error(f"Milvus query error: {e}, {traceback.format_exc()}")
            return []

    async def delete_file_chunks_only(self, db_id: str, file_id: str) -> None:
        """仅删除文件的chunks数据，保留元数据（用于更新操作）"""
        collection = await self._get_milvus_collection(db_id)

        if collection:
            # 先查询文件是否存在，避免不必要的删除操作
            try:
                expr = f'file_id == "{file_id}"'
                results = collection.query(expr=expr, output_fields=["id"], limit=1)

                if not results:
                    logger.info(f"File {file_id} not found in Milvus, skipping delete operation")
                else:
                    # 只有在文件确实存在时才执行删除
                    def _delete_from_milvus():
                        try:
                            collection.delete(expr)
                            logger.info(f"Deleted chunks for file {file_id} from Milvus")
                        except Exception as e:
                            logger.error(f"Error deleting file {file_id} from Milvus: {e}")

                    await asyncio.to_thread(_delete_from_milvus)
            except Exception as e:
                logger.error(f"Error checking file existence in Milvus: {e}")
        # 注意：这里不删除 files_meta[file_id]，保留元数据用于后续操作

    async def delete_file(self, db_id: str, file_id: str) -> None:
        """删除文件（包括元数据）"""
        # 先删除 Milvus 中的 chunks 数据
        await self.delete_file_chunks_only(db_id, file_id)

        # 使用锁确保元数据操作的原子性
        async with self._metadata_lock:
            if file_id in self.files_meta:
                del self.files_meta[file_id]
                self._save_metadata()

    async def get_file_basic_info(self, db_id: str, file_id: str) -> dict:
        """获取文件基本信息（仅元数据）"""
        if file_id not in self.files_meta:
            raise Exception(f"File not found: {file_id}")

        return {"meta": self.files_meta[file_id]}

    async def get_file_content(self, db_id: str, file_id: str) -> dict:
        """获取文件内容信息（chunks和lines）"""
        if file_id not in self.files_meta:
            raise Exception(f"File not found: {file_id}")

        # 使用 Milvus 获取chunks
        content_info = {"lines": []}
        collection = await self._get_milvus_collection(db_id)
        if collection:
            try:
                # 查询文档的所有chunks
                expr = f'file_id == "{file_id}"'
                results = collection.query(
                    expr=expr,
                    output_fields=["content", "chunk_id", "chunk_index"],
                    limit=10000,  # 假设单个文件不会超过10000个chunks
                )

                # 构建chunks数据
                doc_chunks = []
                for result in results:
                    chunk_data = {
                        "id": result.get("chunk_id", ""),
                        "content": result.get("content", ""),
                        "chunk_order_index": result.get("chunk_index", 0),
                    }
                    doc_chunks.append(chunk_data)

                # 按 chunk_order_index 排序
                doc_chunks.sort(key=lambda x: x.get("chunk_order_index", 0))
                content_info["lines"] = doc_chunks
                return content_info

            except Exception as e:
                logger.error(f"Failed to get file content from Milvus: {e}")
                content_info["lines"] = []
                return content_info

        return content_info

    async def get_file_info(self, db_id: str, file_id: str) -> dict:
        """获取文件完整信息（基本信息+内容信息）- 保持向后兼容"""
        if file_id not in self.files_meta:
            raise Exception(f"File not found: {file_id}")

        # 合并基本信息和内容信息
        basic_info = await self.get_file_basic_info(db_id, file_id)
        content_info = await self.get_file_content(db_id, file_id)

        return {**basic_info, **content_info}

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
            if hasattr(self, "connection_alias"):
                connections.disconnect(self.connection_alias)
        except Exception:  # noqa: S110
            pass
