import os
import json
import time
import traceback
import shutil

from pymilvus import MilvusClient, MilvusException

from src import config
from src.utils import logger, hashstr
from src.core.indexing import chunk, read_text



class KnowledgeBase:

    def __init__(self) -> None:
        self.data = []
        self.client = None
        self.work_dir = os.path.join(config.save_dir, "data")
        self.database_path = os.path.join(self.work_dir, "database.json")

        # Configuration
        self.default_distance_threshold = 0.5
        self.default_rerank_threshold = 0.1
        self.default_max_query_count = 20

        self._load_models()
        self._load_databases()

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

    def _load_databases(self):
        """将数据库的信息保存到本地的文件里面"""
        if not os.path.exists(self.database_path):
            return

        with open(self.database_path, "r") as f:
            data = json.load(f)
            self.data = [DataBaseLite(**db) for db in data["databases"]]

        self._update_database()

    def _save_databases(self):
        """将数据库的信息保存到本地的文件里面"""
        self._update_database()
        os.makedirs(os.path.dirname(self.database_path), exist_ok=True)
        with open(self.database_path, "w") as f:
            json.dump({
                "databases": [db.to_dict() for db in self.data],
            }, f, ensure_ascii=False, indent=4)

    def _update_database(self):
        self.id2db = {db.db_id: db for db in self.data}
        self.name2db = {db.name: db for db in self.data}

    def create_database(self, database_name, description, dimension=None):
        """创建一个数据库"""
        dimension = dimension or self.embed_model.get_dimension()
        db = DataBaseLite(database_name,
                          description,
                          embed_model=self.embed_model.embed_model_fullname,
                          dimension=dimension)

        # 创建数据库对应的文件夹
        self._ensure_db_folders(db.db_id)

        self.add_collection(db.db_id, dimension)
        self.data.append(db)
        self._save_databases()

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

        for db in self.data:
            db.update(self.get_collection_info(db.db_id))
            processing_files = [f for fid, f in db.files.items() if f["status"] in ["processing", "waiting"]]
            if processing_files:
                logger.info(f"数据库 {db.name} 有 {len(processing_files)} 个文件正在处理中")

        self._save_databases()
        return {"databases": [db.to_dict() for db in self.data]}

    def get_database_info(self, db_id):
        db = self.get_kb_by_id(db_id)
        if db is None:
            return None
        else:
            db.update(self.get_collection_info(db.db_id))
            return db.to_dict()

    def get_database_id(self):
        return [db.db_id for db in self.data]

    def get_file_info(self, db_id, file_id):
        db = self.get_kb_by_id(db_id)
        if db is None:
            raise Exception(f"database not found, {db_id}")

        lines = self.client.query(
            collection_name=db.db_id,
            filter=f"file_id == '{file_id}'",
            output_fields=None
        )
        # 删除 vector 字段
        for line in lines:
            line.pop("vector")

        lines.sort(key=lambda x: x.get("start_char_idx") or 0)
        # logger.debug(f"lines[0]: {lines[0]}")
        return {"lines": lines}

    def get_kb_by_id(self, db_id):
        if not config.enable_knowledge_base:
            return None

        return next((db for db in self.data if db.db_id == db_id), None)

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

        if db.embed_model != config.embed_model:
            logger.error(f"Embed model not match, {db.embed_model} != {config.embed_model}")
            return {"message": f"Embed model not match, cur: {config.embed_model}, req: {db.embed_model}", "status": "failed"}

        db.files.update(file_chunks)
        self._save_databases()

        for file_id, chunk in file_chunks.items():
            db.files[file_id]["status"] = "processing"
            self._save_databases()

            try:
                self.add_documents(
                    file_id=file_id,
                    collection_name=db.db_id,
                    docs=[node["text"] for node in chunk["nodes"]],
                    chunk_infos=chunk["nodes"])

                db.files[file_id]["status"] = "done"

            except Exception as e:
                logger.error(f"Failed to add documents to collection {db.db_id}, {e}, {traceback.format_exc()}")
                db.files[file_id]["status"] = "failed"

            self._save_databases()

    def add_files(self, db_id, files, params=None):
        db = self.get_kb_by_id(db_id)

        if db.embed_model != config.embed_model:
            logger.error(f"Embed model not match, {db.embed_model} != {config.embed_model}")
            return {"message": f"Embed model not match, cur: {config.embed_model}, req: {db.embed_model}", "status": "failed"}

        # Preprocessing the files to the queue
        new_files = self.file_to_chunk(files, params=params)
        db.files.update(new_files)  # 更新数据库状态

        # 先保存一次数据库状态，确保waiting状态被记录
        self._save_databases()

        for file_id, new_file in new_files.items():
            db.files[file_id]["status"] = "processing"
            # 更新处理状态
            self._save_databases()

            try:
                self.add_documents(
                    file_id=file_id,
                    collection_name=db.db_id,
                    docs=[node["text"] for node in new_file["nodes"]],
                    chunk_infos=new_file["nodes"])

                db.files[file_id]["status"] = "done"

            except Exception as e:
                logger.error(f"Failed to add documents to collection {db.db_id}, {e}, {traceback.format_exc()}")
                db.files[file_id]["status"] = "failed"

            # 每个文件处理完成后立即保存数据库状态
            self._save_databases()

    def delete_file(self, db_id, file_id):
        db = self.get_kb_by_id(db_id)
        if db is None:
            raise Exception(f"database not found, {db_id}")

        self.client.delete(collection_name=db.db_id, filter=f"file_id == '{file_id}'")
        del db.files[file_id]
        self._save_databases()

    def delete_database(self, db_id):
        db = self.get_kb_by_id(db_id)
        if db is None:
            raise Exception(f"database not found, {db_id}")

        self.client.drop_collection(collection_name=db.db_id)
        self.data.remove(db)
        # 删除数据库对应的文件夹
        db_folder = os.path.join(self.work_dir, db.db_id)
        if os.path.exists(db_folder):
            shutil.rmtree(db_folder)
        self._save_databases()
        return {"message": "删除成功"}

    def restart(self):
        self._load_models()
        self._load_databases()

    ###################################
    #* Below is the code for retriever #
    ###################################

    def query(self, query, db_id, **kwargs):
        db = self.get_kb_by_id(db_id)

        distance_threshold = kwargs.get("distance_threshold", self.default_distance_threshold)
        rerank_threshold = kwargs.get("rerank_threshold", self.default_rerank_threshold)
        max_query_count = kwargs.get("max_query_count", self.default_max_query_count)

        all_db_result = self.search(query, db_id, limit=max_query_count)
        for res in all_db_result:
            res["file"] = db.files[res["entity"]["file_id"]]

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

    def get_retriever(self, db_id):
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
            logger.error(f"Failed to connect to Milvus: {e}")
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
        collection = self.client.describe_collection(collection_name)
        collection.update(self.client.get_collection_stats(collection_name))
        # collection["id"] = hashstr(collection_name)
        return collection

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


class DataBaseLite:
    def __init__(self, name, description, dimension=None, **kwargs) -> None:
        self.name = name
        self.description = description
        self.dimension = dimension
        self.metadata = kwargs.get("metadata", {})
        # logger.debug(f"DataBaseLite init: {self.metadata}")
        self.db_id = self.metadata.get("collection_name", kwargs.get("db_id"))  # metaname 的历史遗留问题
        self.db_id = self.db_id or f"kb_{hashstr(name, with_salt=True)}"
        self.files = kwargs.get("files", [])

        if isinstance(self.files, list):
            self.files = {f["file_id"]: f for f in self.files}

        self.embed_model = kwargs.get("embed_model", None)

    def id2file(self, file_id):
        for f in self.files:
            if f["file_id"] == file_id:
                return f
        return None

    def update(self, metadata):
        self.metadata = metadata

    def to_dict(self):
        return {
            "name": self.name,
            "description": self.description,
            "db_id": self.db_id,
            "embed_model": self.embed_model,
            "metadata": self.metadata,
            "files": self.files,
            "dimension": self.dimension
        }

    def to_json(self):
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def __str__(self):
        return self.to_json()