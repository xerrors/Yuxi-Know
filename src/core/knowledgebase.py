import os
import json
import time
import traceback

from pymilvus import MilvusClient, MilvusException

from src import config
from src.utils import logger, hashstr
from src.core.indexing import chunk, read_text



class KnowledgeBase:

    def __init__(self) -> None:
        self.data = []
        self.client = None
        self.database_path = os.path.join(config.save_dir, "data", "database.json")
        self._load_models()
        self._load_databases()

    def _load_models(self):
        """所有需要重启的模型"""
        if not config.enable_knowledge_base:
            return

        from src.models.embedding import get_embedding_model
        self.embed_model = get_embedding_model(config)

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

        self.add_collection(db.db_id, dimension)
        self.data.append(db)
        self._save_databases()

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
        return next((db for db in self.data if db.db_id == db_id), None)

    def add_files(self, db_id, files, params=None):
        db = self.get_kb_by_id(db_id)

        if db.embed_model != config.embed_model:
            logger.error(f"Embed model not match, {db.embed_model} != {config.embed_model}")
            return {"message": f"Embed model not match, cur: {config.embed_model}", "status": "failed"}

        # Preprocessing the files to the queue
        new_files = {}
        for file in files:
            file_id = "file_" + hashstr(file + str(time.time()))
            new_file = {
                "file_id": file_id,
                "filename": os.path.basename(file),
                "path": file,
                "type": file.split(".")[-1].lower(),
                "status": "waiting",
                "created_at": time.time()
            }
            new_files[file_id] = new_file

        db.files.update(new_files)  # 更新数据库状态

        # 先保存一次数据库状态，确保waiting状态被记录
        self._save_databases()

        for file_id, new_file in new_files.items():
            db.files[file_id]["status"] = "processing"
            # 更新处理状态
            self._save_databases()

            try:
                if new_file["type"] == "pdf":
                    texts = read_text(new_file["path"])
                    nodes = chunk(texts, params=params)
                else:
                    nodes = chunk(new_file["path"], params=params)

                self.add_documents(
                    file_id=file_id,
                    collection_name=db.db_id,
                    docs=[node.text for node in nodes],
                    chunk_infos=[node.dict() for node in nodes])

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
        self._save_databases()
        return {"message": "删除成功"}

    def restart(self):
        self.embed_model = get_embedding_model(config)
        self._load_databases()

    ################################
    # Below is the code for milvus #
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