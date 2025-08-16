import os
import time
import traceback
import json
from pathlib import Path
from typing import Optional, Any
from datetime import datetime

import chromadb
from chromadb.config import Settings
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from src.knowledge.indexing import process_url_to_markdown, process_file_to_markdown
from src.knowledge.knowledge_base import KnowledgeBase
from src.knowledge.kb_utils import split_text_into_chunks, split_text_into_qa_chunks, prepare_item_metadata, get_embedding_config
from src.utils import logger, hashstr
from src import config


class ChromaKB(KnowledgeBase):
    """基于 ChromaDB 的向量知识库实现"""

    def __init__(self, work_dir: str, **kwargs):
        """
        初始化 ChromaDB 知识库

        Args:
            work_dir: 工作目录
            **kwargs: 其他配置参数
        """
        super().__init__(work_dir)

        if chromadb is None:
            raise ImportError("chromadb is not installed. Please install it with: pip install chromadb")

        # ChromaDB 配置
        self.chroma_db_path = os.path.join(work_dir, "chromadb")
        os.makedirs(self.chroma_db_path, exist_ok=True)

        # 初始化 ChromaDB 客户端
        self.chroma_client = chromadb.PersistentClient(
            path=self.chroma_db_path,
            settings=Settings(anonymized_telemetry=False)
        )

        # 存储集合映射 {db_id: collection}
        self.collections: dict[str, Any] = {}
        logger.info("ChromaKB initialized")

    @property
    def kb_type(self) -> str:
        """知识库类型标识"""
        return "chroma"

    async def _create_kb_instance(self, db_id: str, kb_config: dict) -> Any:
        """创建向量数据库集合"""
        logger.info(f"Creating ChromaDB collection for {db_id}")

        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        embed_info = self.databases_meta[db_id].get("embed_info", {})
        embedding_function = self._get_embedding_function(embed_info)

        # 创建或获取集合
        collection_name = db_id

        try:
            # 尝试获取现有集合
            collection = self.chroma_client.get_collection(
                name=collection_name,
                embedding_function=embedding_function
            )
            logger.info(f"Retrieved existing collection: {collection_name}")

            # 检查现有集合的配置是否匹配当前的 embed_info
            expected_model = embed_info.get("name") if embed_info else "default"
            collection_metadata = collection.metadata or {}
            current_model = collection_metadata.get("embedding_model", "unknown")

            logger.debug(f"Collection {collection_name} uses model '{current_model}', but expected '{expected_model}'.")
            # 如果模型不匹配，删除现有集合并重新创建
            if current_model != expected_model:
                logger.warning(f"Collection {collection_name} uses model '{current_model}', but expected '{expected_model}'. Recreating collection.")
                self.chroma_client.delete_collection(name=collection_name)
                raise Exception("Model mismatch, recreating collection")

        except Exception:
            # 创建新集合
            logger.info(f"Creating new collection with embedding model: {embed_info.get('name', 'default')}")
            collection_metadata = {
                "db_id": db_id,
                "created_at": datetime.now().isoformat(),
                "embedding_model": embed_info.get("name") if embed_info else "default"
            }
            collection = self.chroma_client.create_collection(
                name=collection_name,
                embedding_function=embedding_function,
                metadata=collection_metadata
            )
            logger.info(f"Created new collection: {collection_name}")

        return collection

    async def _initialize_kb_instance(self, instance: Any) -> None:
        """初始化向量数据库集合（无需特殊初始化）"""
        pass

    def _get_embedding_function(self, embed_info: dict):
        """获取 embedding 函数"""
        config_dict = get_embedding_config(embed_info)

        return OpenAIEmbeddingFunction(
            model_name=config_dict["model"],
            api_key=config_dict["api_key"],
            api_base=config_dict["base_url"].replace('/embeddings', '')
        )

    async def _get_chroma_collection(self, db_id: str):
        """获取或创建 ChromaDB 集合"""
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
            logger.error(f"Failed to create vector collection for {db_id}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def _split_text_into_chunks(self, text: str, file_id: str, filename: str, params: dict) -> list[dict]:
        """将文本分割成块"""
        # 检查是否使用QA分割模式
        use_qa_split = params.get('use_qa_split', False)

        if use_qa_split:
            # 使用QA分割模式
            qa_separator = params.get('qa_separator', '\n\n\n')
            chunks = split_text_into_qa_chunks(text, file_id, filename, qa_separator, params)
        else:
            # 使用传统分割模式
            chunks = split_text_into_chunks(text, file_id, filename, params)

        # 为 ChromaDB 添加特定的 metadata 格式
        for chunk in chunks:
            chunk["metadata"] = {
                "source": chunk["source"],
                "chunk_id": chunk["chunk_id"],
                "full_doc_id": file_id,
                "chunk_type": chunk.get("chunk_type", "normal")  # 添加chunk类型标识
            }

        return chunks

    async def add_content(self, db_id: str, items: list[str],
                         params:dict | None) -> list[dict]:
        """添加内容（文件/URL）"""
        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        collection = await self._get_chroma_collection(db_id)
        if not collection:
            raise ValueError(f"Failed to get ChromaDB collection for {db_id}")

        content_type = params.get('content_type', 'file') if params else 'file'
        processed_items_info = []

        for item in items:
            # 准备文件元数据
            metadata = prepare_item_metadata(item, content_type, db_id)
            file_id = metadata["file_id"]
            filename = metadata["filename"]

            # 添加文件记录
            file_record = metadata.copy()
            self.files_meta[file_id] = file_record
            self._save_metadata()

            self._add_to_processing_queue(file_id)
            try:
                # 根据内容类型处理内容
                if content_type == "file":
                    markdown_content = await process_file_to_markdown(item, params=params)
                else:  # URL
                    markdown_content = await process_url_to_markdown(item, params=params)

                # 分割文本成块
                chunks = self._split_text_into_chunks(markdown_content, file_id, filename, params)
                logger.info(f"Split {filename} into {len(chunks)} chunks")

                # 准备向量数据库插入的数据
                if chunks:
                    documents = [chunk["content"] for chunk in chunks]
                    metadatas = [chunk["metadata"] for chunk in chunks]
                    ids = [chunk["id"] for chunk in chunks]

                    # 插入到 ChromaDB
                    collection.add(
                        documents=documents,
                        metadatas=metadatas,
                        ids=ids
                    )

                logger.info(f"Inserted {content_type} {item} into ChromaDB. Done.")

                # 更新状态为完成
                self.files_meta[file_id]["status"] = "done"
                self._save_metadata()
                file_record['status'] = "done"

            except Exception as e:
                logger.error(f"处理{content_type} {item} 失败: {e}, {traceback.format_exc()}")
                self.files_meta[file_id]["status"] = "failed"
                self._save_metadata()
                file_record['status'] = "failed"
            finally:
                self._remove_from_processing_queue(file_id)

            processed_items_info.append(file_record)

        return processed_items_info

    async def aquery(self, query_text: str, db_id: str, **kwargs) -> list[dict]:
        """异步查询知识库"""
        collection = await self._get_chroma_collection(db_id)
        if not collection:
            raise ValueError(f"Database {db_id} not found")

        try:
            top_k = kwargs.get("top_k", 10)
            similarity_threshold = kwargs.get("similarity_threshold", 0.0)

            results = collection.query(
                query_texts=[query_text],
                n_results=top_k,
                include=["documents", "metadatas", "distances"]
            )

            if not results or not results.get("documents") or not results["documents"][0]:
                return []

            documents = results["documents"][0]
            metadatas = results["metadatas"][0] if results.get("metadatas") else []
            distances = results["distances"][0] if results.get("distances") else []

            retrieved_chunks = []
            for i, doc in enumerate(documents):
                similarity = 1 - distances[i] if i < len(distances) else 1.0

                if similarity < similarity_threshold:
                    continue

                metadata = metadatas[i] if i < len(metadatas) else {}
                # 确保 file_id 在元数据中，并使用统一的键名
                if 'full_doc_id' in metadata:
                    metadata['file_id'] = metadata.pop('full_doc_id')

                retrieved_chunks.append({
                    "content": doc,
                    "metadata": metadata,
                    "score": similarity
                })

            logger.debug(f"ChromaDB query response: {len(retrieved_chunks)} chunks found (after similarity filtering)")
            return retrieved_chunks

        except Exception as e:
            logger.error(f"ChromaDB query error: {e}, {traceback.format_exc()}")
            return []

    async def delete_file(self, db_id: str, file_id: str) -> None:
        """删除文件"""
        collection = await self._get_chroma_collection(db_id)
        if collection:
            try:
                # 查找所有相关的chunks
                results = collection.get(
                    where={"full_doc_id": file_id},
                    include=["metadatas"]
                )

                # 删除所有相关chunks
                if results and results.get("ids"):
                    collection.delete(ids=results["ids"])
                    logger.info(f"Deleted {len(results['ids'])} chunks for file {file_id}")

            except Exception as e:
                logger.error(f"Error deleting file {file_id} from ChromaDB: {e}")

        # 删除文件记录
        if file_id in self.files_meta:
            del self.files_meta[file_id]
            self._save_metadata()

    async def get_file_info(self, db_id: str, file_id: str) -> dict:
        """获取文件信息和chunks"""
        if file_id not in self.files_meta:
            raise Exception(f"File not found: {file_id}")

        # 使用 ChromaDB 获取chunks
        collection = await self._get_chroma_collection(db_id)
        if collection:
            try:
                # 获取文档的所有chunks
                results = collection.get(
                    where={"full_doc_id": file_id},
                    include=["documents", "metadatas"]
                )

                # 构建chunks数据
                doc_chunks = []
                if results and results.get("ids"):
                    for i, chunk_id in enumerate(results["ids"]):
                        chunk_data = {
                            "id": chunk_id,
                            "content": results["documents"][i] if i < len(results["documents"]) else "",
                            "metadata": results["metadatas"][i] if i < len(results["metadatas"]) else {},
                            "chunk_order_index": results["metadatas"][i].get("chunk_index", i) if i < len(results["metadatas"]) else i
                        }
                        doc_chunks.append(chunk_data)

                # 按 chunk_order_index 排序
                doc_chunks.sort(key=lambda x: x.get("chunk_order_index", 0))
                return {"lines": doc_chunks}

            except Exception as e:
                logger.error(f"Error getting chunks for file {file_id}: {e}")

        return {"lines": []}
