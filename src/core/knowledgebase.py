import os
import json
import time
import traceback
import shutil
from sqlalchemy.orm import joinedload

from pymilvus import MilvusClient, MilvusException

from src import config
from src.utils import logger, hashstr
from src.core.indexing import chunk, read_text_async
from server.db_manager import db_manager
from server.models.kb_models import KnowledgeDatabase, KnowledgeFile, KnowledgeNode
from src.utils.db_migration import migrate_knowledge_db

class KnowledgeBase:

    def __init__(self) -> None:
        self.client = None
        self.work_dir = os.path.join(config.save_dir, "data")

        # Configuration
        self.default_distance_threshold = 0.5
        self.default_rerank_threshold = 0.1
        self.default_max_query_count = 20

        # 检查是否需要从JSON文件迁移到SQLite
        self._check_migration()

        self._load_models()

    def _to_dict_safely(self, obj):
        """安全地将对象转换为字典，避免延迟加载问题"""
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        return obj

    def _check_migration(self):
        """检查是否需要从JSON文件迁移到SQLite和从knowledge.db迁移到server.db"""
        # 检查旧的JSON文件迁移
        json_path = os.path.join(self.work_dir, "database.json")
        if os.path.exists(json_path):
            logger.info("检测到旧的JSON格式知识库数据，准备迁移到SQLite...")
            try:
                from src.core.migrate_kb_to_sqlite import migrate_json_to_sqlite
                result = migrate_json_to_sqlite()
                if result:
                    logger.info("知识库数据已成功迁移到SQLite")
                else:
                    logger.warning("知识库数据迁移失败或无需迁移")
            except Exception as e:
                logger.error(f"迁移过程中出错: {e}")

        # 检查独立knowledge.db迁移
        knowledge_db_path = os.path.join(config.save_dir, "data", "knowledge.db")
        if os.path.exists(knowledge_db_path):
            logger.info("检测到独立的knowledge.db数据库，准备合并到server.db...")
            try:
                result = migrate_knowledge_db()
                if result:
                    logger.info("knowledge.db数据已成功迁移到server.db")
                else:
                    logger.warning("knowledge.db数据迁移失败或无需迁移")
            except Exception as e:
                logger.error(f"迁移过程中出错: {e}")

    def _load_models(self):
        """所有需要重启的模型"""
        if not config.enable_knowledge_base:
            return

        from src.models.embedding import get_embedding_model
        self.embed_model = get_embedding_model(config)

        if config.enable_reranker:
            from src.models.rerank_model import get_reranker
            self.reranker = get_reranker(config)

        if not self.connect_to_milvus():
            raise ConnectionError("Failed to connect to Milvus")

    # 知识库数据库操作方法
    def get_all_databases(self):
        """获取所有知识库"""
        with db_manager.get_session_context() as session:
            # 使用eager loading加载关联的files
            databases = session.query(KnowledgeDatabase).options(
                joinedload(KnowledgeDatabase.files)
            ).all()

            # 转换为字典并返回，避免后续延迟加载
            return [self._to_dict_safely(db) for db in databases]

    def get_database_by_id(self, db_id):
        """根据ID获取知识库"""
        with db_manager.get_session_context() as session:
            # 使用eager loading加载关联的files
            db = session.query(KnowledgeDatabase).options(
                joinedload(KnowledgeDatabase.files).joinedload(KnowledgeFile.nodes)
            ).filter_by(db_id=db_id).first()

            # 转换为字典并返回，避免后续延迟加载
            return self._to_dict_safely(db) if db else None

    def create_database_record(self, db_id, name, description, embed_model=None, dimension=None, metadata=None):
        """在数据库中创建知识库记录"""
        with db_manager.get_session_context() as session:
            db = KnowledgeDatabase(
                db_id=db_id,
                name=name,
                description=description,
                embed_model=embed_model,
                dimension=dimension,
                meta_info=metadata or {}  # 存储到meta_info字段
            )
            session.add(db)
            session.flush()  # 立即写入数据库，获取ID

            # 手动将必要的数据加载到内存中
            db_dict = {
                "db_id": db_id,
                "name": name,
                "description": description,
                "embed_model": embed_model,
                "dimension": dimension,
                "metadata": metadata or {},  # 返回时使用metadata键
                "files": {}
            }
            return db_dict

    def delete_database_record(self, db_id):
        """从数据库中删除知识库记录"""
        with db_manager.get_session_context() as session:
            db = session.query(KnowledgeDatabase).filter_by(db_id=db_id).first()
            if db:
                session.delete(db)
                return True
            return False

    def update_database_record(self, db_id, name, description):
        """更新数据库中的知识库记录"""
        with db_manager.get_session_context() as session:
            db = session.query(KnowledgeDatabase).filter_by(db_id=db_id).first()
            if not db:
                raise ValueError(f"数据库 {db_id} 不存在")

            # 更新字段
            db.name = name
            db.description = description
            session.commit()

            # 返回更新后的数据库信息
            return self._to_dict_safely(db)

    def add_file_record(self, db_id, file_id, filename, path, file_type, status="waiting"):
        """在数据库中添加文件记录"""
        with db_manager.get_session_context() as session:
            file = KnowledgeFile(
                file_id=file_id,
                database_id=db_id,
                filename=filename,
                path=path,
                file_type=file_type,
                status=status
            )
            session.add(file)
            session.flush()

            # 返回字典而非对象，避免会话关闭后的延迟加载问题
            return {
                "file_id": file_id,
                "filename": filename,
                "path": path,
                "type": file_type,
                "status": status,
                "created_at": file.created_at.timestamp() if file.created_at else None,
                "nodes": []
            }

    def update_file_status(self, file_id, status):
        """更新文件状态"""
        with db_manager.get_session_context() as session:
            file = session.query(KnowledgeFile).filter_by(file_id=file_id).first()
            if file:
                file.status = status
                return True
            return False

    def delete_file_record(self, file_id):
        """从数据库中删除文件记录"""
        with db_manager.get_session_context() as session:
            file = session.query(KnowledgeFile).filter_by(file_id=file_id).first()
            if file:
                session.delete(file)
                return True
            return False

    def get_files_by_database(self, db_id):
        """获取知识库下的所有文件"""
        with db_manager.get_session_context() as session:
            files = session.query(KnowledgeFile).options(
                joinedload(KnowledgeFile.nodes)
            ).filter_by(database_id=db_id).all()
            return [self._to_dict_safely(file) for file in files]

    def get_file_by_id(self, file_id):
        """根据ID获取文件"""
        with db_manager.get_session_context() as session:
            file = session.query(KnowledgeFile).options(
                joinedload(KnowledgeFile.nodes)
            ).filter_by(file_id=file_id).first()
            return self._to_dict_safely(file) if file else None

    def add_node(self, file_id, text, hash_value=None, start_char_idx=None, end_char_idx=None, metadata=None):
        """添加知识块"""
        with db_manager.get_session_context() as session:
            node = KnowledgeNode(
                file_id=file_id,
                text=text,
                hash=hash_value,
                start_char_idx=start_char_idx,
                end_char_idx=end_char_idx,
                meta_info=metadata or {}
            )
            session.add(node)
            session.flush()

            # 返回字典而非对象，避免会话关闭后的延迟加载问题
            return {
                "id": node.id,
                "file_id": file_id,
                "text": text,
                "hash": hash_value,
                "start_char_idx": start_char_idx,
                "end_char_idx": end_char_idx,
                "metadata": metadata or {}
            }

    def get_nodes_by_file(self, file_id):
        """获取文件下的所有知识块"""
        with db_manager.get_session_context() as session:
            nodes = session.query(KnowledgeNode).filter_by(file_id=file_id).all()
            return [self._to_dict_safely(node) for node in nodes]

    def get_nodes_by_filter(self, file_id=None, search_text=None, limit=100):
        """根据条件筛选知识块"""
        with db_manager.get_session_context() as session:
            query = session.query(KnowledgeNode)
            if file_id:
                query = query.filter_by(file_id=file_id)
            if search_text:
                query = query.filter(KnowledgeNode.text.like(f"%{search_text}%"))
            nodes = query.limit(limit).all()
            return [self._to_dict_safely(node) for node in nodes]

    def create_database(self, database_name, description, dimension=None):
        """创建一个数据库（业务逻辑）"""
        dimension = dimension or self.embed_model.get_dimension()
        db_id = f"kb_{hashstr(database_name, with_salt=True)}"

        # 创建数据库记录
        db_dict = self.create_database_record(
            db_id=db_id,
            name=database_name,
            description=description,
            embed_model=self.embed_model.embed_model_fullname,
            dimension=dimension
        )

        # 创建数据库对应的文件夹
        self._ensure_db_folders(db_id)

        # 在Milvus中创建集合
        self.add_collection(db_id, dimension)

        return db_dict

    def _ensure_db_folders(self, db_id):
        """确保数据库文件夹存在"""
        db_folder = os.path.join(self.work_dir, db_id)
        uploads_folder = os.path.join(db_folder, "uploads")
        os.makedirs(db_folder, exist_ok=True)
        os.makedirs(uploads_folder, exist_ok=True)
        return db_folder, uploads_folder

    def get_db_upload_path(self, db_id=None):
        """获取上传文件夹路径，如果没有指定db_id则使用默认路径"""
        _, uploads_folder = self._ensure_db_folders(db_id)
        return uploads_folder

    def get_databases(self):
        assert config.enable_knowledge_base, "知识库未启用"

        # 从数据库获取所有知识库
        databases = self.get_all_databases()

        # 检查和更新Milvus信息
        databases_with_milvus = []
        for db in databases:
            db_copy = db.copy()  # 创建字典的副本以避免修改原始数据
            # 更新Milvus集合信息
            try:
                milvus_info = self.get_collection_info(db["db_id"])
                db_copy["metadata"] = milvus_info
                # logger.debug(f"获取知识库 {db['name']} (ID: {db['db_id']}) 的Milvus信息成功: {milvus_info}")
            except Exception as e:
                logger.warning(f"获取知识库 {db['name']} (ID: {db['db_id']}) 的Milvus信息失败: {e}")
                # 添加一个默认的Milvus状态
                db_copy.update({
                    "row_count": 0,
                    "status": "未连接",
                    "error": str(e)
                })

            # 检查处理中的文件
            processing_files = [f for f_id, f in db_copy.get("files", {}).items()
                               if f["status"] in ["processing", "waiting"]]
            if processing_files:
                logger.info(f"数据库 {db['name']} 有 {len(processing_files)} 个文件正在处理中")

            databases_with_milvus.append(db_copy)

        return {"databases": databases_with_milvus}

    def get_database_info(self, db_id):
        db_dict = self.get_database_by_id(db_id)
        if db_dict is None:
            return None
        else:
            db_copy = db_dict.copy()
            try:
                # 保存原始描述
                original_description = db_copy.get("description")

                milvus_info = self.get_collection_info(db_id)
                db_copy.update(milvus_info)

                # 如果原始描述不为空，恢复它
                if original_description:
                    db_copy["description"] = original_description
            except Exception as e:
                logger.warning(f"获取知识库 ID: {db_id} 的Milvus信息失败: {e}")
                # 添加一个默认的Milvus状态
                db_copy.update({
                    "row_count": 0,
                    "status": "未连接",
                    "error": str(e)
                })
            return db_copy

    def get_database_id(self):
        databases = self.get_all_databases()
        return [db["db_id"] for db in databases]

    def get_file_info(self, db_id, file_id):
        db = self.get_database_by_id(db_id)
        if db is None:
            raise Exception(f"database not found, {db_id}")

        lines = self.client.query(
            collection_name=db_id,
            filter=f"file_id == '{file_id}'",
            output_fields=None
        )
        # 删除 vector 字段
        for line in lines:
            line.pop("vector")

        lines.sort(key=lambda x: x.get("start_char_idx") or 0)
        return {"lines": lines}

    def get_kb_by_id(self, db_id):
        if not config.enable_knowledge_base:
            return None

        return self.get_database_by_id(db_id)

    async def file_to_chunk(self, files, params=None):
        """将文件转换为分块

        这里主要是将文件转换为分块，但并不保存到数据库，仅仅返回分块后的信息，返回的信息里面也包含文件的id，文件名，文件类型，文件路径，文件状态，文件创建时间等。
        files: list of file path
        params: params for chunking

        return: list of chunk info
        """
        file_infos = {}
        for file in files:
            file_id = "file_" + hashstr(file + str(time.time()))

            file_type = file.split(".")[-1].lower()

            if file_type == "pdf":
                texts = await read_text_async(file)
                nodes = chunk(texts, params=params)
            else:
                nodes = chunk(file, params=params)

            file_infos[file_id] = {
                "file_id": file_id,
                "filename": os.path.basename(file),
                "path": file,
                "type": file_type,
                "status": "waiting",
                "created_at": time.time(),
                "nodes": [node.dict() for node in nodes]
            }

        return file_infos

    async def url_to_chunk(self, urls, params=None):
        """将url转换为分块，读取url的内容，并转换为分块

        Args:
            urls: list of urls
            params: params for chunking

        Returns:
            dict: 包含分块信息的字典
        """
        try:
            from langchain_community.document_loaders import UnstructuredURLLoader
        except ImportError:
            raise ImportError("请安装 langchain_community 和 unstructured 包：pip install langchain-community unstructured")

        file_infos = {}

        # 使用UnstructuredURLLoader加载URL内容
        # loader = UnstructuredURLLoader(urls=urls, continue_on_failure=True)

        for url_idx, url in enumerate(urls):
            file_id = "url_" + hashstr(url + str(time.time()))

            try:
                # 加载单个URL内容
                single_loader = UnstructuredURLLoader(urls=[url], continue_on_failure=False)
                documents = await single_loader.aload()

                # 将文档内容合并
                text_content = "\n\n".join([doc.page_content for doc in documents])

                # 对内容进行分块
                nodes = chunk(text_content, params=params)

                # 从URL中提取域名作为文件名
                from urllib.parse import urlparse, unquote
                parsed_url = urlparse(unquote(url))
                domain = parsed_url.netloc
                path = parsed_url.path
                filename = f"{domain}{path}"
                if filename.endswith('/'):
                    filename = filename[:-1]
                if len(filename) > 100:
                    filename = filename[:97] + "..."
                filename = filename.replace('/', '_')

                file_infos[file_id] = {
                    "file_id": file_id,
                    "filename": filename,
                    "path": url,
                    "type": "url",
                    "status": "waiting",
                    "created_at": time.time(),
                    "nodes": [node.dict() for node in nodes]
                }
            except Exception as e:
                logger.error(f"处理URL {url} 时出错: {e}")
                file_infos[file_id] = {
                    "file_id": file_id,
                    "filename": url[:100] + "..." if len(url) > 100 else url,
                    "path": url,
                    "type": "url",
                    "status": "failed",
                    "created_at": time.time(),
                    "error": str(e),
                    "nodes": []
                }

        return file_infos

    async def add_chunks(self, db_id, file_chunks):
        """添加分块"""
        db = self.get_kb_by_id(db_id)

        if db["embed_model"] != self.embed_model.embed_model_fullname:
            logger.error(f"Embed model not match, {db['embed_model']} != {self.embed_model.embed_model_fullname}")
            return {"message": f"Embed model not match, cur: {self.embed_model.embed_model_fullname}, req: {db['embed_model']}", "status": "failed"}

        for file_id, chunk_info in file_chunks.items():
            # 在数据库中创建文件记录
            self.add_file_record(
                db_id=db_id,
                file_id=file_id,
                filename=chunk_info["filename"],
                path=chunk_info["path"],
                file_type=chunk_info["type"],
                status="processing"
            )

            try:
                await self.add_documents(
                    file_id=file_id,
                    collection_name=db_id,
                    docs=[node["text"] for node in chunk_info["nodes"]],
                    chunk_infos=chunk_info["nodes"])

                # 更新文件状态为完成
                self.update_file_status(file_id, "done")

            except Exception as e:
                logger.error(f"Failed to add documents to collection {db_id}, {e}, {traceback.format_exc()}")
                # 更新文件状态为失败
                self.update_file_status(file_id, "failed")

    async def add_files(self, db_id, files, params=None):
        db = self.get_kb_by_id(db_id)

        if not self.check_embed_model(db_id):
            logger.error(f"Embed model not match, {db['embed_model']} != {self.embed_model.embed_model_fullname}")
            return {"message": f"Embed model not match, cur: {self.embed_model.embed_model_fullname}, req: {db['embed_model']}", "status": "failed"}

        # Preprocessing the files to the queue
        new_files = await self.file_to_chunk(files, params=params)

        for file_id, new_file in new_files.items():
            # 在数据库中创建文件记录
            self.add_file_record(
                db_id=db_id,
                file_id=file_id,
                filename=new_file["filename"],
                path=new_file["path"],
                file_type=new_file["type"],
                status="processing"
            )

            try:
                await self.add_documents(
                    file_id=file_id,
                    collection_name=db_id,
                    docs=[node["text"] for node in new_file["nodes"]],
                    chunk_infos=new_file["nodes"])

                # 更新文件状态为完成
                self.update_file_status(file_id, "done")

            except Exception as e:
                logger.error(f"Failed to add documents to collection {db_id}, {e}, {traceback.format_exc()}")
                # 更新文件状态为失败
                self.update_file_status(file_id, "failed")

    def delete_file(self, db_id, file_id):
        # 从Milvus中删除文件的向量
        self.client.delete(collection_name=db_id, filter=f"file_id == '{file_id}'")

        # 从SQLite中删除文件记录
        self.delete_file_record(file_id)

    def delete_database(self, db_id):
        # 从Milvus中删除集合
        self.client.drop_collection(collection_name=db_id)

        # 从SQLite中删除数据库记录
        self.delete_database_record(db_id)

        # 删除数据库对应的文件夹
        db_folder = os.path.join(self.work_dir, db_id)
        if os.path.exists(db_folder):
            shutil.rmtree(db_folder)

        return {"message": "删除成功"}

    def restart(self):
        self._load_models()

    ###################################
    #* Below is the code for retriever #
    ###################################

    def query(self, query, db_id, **kwargs):

        distance_threshold = kwargs.get("distance_threshold", self.default_distance_threshold)
        rerank_threshold = kwargs.get("rerank_threshold", self.default_rerank_threshold)
        max_query_count = kwargs.get("max_query_count", self.default_max_query_count)

        all_db_result = self.search(query, db_id, limit=max_query_count)
        all_db_result = [dict(r) for r in all_db_result]

        # 获取文件信息并添加到结果中
        for res in all_db_result:
            file = self.get_file_by_id(res["entity"]["file_id"])
            if file:
                res["file"] = file

        db_result = [r for r in all_db_result if r["distance"] > distance_threshold]

        if config.enable_reranker and len(db_result) > 0 and self.reranker:
            texts = [r["entity"]["text"] for r in db_result]
            rerank_scores = self.reranker.compute_score([query, texts], normalize=False)
            for i, r in enumerate(db_result):
                r["rerank_score"] = rerank_scores[i]
            db_result.sort(key=lambda x: x["rerank_score"], reverse=True)
            db_result = [_res for _res in db_result if _res["rerank_score"] > rerank_threshold]

        if kwargs.get("top_k", None):
            db_result = db_result[:kwargs["top_k"]]

        return {
            "results": db_result,
            "all_results": all_db_result,
        }

    def get_retriever_by_db_id(self, db_id):
        retriever_params = {
            "distance_threshold": self.default_distance_threshold,
            "rerank_threshold": self.default_rerank_threshold,
            "max_query_count": self.default_max_query_count,
            "top_k": 10,
        }

        def retriever(query):
            response = self.query(query, db_id, **retriever_params)
            return response["results"]

        return retriever

    def get_retrievers(self):
        retrievers = {}
        for db in self.get_all_databases():
            if self.check_embed_model(db["db_id"]):
                retrievers[db["db_id"]] = {
                    "name": db["name"],
                    "description": db["description"],
                    "retriever": self.get_retriever_by_db_id(db["db_id"]),
                    "embed_model": db["embed_model"],
                }
            else:
                logger.warning((
                    f"无法将知识库 {db['name']} 转换为 Tools, 因为向量模型不匹配，"
                    f"当前向量模型: {self.embed_model.embed_model_fullname}，"
                    f"知识库向量模型: {db['embed_model']}。"
                ))
        return retrievers

    ################################
    #* Below is the code for milvus #
    ################################
    def connect_to_milvus(self):
        """
        连接到 Milvus 服务。
        使用配置中的 URI，如果没有配置，则使用默认值。
        """
        try:
            uri = os.getenv('MILVUS_URI', config.get('milvus_uri', "http://milvus:19530"))
            self.client = MilvusClient(uri=uri)
            # 可以添加一个简单的测试来确保连接成功
            self.client.list_collections()
            logger.info(f"Successfully connected to Milvus at {uri}")
            return True
        except MilvusException as e:
            logger.error(f"Failed to connect to Milvus: {e}，请检查 milvus 的容器是否正常运行，如果已退出，请重新启动 `docker restart milvus-standalone-dev`")
            return False

    def get_collection_names(self):
        return self.client.list_collections()

    def get_collections(self):
        collections_name = self.client.list_collections()
        collections = []
        for collection_name in collections_name:
            collection = self.get_collection_info(collection_name)
            collections.append(collection)

        return collections

    def get_collection_info(self, collection_name):
        """获取Milvus集合信息，处理可能的错误"""
        try:
            collection = self.client.describe_collection(collection_name)
            collection.update(self.client.get_collection_stats(collection_name))
            return collection
        except MilvusException as e:
            logger.warning(f"获取集合 {collection_name} 信息失败: {e}")
            # 返回一个带有错误信息的基本结构
            return {
                "name": collection_name,
                "row_count": 0,
                "status": "错误",
                "error_message": str(e)
            }

    def add_collection(self, collection_name, dimension=None):
        if self.client.has_collection(collection_name=collection_name):
            logger.warning(f"Collection {collection_name} already exists, drop it")
            self.client.drop_collection(collection_name=collection_name)

        self.client.create_collection(
            collection_name=collection_name,
            dimension= dimension,  # The vectors we will use in this demo has 768 dimensions
        )

    async def add_documents(self, docs, collection_name, chunk_infos=None, **kwargs):
        """添加已经分块之后的文本"""
        # 检查 collection 是否存在
        import random
        if not self.client.has_collection(collection_name=collection_name):
            logger.error(f"Collection {collection_name} not found, create it")
            # self.add_collection(collection_name)

        chunk_infos = chunk_infos or [{}] * len(docs)

        vectors = await self.embed_model.abatch_encode(docs)

        data = [{
            "id": int(random.random() * 1e12),
            "vector": vectors[i],
            "text": docs[i],
            "hash": hashstr(docs[i], with_salt=True),
            **kwargs,
            **chunk_infos[i]
        } for i in range(len(vectors))]

        res = self.client.insert(collection_name=collection_name, data=data)
        return res

    def search(self, query, collection_name, limit=3):
        """搜索数据库"""
        query_vectors = self.embed_model.batch_encode([query])
        return self.search_by_vector(query_vectors[0], collection_name, limit)

    def search_by_vector(self, vector, collection_name, limit=3):
        res = self.client.search(
            collection_name=collection_name,  # target collection
            data=[vector],  # query vectors
            limit=limit,  # number of returned entities
            output_fields=["text", "file_id"],  # specifies fields to be returned
        )

        return res[0]

    def examples(self, collection_name, limit=20):
        res = self.client.query(
            collection_name=collection_name,
            limit=10,
            output_fields=["id", "text"],
        )
        return res

    def search_by_id(self, collection_name, id, output_fields=["id", "text"]):
        res = self.client.get(collection_name, id, output_fields=output_fields)
        return res

    def check_embed_model(self, db_id):
        db = self.get_database_by_id(db_id)
        return db["embed_model"] == self.embed_model.embed_model_fullname

    def update_database(self, db_id, name, description):
        """更新知识库信息"""
        # 检查知识库是否存在
        db = self.get_database_by_id(db_id)
        if db is None:
            raise Exception(f"数据库不存在: {db_id}")

        # 调用update_database_record更新知识库信息
        updated_db = self.update_database_record(db_id, name, description)
        return updated_db

