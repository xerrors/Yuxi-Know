import os
import json
import time
import traceback
import shutil

from pymilvus import MilvusClient, MilvusException

from src import config
from src.utils import logger, hashstr
from src.core.indexing import chunk, read_text
from src.core.kb_db_manager import kb_db_manager

class KnowledgeBase:

    def __init__(self) -> None:
        self.client = None
        self.work_dir = os.path.join(config.save_dir, "data")

        # 数据库管理器
        self.db_manager = kb_db_manager

        # Configuration
        self.default_distance_threshold = 0.5
        self.default_rerank_threshold = 0.1
        self.default_max_query_count = 20

        # 检查是否需要从JSON文件迁移到SQLite
        self._check_migration()

        self._load_models()

    def _check_migration(self):
        """检查是否需要从JSON文件迁移到SQLite"""
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

    def create_database(self, database_name, description, dimension=None):
        """创建一个数据库"""
        dimension = dimension or self.embed_model.get_dimension()
        db_id = f"kb_{hashstr(database_name, with_salt=True)}"

        # 创建数据库记录
        db_dict = self.db_manager.create_database(
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
        databases = self.db_manager.get_all_databases()

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
        db_dict = self.db_manager.get_database_by_id(db_id)
        if db_dict is None:
            return None
        else:
            db_copy = db_dict.copy()
            try:
                milvus_info = self.get_collection_info(db_id)
                db_copy.update(milvus_info)
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
        databases = self.db_manager.get_all_databases()
        return [db["db_id"] for db in databases]

    def get_file_info(self, db_id, file_id):
        db = self.db_manager.get_database_by_id(db_id)
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

        return self.db_manager.get_database_by_id(db_id)

    def file_to_chunk(self, files, params=None):
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
                texts = read_text(file)
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

    def url_to_chunk(self, url, params=None):
        """将url转换为分块，读取url的内容，并转换为分块"""
        raise NotImplementedError("Not implemented")

    def add_chunks(self, db_id, file_chunks):
        """添加分块"""
        db = self.get_kb_by_id(db_id)

        if db["embed_model"] != self.embed_model.embed_model_fullname:
            logger.error(f"Embed model not match, {db['embed_model']} != {self.embed_model.embed_model_fullname}")
            return {"message": f"Embed model not match, cur: {self.embed_model.embed_model_fullname}, req: {db['embed_model']}", "status": "failed"}

        for file_id, chunk_info in file_chunks.items():
            # 在数据库中创建文件记录
            self.db_manager.add_file(
                db_id=db_id,
                file_id=file_id,
                filename=chunk_info["filename"],
                path=chunk_info["path"],
                file_type=chunk_info["type"],
                status="processing"
            )

            try:
                self.add_documents(
                    file_id=file_id,
                    collection_name=db_id,
                    docs=[node["text"] for node in chunk_info["nodes"]],
                    chunk_infos=chunk_info["nodes"])

                # 更新文件状态为完成
                self.db_manager.update_file_status(file_id, "done")

            except Exception as e:
                logger.error(f"Failed to add documents to collection {db_id}, {e}, {traceback.format_exc()}")
                # 更新文件状态为失败
                self.db_manager.update_file_status(file_id, "failed")

    def add_files(self, db_id, files, params=None):
        db = self.get_kb_by_id(db_id)

        if not self.check_embed_model(db_id):
            logger.error(f"Embed model not match, {db['embed_model']} != {self.embed_model.embed_model_fullname}")
            return {"message": f"Embed model not match, cur: {self.embed_model.embed_model_fullname}, req: {db['embed_model']}", "status": "failed"}

        # Preprocessing the files to the queue
        new_files = self.file_to_chunk(files, params=params)

        for file_id, new_file in new_files.items():
            # 在数据库中创建文件记录
            self.db_manager.add_file(
                db_id=db_id,
                file_id=file_id,
                filename=new_file["filename"],
                path=new_file["path"],
                file_type=new_file["type"],
                status="processing"
            )

            try:
                self.add_documents(
                    file_id=file_id,
                    collection_name=db_id,
                    docs=[node["text"] for node in new_file["nodes"]],
                    chunk_infos=new_file["nodes"])

                # 更新文件状态为完成
                self.db_manager.update_file_status(file_id, "done")

            except Exception as e:
                logger.error(f"Failed to add documents to collection {db_id}, {e}, {traceback.format_exc()}")
                # 更新文件状态为失败
                self.db_manager.update_file_status(file_id, "failed")

    def delete_file(self, db_id, file_id):
        # 从Milvus中删除文件的向量
        self.client.delete(collection_name=db_id, filter=f"file_id == '{file_id}'")

        # 从SQLite中删除文件记录
        self.db_manager.delete_file(file_id)

    def delete_database(self, db_id):
        # 从Milvus中删除集合
        self.client.drop_collection(collection_name=db_id)

        # 从SQLite中删除数据库记录
        self.db_manager.delete_database(db_id)

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
            file = self.db_manager.get_file_by_id(res["entity"]["file_id"])
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
        for db in self.db_manager.get_all_databases():
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

    def add_documents(self, docs, collection_name, chunk_infos=None, **kwargs):
        """添加已经分块之后的文本"""
        # 检查 collection 是否存在
        import random
        if not self.client.has_collection(collection_name=collection_name):
            logger.error(f"Collection {collection_name} not found, create it")
            # self.add_collection(collection_name)

        chunk_infos = chunk_infos or [{}] * len(docs)

        vectors = self.embed_model.batch_encode(docs)

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
        db = self.db_manager.get_database_by_id(db_id)
        return db["embed_model"] == self.embed_model.embed_model_fullname

