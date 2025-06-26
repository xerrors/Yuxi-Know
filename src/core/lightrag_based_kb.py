import os
import json
import time
import traceback
import shutil
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc
from lightrag.kg.shared_storage import initialize_pipeline_status

from src import config
from src.utils import logger, hashstr, get_docker_safe_url
from src.plugins import ocr


class LightRagBasedKB:
    """基于 LightRAG 的知识库管理类"""

    def __init__(self) -> None:
        # 存储 LightRAG 实例映射 {db_id: LightRAG}
        self.instances: Dict[str, LightRAG] = {}
        # 数据库元信息存储 {db_id: metadata}
        self.databases_meta: Dict[str, dict] = {}
        # 文件信息存储 {file_id: file_info}
        self.files_meta: Dict[str, dict] = {}
        # 工作目录
        self.work_dir = os.path.join(config.save_dir, "lightrag_data")
        os.makedirs(self.work_dir, exist_ok=True)

        # 加载已有的元数据
        self._load_metadata()

        logger.info("LightRagBasedKB initialized")

    def _load_metadata(self):
        """加载元数据"""
        meta_file = os.path.join(self.work_dir, "metadata.json")
        if os.path.exists(meta_file):
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.databases_meta = data.get("databases", {})
                    self.files_meta = data.get("files", {})
                logger.info(f"Loaded metadata for {len(self.databases_meta)} databases")
            except Exception as e:
                logger.error(f"Failed to load metadata: {e}")

    def _save_metadata(self):
        """保存元数据"""
        # 确保工作目录存在
        os.makedirs(self.work_dir, exist_ok=True)

        meta_file = os.path.join(self.work_dir, "metadata.json")
        try:
            data = {
                "databases": self.databases_meta,
                "files": self.files_meta
            }
            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")

    async def _get_lightrag_instance(self, db_id: str) -> Optional[LightRAG]:
        """获取或创建 LightRAG 实例"""
        logger.info(f"Getting or creating LightRAG instance for {db_id}")

        if db_id in self.instances:
            return self.instances[db_id]

        if db_id not in self.databases_meta:
            return None

        # 创建 LightRAG 实例
        working_dir = os.path.join(self.work_dir, db_id)
        os.makedirs(working_dir, exist_ok=True)

        try:
            # 使用配置的 LLM 和 embedding 函数
            rag = LightRAG(
                working_dir=working_dir,
                llm_model_func=self._get_llm_func(),
                embedding_func=self._get_embedding_func(),
                vector_storage="MilvusVectorDBStorage",
                kv_storage="JsonKVStorage",
                graph_storage="PGGraphStorage",
                doc_status_storage="JsonDocStatusStorage",
                log_file_path=os.path.join(self.work_dir, db_id, "lightrag.log"),
            )

            # 异步初始化存储
            await self._initialize_rag_storages(rag)

            self.instances[db_id] = rag
            return rag

        except Exception as e:
            logger.error(f"Failed to create LightRAG instance for {db_id}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    async def _initialize_rag_storages(self, rag: LightRAG):
        """异步初始化 LightRAG 存储"""
        logger.info(f"Initializing LightRAG storages for {rag.working_dir}")
        await rag.initialize_storages()
        await initialize_pipeline_status()

    def _get_llm_func(self):
        """获取 LLM 函数"""
        async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
            return await openai_complete_if_cache(
                "qwen3:32b",
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                api_key="no_api_key",
                base_url="http://172.19.13.7:8080/v1",
                **kwargs,
            )
        return llm_model_func

    def _get_embedding_func(self):
        """获取 embedding 函数"""
        return EmbeddingFunc(
            embedding_dim=1024,
            max_token_size=4096,
            func=lambda texts: openai_embed(
                texts=texts,
                model="Qwen3-Embedding-0.6B",
                api_key="no_api_key",
                base_url=get_docker_safe_url("http://localhost:8081/v1")
            ),
        )

    async def _process_file_to_markdown(self, file_path: str, params=None) -> str:
        """将不同类型的文件转换为 markdown 格式"""
        file_path = Path(file_path)
        file_ext = file_path.suffix.lower()

        if file_ext == '.pdf':
            # 使用 OCR 处理 PDF
            from src.core.indexing import parse_pdf_async
            text = await parse_pdf_async(str(file_path), params=params)
            return f"Using OCR to process {file_path.name}\n\n{text}"

        elif file_ext in ['.txt', '.md']:
            # 直接读取文本文件
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return f"Using f.read() to process {file_path.name}\n\n{content}"

        elif file_ext in ['.doc', '.docx']:
            # 处理 Word 文档
            try:
                from docx import Document
                doc = Document(file_path)
                text = '\n'.join([para.text for para in doc.paragraphs])
                return f"Using python-docx to process {file_path.name}\n\n{text}"
            except ImportError:
                logger.warning("python-docx not installed, cannot process .docx files")
                return f"# {file_path.name}\n\n[Cannot process .docx file - python-docx not installed]"

        elif file_ext in ['.jpg', '.jpeg', '.png', '.bmp']:
            # 使用 OCR 处理图片
            text = ocr.process_image(str(file_path))
            return f"Using OCR to process {file_path.name}\n\n{text}"

        else:
            # 尝试作为文本文件读取
            import textract
            text = textract.process(file_path)
            return f"Using textract to process {file_path.name}\n\n{text}"

    async def _process_url_to_markdown(self, url: str, params=None) -> str:
        """将 URL 转换为 markdown 格式"""
        try:
            import requests
            from bs4 import BeautifulSoup

            response = requests.get(url, timeout=30)
            soup = BeautifulSoup(response.content, 'html.parser')
            text_content = soup.get_text()
            return f"# {url}\n\n{text_content}"
        except Exception as e:
            logger.warning(f"Failed to scrape URL {url}: {e}")
            return f"# {url}\n\n[Failed to scrape URL: {str(e)}]"

    # =============================================================================
    # data_router.py 中使用的核心方法
    # =============================================================================

    def get_databases(self):
        """获取所有数据库信息 - data_router.py 使用"""
        databases = []
        for db_id, meta in self.databases_meta.items():
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

            db_dict["files"] = db_files
            db_dict["row_count"] = len(db_files)
            db_dict["status"] = "已连接"
            databases.append(db_dict)

        return {"databases": databases}

    def create_database(self, database_name, description, embed_info: dict = None, **kwargs):
        """创建数据库 - data_router.py 使用"""
        db_id = f"kb_{hashstr(database_name, with_salt=True)}"

        # 创建数据库记录
        self.databases_meta[db_id] = {
            "name": database_name,
            "description": description,
            "embed_info": embed_info,
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

    def delete_database(self, db_id):
        """删除数据库 - data_router.py 使用"""
        if db_id in self.databases_meta:
            # 删除相关文件记录
            files_to_delete = [fid for fid, finfo in self.files_meta.items()
                             if finfo.get("database_id") == db_id]
            for file_id in files_to_delete:
                del self.files_meta[file_id]

            # 删除数据库记录
            del self.databases_meta[db_id]

            # 删除 LightRAG 实例
            if db_id in self.instances:
                del self.instances[db_id]

            self._save_metadata()

        # 删除工作目录
        working_dir = os.path.join(self.work_dir, db_id)
        if os.path.exists(working_dir):
            try:
                shutil.rmtree(working_dir)
            except Exception as e:
                logger.error(f"Error deleting working directory {working_dir}: {e}")

        return {"message": "删除成功"}

    async def add_content(self, db_id, items, params=None):
        """通用的内容添加方法 - 支持文件和URL"""
        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        rag = await self._get_lightrag_instance(db_id)
        if not rag:
            raise ValueError(f"Failed to get LightRAG instance for {db_id}")

        content_type = params.get('content_type', 'file')

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
                    logger.info(f"Markdown content: {markdown_content[:100].replace('\n', ' ')}...")
                else:  # URL
                    markdown_content = await self._process_url_to_markdown(item, params=params)

                # 使用 LightRAG 插入内容
                await rag.ainsert(
                    input=markdown_content,
                    ids=file_id,
                    file_paths=item_path
                )

                logger.info(f"Inserted {content_type} {item} into LightRAG. Done.")

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

    def get_database_info(self, db_id):
        """获取数据库详细信息 - data_router.py 使用"""
        if db_id not in self.databases_meta:
            return None

        meta = self.databases_meta[db_id].copy()
        meta["db_id"] = db_id

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

        meta["files"] = db_files
        meta["row_count"] = len(db_files)
        meta["status"] = "已连接"
        return meta

    async def delete_file(self, db_id, file_id):
        """删除文件 - data_router.py 使用"""
        rag = await self._get_lightrag_instance(db_id)
        if rag:
            try:
                # 使用 LightRAG 删除文档
                await rag.adelete_by_doc_id(file_id)
            except Exception as e:
                logger.error(f"Error deleting file {file_id} from LightRAG: {e}")

        # 删除文件记录
        if file_id in self.files_meta:
            del self.files_meta[file_id]
            self._save_metadata()

    async def get_file_info(self, db_id, file_id):
        """获取文件信息和其 chunks - data_router.py 使用"""
        if file_id not in self.files_meta:
            raise Exception(f"File not found: {file_id}")

        # 使用 LightRAG 获取 chunks
        rag = await self._get_lightrag_instance(db_id)
        if rag:
            try:
                # 获取文档的所有 chunks
                all_chunks = await rag.text_chunks.get_all()

                # 筛选属于该文档的 chunks
                doc_chunks = []
                for chunk_id, chunk_data in all_chunks.items():
                    if isinstance(chunk_data, dict) and chunk_data.get("full_doc_id") == file_id:
                        chunk_data["id"] = chunk_id
                        chunk_data["content_vector"] = []
                        doc_chunks.append(chunk_data)

                # 按 chunk_order_index 排序
                doc_chunks.sort(key=lambda x: x.get("chunk_order_index", 0))
                # logger.debug(f"All chunks: {doc_chunks}")
                return {"lines": doc_chunks}

            except Exception as e:
                logger.error(f"Error getting chunks for file {file_id}: {e}")

        return {"lines": []}

    def get_db_upload_path(self, db_id=None):
        """获取数据库上传路径 - data_router.py 使用"""
        if db_id:
            uploads_folder = os.path.join(self.work_dir, db_id, "uploads")
            os.makedirs(uploads_folder, exist_ok=True)
            return uploads_folder

        general_uploads = os.path.join(self.work_dir, "uploads")
        os.makedirs(general_uploads, exist_ok=True)
        return general_uploads

    def update_database(self, db_id, name, description):
        """更新数据库 - data_router.py 使用"""
        if db_id not in self.databases_meta:
            raise ValueError(f"数据库 {db_id} 不存在")

        self.databases_meta[db_id]["name"] = name
        self.databases_meta[db_id]["description"] = description
        self._save_metadata()

        # 返回更新后的数据库信息
        return self.get_database_info(db_id)

    # =============================================================================
    # 为了系统兼容性需要的其他方法
    # =============================================================================

    def query(self, query_text, db_id, **kwargs):
        logger.warning("query is deprecated, use aquery instead")
        return asyncio.run(self.aquery(query_text, db_id, **kwargs))

    async def aquery(self, query_text, db_id, **kwargs):
        """查询知识库 - 用于检索器"""
        rag = await self._get_lightrag_instance(db_id)
        if not rag:
            raise ValueError(f"Database {db_id} not found")

        try:
            # 设置查询参数
            params_dict = {
                "mode": "mix",
                "only_need_context": True,
                "top_k": 10,
            } | kwargs
            param = QueryParam(**params_dict)

            # 执行查询
            response = await rag.aquery(query_text, param)
            logger.debug(f"Query response: {response}")

            return response

        except Exception as e:
            logger.error(f"Query error: {e}, {traceback.format_exc()}")
            return ""

    def get_retrievers(self):
        """获取所有检索器 - 用于工具系统"""
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
            }
        return retrievers