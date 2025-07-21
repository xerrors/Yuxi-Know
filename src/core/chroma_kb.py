import os
import time
import traceback
import json
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime

try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
except ImportError:
    chromadb = None
    EmbeddingFunction = None
    Documents = None
    Embeddings = None

from src.core.knowledge_base import KnowledgeBase
from src.utils import logger, hashstr
from src import config


if EmbeddingFunction is not None:
    class OpenAIEmbeddingFunction(EmbeddingFunction):
        """
        符合 ChromaDB 0.4.16+ 接口的 OpenAI 兼容嵌入函数
        """

        def __init__(self, model: str, api_key: str, base_url: str):
            self.model = model
            self.api_key = api_key
            self.base_url = base_url.replace("/embeddings", "")

        def __call__(self, input: Documents) -> Embeddings:
            """
            生成文档嵌入向量

            Args:
                input: 文档列表（字符串列表）

            Returns:
                Embeddings: 嵌入向量列表
            """
            import asyncio
            import concurrent.futures
            from lightrag.llm.openai import openai_embed

            # 确保输入是列表格式
            if isinstance(input, str):
                texts = [input]
            else:
                texts = list(input)

            # 在新线程中运行异步函数，避免事件循环冲突
            def run_embedding():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(
                        openai_embed(
                            texts=texts,
                            model=self.model,
                            api_key=self.api_key,
                            base_url=self.base_url,
                        )
                    )
                finally:
                    loop.close()

            # 使用线程池执行异步函数
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_embedding)
                embeddings = future.result()

            return embeddings
else:
    # 如果 ChromaDB 没有安装，提供一个空的类
    class OpenAIEmbeddingFunction:
        def __init__(self, *args, **kwargs):
            pass


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
        self.collections: Dict[str, Any] = {}

        # 分块配置
        self.chunk_size = kwargs.get('chunk_size', 1000)
        self.chunk_overlap = kwargs.get('chunk_overlap', 200)

        logger.info("ChromaKB initialized")

    @property
    def kb_type(self) -> str:
        """知识库类型标识"""
        return "chroma"

    async def _create_kb_instance(self, db_id: str, config: Dict) -> Any:
        """创建向量数据库集合"""
        logger.info(f"Creating ChromaDB collection for {db_id}")

        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        embed_info = self.databases_meta[db_id].get("embed_info", {})
        embedding_function = self._get_embedding_function(embed_info)

        # 创建或获取集合
        collection_name = f"kb_{db_id}"

        try:
            # 尝试获取现有集合
            collection = self.chroma_client.get_collection(name=collection_name)
            logger.info(f"Retrieved existing collection: {collection_name}")

            # 检查现有集合的配置是否匹配当前的 embed_info
            expected_model = embed_info.get("name") if embed_info else "default"
            collection_metadata = collection.metadata or {}
            current_model = collection_metadata.get("embedding_model", "unknown")

            # 如果模型不匹配，删除现有集合并重新创建
            if current_model != expected_model:
                logger.warning(f"Collection {collection_name} uses model '{current_model}', but expected '{expected_model}'. Recreating collection.")
                self.chroma_client.delete_collection(name=collection_name)
                raise Exception("Model mismatch, recreating collection")

        except Exception as e:
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

        # 返回符合 ChromaDB 0.4.16+ 接口的 EmbeddingFunction 实例
        return OpenAIEmbeddingFunction(
            model=model,
            api_key=api_key,
            base_url=base_url
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
                    "metadata": {
                        "source": filename,
                        "chunk_id": f"{file_id}_chunk_{chunk_index}",
                        "full_doc_id": file_id
                    }
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
                "metadata": {
                    "source": filename,
                    "chunk_id": f"{file_id}_chunk_{chunk_index}",
                    "full_doc_id": file_id
                }
            })

        return chunks

    async def add_content(self, db_id: str, items: List[str],
                         params: Optional[Dict] = None) -> List[Dict]:
        """添加内容（文件/URL）"""
        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        collection = await self._get_chroma_collection(db_id)
        if not collection:
            raise ValueError(f"Failed to get ChromaDB collection for {db_id}")

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

            processed_items_info.append(file_record)

        return processed_items_info

    async def aquery(self, query_text: str, db_id: str, **kwargs) -> str:
        """异步查询知识库"""
        collection = await self._get_chroma_collection(db_id)
        if not collection:
            raise ValueError(f"Database {db_id} not found")

        try:
            # 设置查询参数 - ChromaDB 知识库特有的参数
            top_k = kwargs.get("top_k", 10)
            similarity_threshold = kwargs.get("similarity_threshold", 0.0)  # 相似度阈值
            include_distances = kwargs.get("include_distances", True)  # 是否包含距离信息

            # 执行相似性搜索
            results = collection.query(
                query_texts=[query_text],
                n_results=top_k,
                include=["documents", "metadatas", "distances"] if include_distances else ["documents", "metadatas"]
            )

            # 处理结果
            if results and results.get("documents") and results["documents"][0]:
                documents = results["documents"][0]
                metadatas = results["metadatas"][0] if results.get("metadatas") else []
                distances = results["distances"][0] if results.get("distances") else []

                # 构建上下文，应用相似度阈值过滤
                contexts = []
                for i, doc in enumerate(documents):
                    # 计算相似度（距离越小相似度越高）
                    similarity = 1 - distances[i] if i < len(distances) else 1.0

                    # 应用相似度阈值过滤
                    if similarity < similarity_threshold:
                        continue

                    context = f"[文档片段 {i+1}]:\n{doc}\n"
                    if i < len(metadatas) and metadatas[i]:
                        source = metadatas[i].get("source", "未知来源")
                        chunk_id = metadatas[i].get("chunk_id", f"chunk_{i}")
                        context += f"来源: {source} ({chunk_id})\n"
                    if include_distances and i < len(distances):
                        context += f"相似度: {similarity:.3f}\n"
                    contexts.append(context)

                response = "\n".join(contexts)
                logger.debug(f"ChromaDB query response: {len(contexts)} chunks found (after similarity filtering)")
                return response

            return ""

        except Exception as e:
            logger.error(f"ChromaDB query error: {e}, {traceback.format_exc()}")
            return ""

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

    async def get_file_info(self, db_id: str, file_id: str) -> Dict:
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