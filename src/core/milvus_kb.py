import os
import time
import traceback
import json
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime

try:
    from pymilvus import (
        connections, utility, Collection, CollectionSchema,
        FieldSchema, DataType, db
    )
    MILVUS_AVAILABLE = True
except ImportError:
    MILVUS_AVAILABLE = False
    connections = None
    utility = None
    Collection = None

from src.core.knowledge_base import KnowledgeBase
from src.utils import logger, hashstr
from src import config


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
        self.collections: Dict[str, Any] = {}

        # 分块配置
        self.chunk_size = kwargs.get('chunk_size', 1000)
        self.chunk_overlap = kwargs.get('chunk_overlap', 200)

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

    async def _create_kb_instance(self, db_id: str, config: Dict) -> Any:
        """创建 Milvus 集合"""
        logger.info(f"Creating Milvus collection for {db_id}")

        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        embed_info = self.databases_meta[db_id].get("embed_info", {})
        collection_name = f"kb_{db_id}"

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

    def _get_embedding_function(self, embed_info: Dict):
        """获取 embedding 函数"""
        if embed_info:
            model = embed_info["name"]
            api_key = os.getenv(embed_info["api_key"], embed_info["api_key"])
            base_url = embed_info["base_url"]
        else:
            from src.models import select_embedding_model
            default_model = select_embedding_model(config.embed_model)
            model = default_model.model
            api_key = default_model.api_key
            base_url = default_model.base_url

        # 返回同步的嵌入函数
        def embedding_function(texts):
            import asyncio
            import concurrent.futures
            from lightrag.llm.openai import openai_embed

            def run_embedding():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(
                        openai_embed(
                            texts=texts,
                            model=model,
                            api_key=api_key,
                            base_url=base_url.replace("/embeddings", ""),
                        )
                    )
                finally:
                    loop.close()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_embedding)
                return future.result()

        return embedding_function

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

    def _split_text_into_chunks(self, text: str, file_id: str, filename: str) -> List[Dict]:
        """将文本分割成块"""
        chunks = []

        # 简单的分块策略：按段落和长度分割
        paragraphs = text.split('\n\n')

        current_chunk = ""
        chunk_index = 0

        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue

            # 如果当前块加上新段落会超过限制，保存当前块
            if len(current_chunk) + len(paragraph) > self.chunk_size and current_chunk:
                chunks.append({
                    "id": f"{file_id}_chunk_{chunk_index}",
                    "content": current_chunk.strip(),
                    "file_id": file_id,
                    "filename": filename,
                    "chunk_index": chunk_index,
                    "source": filename,
                    "chunk_id": f"{file_id}_chunk_{chunk_index}"
                })

                # 开始新块，包含重叠内容
                if len(current_chunk) > self.chunk_overlap:
                    current_chunk = current_chunk[-self.chunk_overlap:] + "\n\n" + paragraph
                else:
                    current_chunk = paragraph
                chunk_index += 1
            else:
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph

        # 添加最后一块
        if current_chunk.strip():
            chunks.append({
                "id": f"{file_id}_chunk_{chunk_index}",
                "content": current_chunk.strip(),
                "file_id": file_id,
                "filename": filename,
                "chunk_index": chunk_index,
                "source": filename,
                "chunk_id": f"{file_id}_chunk_{chunk_index}"
            })

        return chunks

    async def add_content(self, db_id: str, items: List[str],
                         params: Optional[Dict] = None) -> List[Dict]:
        """添加内容（文件/URL）"""
        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        collection = await self._get_milvus_collection(db_id)
        if not collection:
            raise ValueError(f"Failed to get Milvus collection for {db_id}")

        embed_info = self.databases_meta[db_id].get("embed_info", {})
        embedding_function = self._get_embedding_function(embed_info)

        content_type = params.get('content_type', 'file') if params else 'file'
        processed_items_info = []

        for item in items:
            # 根据内容类型生成不同的ID和文件名
            if content_type == "file":
                file_path = Path(item)
                file_id = f"file_{hashstr(str(file_path) + str(time.time()), 6)}"
                file_type = file_path.suffix.lower().replace(".", "")
                filename = file_path.name
                item_path = str(file_path)
            else:  # URL
                file_id = f"url_{hashstr(item + str(time.time()), 6)}"
                file_type = "url"
                filename = f"webpage_{hashstr(item, 6)}.md"
                item_path = item

            # 添加文件记录
            file_record = {
                "database_id": db_id,
                "filename": filename,
                "path": item_path,
                "file_type": file_type,
                "status": "processing",
                "created_at": time.time()
            }
            self.files_meta[file_id] = file_record
            self._save_metadata()

            # 添加 file_id 到返回数据
            file_record = file_record.copy()
            file_record["file_id"] = file_id

            try:
                # 根据内容类型处理内容
                if content_type == "file":
                    markdown_content = await self._process_file_to_markdown(item, params=params)
                else:  # URL
                    markdown_content = await self._process_url_to_markdown(item, params=params)

                # 分割文本成块
                chunks = self._split_text_into_chunks(markdown_content, file_id, filename)
                logger.info(f"Split {filename} into {len(chunks)} chunks")

                # 准备 Milvus 插入的数据
                if chunks:
                    # 生成嵌入向量
                    texts = [chunk["content"] for chunk in chunks]
                    embeddings = embedding_function(texts)

                    # 准备插入数据
                    entities = [
                        [chunk["id"] for chunk in chunks],                    # id
                        [chunk["content"] for chunk in chunks],              # content
                        [chunk["source"] for chunk in chunks],               # source
                        [chunk["chunk_id"] for chunk in chunks],             # chunk_id
                        [chunk["file_id"] for chunk in chunks],              # file_id
                        [chunk["chunk_index"] for chunk in chunks],          # chunk_index
                        embeddings                                            # embedding
                    ]

                    # 插入到 Milvus
                    collection.insert(entities)
                    collection.flush()

                logger.info(f"Inserted {content_type} {item} into Milvus. Done.")

                # 更新状态为完成
                self.files_meta[file_id]["status"] = "done"
                self._save_metadata()
                file_record['status'] = "done"

            except Exception as e:
                logger.error(f"处理{content_type} {item} 失败: {e}, {traceback.format_exc()}")
                self.files_meta[file_id]["status"] = "failed"
                self._save_metadata()
                file_record['status'] = "failed"

            processed_items_info.append(file_record)

        return processed_items_info

    async def aquery(self, query_text: str, db_id: str, **kwargs) -> str:
        """异步查询知识库"""
        collection = await self._get_milvus_collection(db_id)
        if not collection:
            raise ValueError(f"Database {db_id} not found")

        try:
            # 设置查询参数 - Milvus 知识库特有的参数
            top_k = kwargs.get("top_k", 10)
            similarity_threshold = kwargs.get("similarity_threshold", 0.0)  # 相似度阈值
            include_distances = kwargs.get("include_distances", True)  # 是否包含距离信息
            metric_type = kwargs.get("metric_type", "COSINE")  # 距离度量类型

            # 生成查询向量
            embed_info = self.databases_meta[db_id].get("embed_info", {})
            embedding_function = self._get_embedding_function(embed_info)
            query_embedding = embedding_function([query_text])

            # 执行相似性搜索
            search_params = {"metric_type": metric_type, "params": {"nprobe": 10}}
            results = collection.search(
                data=query_embedding,
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=["content", "source", "chunk_id", "file_id", "chunk_index"]
            )

            # 处理结果
            if results and len(results) > 0 and len(results[0]) > 0:
                contexts = []
                for i, hit in enumerate(results[0]):
                    # 计算相似度
                    similarity = 1 - hit.distance if metric_type == "COSINE" else 1 / (1 + hit.distance)

                    # 应用相似度阈值过滤
                    if similarity < similarity_threshold:
                        continue

                    entity = hit.entity
                    content = entity.get("content", "")
                    source = entity.get("source", "未知来源")
                    chunk_id = entity.get("chunk_id", f"chunk_{i}")

                    context = f"[文档片段 {i+1}]:\n{content}\n"
                    context += f"来源: {source} ({chunk_id})\n"
                    if include_distances:
                        context += f"相似度: {similarity:.3f}\n"
                    contexts.append(context)

                response = "\n".join(contexts)
                logger.debug(f"Milvus query response: {len(contexts)} chunks found (after similarity filtering)")
                return response

            return ""

        except Exception as e:
            logger.error(f"Milvus query error: {e}, {traceback.format_exc()}")
            return ""

    async def delete_file(self, db_id: str, file_id: str) -> None:
        """删除文件"""
        collection = await self._get_milvus_collection(db_id)
        if collection:
            try:
                # 删除所有相关chunks
                expr = f'file_id == "{file_id}"'
                collection.delete(expr)
                collection.flush()
                logger.info(f"Deleted chunks for file {file_id} from Milvus")

            except Exception as e:
                logger.error(f"Error deleting file {file_id} from Milvus: {e}")

        # 删除文件记录
        if file_id in self.files_meta:
            del self.files_meta[file_id]
            self._save_metadata()

    async def get_file_info(self, db_id: str, file_id: str) -> Dict:
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

    def __del__(self):
        """清理连接"""
        try:
            if hasattr(self, 'connection_alias'):
                connections.disconnect(self.connection_alias)
        except:
            pass