import os
import json
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any, AsyncGenerator
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

    def __init__(self, work_dir: str):
        """
        初始化知识库

        Args:
            work_dir: 工作目录
        """
        self.work_dir = work_dir
        self.databases_meta: Dict[str, Dict] = {}
        self.files_meta: Dict[str, Dict] = {}
        os.makedirs(work_dir, exist_ok=True)

        # 自动加载元数据
        self._load_metadata()

    @property
    @abstractmethod
    def kb_type(self) -> str:
        """知识库类型标识"""
        pass

    @abstractmethod
    async def _create_kb_instance(self, db_id: str, config: Dict) -> Any:
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
                       embed_info: Optional[Dict] = None, **kwargs) -> Dict:
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

    def delete_database(self, db_id: str) -> Dict:
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
    async def add_content(self, db_id: str, items: List[str],
                         params: Optional[Dict] = None) -> List[Dict]:
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
    async def aquery(self, query_text: str, db_id: str, **kwargs) -> str:
        """
        异步查询知识库

        Args:
            query_text: 查询文本
            db_id: 数据库ID
            **kwargs: 查询参数

        Returns:
            查询结果
        """
        pass

    def query(self, query_text: str, db_id: str, **kwargs) -> str:
        """
        同步查询知识库（兼容性方法）

        Args:
            query_text: 查询文本
            db_id: 数据库ID
            **kwargs: 查询参数

        Returns:
            查询结果
        """
        import asyncio
        logger.warning("query is deprecated, use aquery instead")
        return asyncio.run(self.aquery(query_text, db_id, **kwargs))

    def get_database_info(self, db_id: str) -> Optional[Dict]:
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

    def get_databases(self) -> Dict:
        """
        获取所有数据库信息

        Returns:
            数据库列表
        """
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
    async def get_file_info(self, db_id: str, file_id: str) -> Dict:
        """
        获取文件信息和chunks

        Args:
            db_id: 数据库ID
            file_id: 文件ID

        Returns:
            文件信息和chunks
        """
        pass

    def get_db_upload_path(self, db_id: Optional[str] = None) -> str:
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

    def update_database(self, db_id: str, name: str, description: str) -> Dict:
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

    def get_retrievers(self) -> Dict[str, Dict]:
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

    async def _process_file_to_markdown(self, file_path: str,
                                      params: Optional[Dict] = None) -> str:
        """
        将不同类型的文件转换为markdown格式

        Args:
            file_path: 文件路径
            params: 处理参数

        Returns:
            markdown格式内容
        """
        file_path_obj = Path(file_path)
        file_ext = file_path_obj.suffix.lower()

        if file_ext == '.pdf':
            # 使用 OCR 处理 PDF
            from src.core.indexing import parse_pdf_async
            text = await parse_pdf_async(str(file_path_obj), params=params)
            return f"Using OCR to process {file_path_obj.name}\n\n{text}"

        elif file_ext in ['.txt', '.md']:
            # 直接读取文本文件
            with open(file_path_obj, encoding='utf-8') as f:
                content = f.read()
            return f"# {file_path_obj.name}\n\n{content}"

        elif file_ext in ['.doc', '.docx']:
            # 处理 Word 文档
            from docx import Document  # type: ignore
            doc = Document(file_path_obj)
            text = '\n'.join([para.text for para in doc.paragraphs])
            return f"# {file_path_obj.name}\n\n{text}"

        elif file_ext in ['.jpg', '.jpeg', '.png', '.bmp']:
            # 使用 OCR 处理图片
            from src.plugins import ocr
            text = ocr.process_image(str(file_path_obj))
            return f"# {file_path_obj.name}\n\n{text}"

        else:
            # 尝试作为文本文件读取
            try:
                import textract  # type: ignore
                text = textract.process(file_path_obj).decode('utf-8')
                return f"# {file_path_obj.name}\n\n{text}"
            except Exception as e:
                logger.error(f"Failed to process file {file_path_obj}: {e}")
                return f"# {file_path_obj.name}\n\nFailed to process file: {e}"

    async def _process_url_to_markdown(self, url: str,
                                     params: Optional[Dict] = None) -> str:
        """
        将URL转换为markdown格式

        Args:
            url: URL地址
            params: 处理参数

        Returns:
            markdown格式内容
        """
        import requests
        from bs4 import BeautifulSoup

        try:
            response = requests.get(url, timeout=30)
            soup = BeautifulSoup(response.content, 'html.parser')
            text_content = soup.get_text()
            return f"# {url}\n\n{text_content}"
        except Exception as e:
            logger.error(f"Failed to process URL {url}: {e}")
            return f"# {url}\n\nFailed to process URL: {e}"