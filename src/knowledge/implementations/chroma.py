import asyncio
import os
import time
import traceback
from typing import Any

import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from src.knowledge.base import KnowledgeBase
from src.knowledge.indexing import process_file_to_markdown
from src.knowledge.utils.kb_utils import (
    get_embedding_config,
    prepare_item_metadata,
    split_text_into_chunks,
    split_text_into_qa_chunks,
)
from src.utils import logger
from src.utils.datetime_utils import utc_isoformat


class ChromaKB(KnowledgeBase):
    """基于 ChromaDB 的向量库"""

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
            path=self.chroma_db_path, settings=Settings(anonymized_telemetry=False)
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
            collection = self.chroma_client.get_collection(name=collection_name, embedding_function=embedding_function)
            logger.info(f"Retrieved existing collection: {collection_name}")

            # 检查现有集合的配置是否匹配当前的 embed_info
            expected_model = getattr(embed_info, "name", None) if embed_info else None
            if expected_model is None and hasattr(embed_info, "get"):
                expected_model = embed_info.get("name")
            elif embed_info and isinstance(embed_info, dict):
                expected_model = embed_info.get("name")
            expected_model = expected_model or "default"
            collection_metadata = collection.metadata or {}
            current_model = collection_metadata.get("embedding_model", "unknown")

            logger.debug(f"Collection {collection_name} uses model '{current_model}', but expected '{expected_model}'.")
            # 如果模型不匹配，删除现有集合并重新创建
            if current_model != expected_model:
                logger.warning(
                    f"Collection {collection_name} uses model '{current_model}', "
                    f"but expected '{expected_model}'. Recreating collection."
                )
                self.chroma_client.delete_collection(name=collection_name)
                raise Exception("Model mismatch, recreating collection")

        except Exception:
            # 创建新集合
            model_name = getattr(embed_info, "name", None) if embed_info else None
            if model_name is None and hasattr(embed_info, "get"):
                model_name = embed_info.get("name")
            elif embed_info and isinstance(embed_info, dict):
                model_name = embed_info.get("name")

            model_name = model_name or "default"
            logger.info(f"Creating new collection with embedding model: {model_name}")
            collection_metadata = {
                "db_id": db_id,
                "created_at": utc_isoformat(),
                "embedding_model": model_name,
            }
            collection = self.chroma_client.create_collection(
                name=collection_name, embedding_function=embedding_function, metadata=collection_metadata
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
            api_base=config_dict["base_url"].replace("/embeddings", ""),
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
        use_qa_split = params.get("use_qa_split", False)

        if use_qa_split:
            # 使用QA分割模式
            qa_separator = params.get("qa_separator", "\n\n\n")
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
                "chunk_type": chunk.get("chunk_type", "normal"),  # 添加chunk类型标识
            }

        return chunks

    async def add_content(self, db_id: str, items: list[str], params: dict | None = None) -> list[dict]:
        """添加内容（文件/URL）"""
        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        collection = await self._get_chroma_collection(db_id)
        if not collection:
            raise ValueError(f"Failed to get ChromaDB collection for {db_id}")

        content_type = params.get("content_type", "file") if params else "file"
        processed_items_info = []

        for item in items:
            # 准备文件元数据
            metadata = await prepare_item_metadata(item, content_type, db_id, params=params)
            file_id = metadata["file_id"]
            filename = metadata["filename"]

            # 添加文件记录
            file_record = metadata.copy()
            self.files_meta[file_id] = file_record
            self._save_metadata()

            self._add_to_processing_queue(file_id)
            try:
                # 确保params中包含db_id（ZIP文件处理需要）
                if params is None:
                    params = {}
                params["db_id"] = db_id

                # 根据内容类型处理内容
                if content_type != "file":
                    raise ValueError("URL 内容解析已禁用")
                markdown_content = await process_file_to_markdown(item, params=params)

                # 分割文本成块
                chunks = self._split_text_into_chunks(markdown_content, file_id, filename, params)
                logger.info(f"Split {filename} into {len(chunks)} chunks")

                # 准备向量数据库插入的数据
                if chunks:
                    documents = [chunk["content"] for chunk in chunks]
                    metadatas = [chunk["metadata"] for chunk in chunks]
                    ids = [chunk["id"] for chunk in chunks]

                    # 插入到 ChromaDB - 分批处理以避免超出 OpenAI 批次大小限制
                    batch_size = 64  # OpenAI 的最大批次大小限制
                    total_batches = (len(chunks) + batch_size - 1) // batch_size

                    for i in range(0, len(chunks), batch_size):
                        batch_documents = documents[i : i + batch_size]
                        batch_metadatas = metadatas[i : i + batch_size]
                        batch_ids = ids[i : i + batch_size]

                        await asyncio.to_thread(
                            collection.add,
                            documents=batch_documents,
                            metadatas=batch_metadatas,
                            ids=batch_ids,
                        )

                        batch_num = i // batch_size + 1
                        logger.info(f"Processed batch {batch_num}/{total_batches} for {filename}")

                logger.info(f"Inserted {content_type} {item} into ChromaDB. Done.")

                # 更新状态为完成
                self.files_meta[file_id]["status"] = "done"
                self._save_metadata()
                file_record["status"] = "done"

            except Exception as e:
                logger.error(f"处理{content_type} {item} 失败: {e}, {traceback.format_exc()}")
                self.files_meta[file_id]["status"] = "failed"
                self._save_metadata()
                file_record["status"] = "failed"
            finally:
                self._remove_from_processing_queue(file_id)

            processed_items_info.append(file_record)

        return processed_items_info

    async def update_content(self, db_id: str, file_ids: list[str], params: dict | None = None) -> list[dict]:
        """更新内容 - 根据file_ids重新解析文件并更新向量库"""
        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        collection = await self._get_chroma_collection(db_id)
        if not collection:
            raise ValueError(f"Failed to get ChromaDB collection for {db_id}")

        # 处理默认参数
        if params is None:
            params = {}
        content_type = params.get("content_type", "file")
        processed_items_info = []

        for file_id in file_ids:
            # 从元数据中获取文件信息
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
                self.files_meta[file_id]["processing_params"] = params.copy()
                self.files_meta[file_id]["status"] = "processing"
                self._save_metadata()

                # 重新解析文件为 markdown
                if content_type != "file":
                    raise ValueError("URL 内容解析已禁用")
                markdown_content = await process_file_to_markdown(file_path, params=params)

                # 先删除现有的 ChromaDB 数据（仅删除chunks，保留元数据）
                await self.delete_file_chunks_only(db_id, file_id)

                # 重新生成 chunks
                chunks = self._split_text_into_chunks(markdown_content, file_id, filename, params)
                logger.info(f"Split {filename} into {len(chunks)} chunks")

                if chunks:
                    documents = [chunk["content"] for chunk in chunks]
                    metadatas = [chunk["metadata"] for chunk in chunks]
                    ids = [chunk["id"] for chunk in chunks]

                    # 插入到 ChromaDB - 分批处理以避免超出 OpenAI 批次大小限制
                    batch_size = 64  # OpenAI 的最大批次大小限制
                    total_batches = (len(chunks) + batch_size - 1) // batch_size

                    for i in range(0, len(chunks), batch_size):
                        batch_documents = documents[i : i + batch_size]
                        batch_metadatas = metadatas[i : i + batch_size]
                        batch_ids = ids[i : i + batch_size]

                        await asyncio.to_thread(
                            collection.add,
                            documents=batch_documents,
                            metadatas=batch_metadatas,
                            ids=batch_ids,
                        )

                        batch_num = i // batch_size + 1
                        logger.info(f"Processed batch {batch_num}/{total_batches} for {filename}")

                logger.info(f"Updated {content_type} {file_path} in ChromaDB. Done.")

                # 更新元数据状态
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
        collection = await self._get_chroma_collection(db_id)
        if not collection:
            raise ValueError(f"Database {db_id} not found")

        try:
            db_meta = self.databases_meta.get(db_id, {})
            db_metadata = db_meta.get("metadata", {}) or {}
            reranker_config = db_metadata.get("reranker_config", {}) or {}

            requested_top_k = int(kwargs.get("top_k", reranker_config.get("final_top_k", 10)))
            requested_top_k = max(requested_top_k, 1)

            similarity_threshold = float(kwargs.get("similarity_threshold", 0.0))
            include_distances = bool(kwargs.get("include_distances", True))

            use_reranker = bool(kwargs.get("use_reranker", reranker_config.get("enabled", False)))

            if use_reranker:
                recall_top_k = int(kwargs.get("recall_top_k", reranker_config.get("recall_top_k", 50)))
                recall_top_k = max(recall_top_k, requested_top_k)
                final_top_k = requested_top_k
            else:
                recall_top_k = requested_top_k
                final_top_k = requested_top_k

            results = collection.query(
                query_texts=[query_text],
                n_results=recall_top_k,
                include=["documents", "metadatas", "distances"],
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
                if "full_doc_id" in metadata:
                    metadata["file_id"] = metadata.pop("full_doc_id")

                chunk = {"content": doc, "metadata": metadata, "score": similarity}
                if include_distances and i < len(distances):
                    chunk["distance"] = distances[i]
                retrieved_chunks.append(chunk)

            logger.debug(f"ChromaDB query response: {len(retrieved_chunks)} chunks found (after similarity filtering)")

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
            logger.error(f"ChromaDB query error: {e}, {traceback.format_exc()}")
            return []

    async def delete_file_chunks_only(self, db_id: str, file_id: str) -> None:
        """仅删除文件的chunks数据，保留元数据（用于更新操作）"""
        collection = await self._get_chroma_collection(db_id)
        if collection:
            try:
                # 查找所有相关的chunks
                results = collection.get(where={"full_doc_id": file_id}, include=["metadatas"])

                # 删除所有相关chunks
                if results and results.get("ids"):
                    collection.delete(ids=results["ids"])
                    logger.info(f"Deleted {len(results['ids'])} chunks for file {file_id}")

            except Exception as e:
                logger.error(f"Error deleting file {file_id} from ChromaDB: {e}")
        # 注意：这里不删除 files_meta[file_id]，保留元数据用于后续操作

    async def delete_file(self, db_id: str, file_id: str) -> None:
        """删除文件（包括元数据）"""
        # 先删除 ChromaDB 中的 chunks 数据
        await self.delete_file_chunks_only(db_id, file_id)

        # 删除文件记录
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

        # 使用 ChromaDB 获取chunks
        content_info = {"lines": []}
        collection = await self._get_chroma_collection(db_id)
        if collection:
            try:
                # 获取文档的所有chunks
                results = collection.get(where={"full_doc_id": file_id}, include=["documents", "metadatas"])

                # 构建chunks数据
                doc_chunks = []
                if results and results.get("ids"):
                    for i, chunk_id in enumerate(results["ids"]):
                        chunk_data = {
                            "id": chunk_id,
                            "content": results["documents"][i] if i < len(results["documents"]) else "",
                            "metadata": results["metadatas"][i] if i < len(results["metadatas"]) else {},
                            "chunk_order_index": results["metadatas"][i].get("chunk_index", i)
                            if i < len(results["metadatas"])
                            else i,
                        }
                        doc_chunks.append(chunk_data)

                # 按 chunk_order_index 排序
                doc_chunks.sort(key=lambda x: x.get("chunk_order_index", 0))
                content_info["lines"] = doc_chunks
                return content_info

            except Exception as e:
                logger.error(f"Failed to get file content from ChromaDB: {e}")
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
