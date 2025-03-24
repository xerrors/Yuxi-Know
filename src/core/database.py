import os
import json
import time
from src.utils import hashstr, logger
from src.core.indexing import chunk
from src.models.embedding import get_embedding_model


class DataBaseManager:

    def __init__(self, config=None) -> None:
        self.config = config
        self.database_path = os.path.join(config.save_dir, "data", "database.json")
        self.embed_model = get_embedding_model(config)

        if self.config.enable_knowledge_base:
            from src.core.knowledgebase import KnowledgeBase
            self.knowledge_base = KnowledgeBase(config, self.embed_model)
            if self.config.enable_knowledge_graph:
                from src.core.graphbase import GraphDatabase
                self.graph_base = GraphDatabase(self.config, self.embed_model)
            else:
                self.graph_base = None

        self.data = {"databases": [], "graph": {}}

        self._load_databases()
        self._update_database()

    def _load_databases(self):
        """将数据库的信息保存到本地的文件里面"""
        if not os.path.exists(self.database_path):
            return

        with open(self.database_path, "r") as f:
            data = json.load(f)
            self.data = {
                "databases": [DataBaseLite(**db) for db in data["databases"]],
                "graph": data["graph"]
            }

        # 检查所有文件，如果出现状态是 processing 的，那么设置为 failed
        for db in self.data["databases"]:
            for file in db.files:
                if file["status"] == "processing" or file["status"] == "waiting":
                    file["status"] = "failed"

    def _save_databases(self):
        """将数据库的信息保存到本地的文件里面"""
        self._update_database()
        os.makedirs(os.path.dirname(self.database_path), exist_ok=True)
        with open(self.database_path, "w+") as f:
            json.dump({
                "databases": [db.to_dict() for db in self.data["databases"]],
                "graph": self.data["graph"]
            }, f, ensure_ascii=False, indent=4)

    def _update_database(self):
        self.id2db = {db.db_id: db for db in self.data["databases"]}
        self.name2db = {db.name: db for db in self.data["databases"]}
        self.metaname2db = {db.metaname: db for db in self.data["databases"]}

    def get_databases(self):
        self._update_database()
        assert self.config.enable_knowledge_base, "知识库未启用"
        knowledge_base_collections = self.knowledge_base.get_collection_names()
        if len(self.data["databases"]) != len(knowledge_base_collections):
            logger.warning(
                f"Database number not match, {knowledge_base_collections}, "
                f"self.data['databases']: {self.get_db_metanames()}, ")

        # 更新每个数据库的状态信息
        for db in self.data["databases"]:
            # 获取最新的集合信息
            db.update(self.knowledge_base.get_collection_info(db.metaname))

            # 检查文件处理状态
            processing_files = [f for f in db.files if f["status"] in ["processing", "waiting"]]
            if processing_files:
                logger.info(f"数据库 {db.name} 有 {len(processing_files)} 个文件正在处理中")

        return {"databases": [db.to_dict() for db in self.data["databases"]]}

    def get_graph(self):
        if self.config.enable_knowledge_graph:
            self.data["graph"].update(self.graph_base.get_database_info("neo4j"))
            return {"graph": self.data["graph"]}
        else:
            return {"message": "Graph base not enabled", "graph": {}}

    def is_graph_running(self):
        """检查图数据库是否正在运行

        Returns:
            bool: 图数据库是否正在运行
        """
        # 检查是否启用了图数据库
        if not self.config.enable_knowledge_graph or not hasattr(self, 'graph_base') or self.graph_base is None:
            return False

        # 获取图数据库信息，检查状态
        graph_info = self.graph_base.get_database_info("neo4j")
        return graph_info.get("status") == "open"

    def create_database(self, database_name, description, db_type, dimension):
        from src.config import EMBED_MODEL_INFO
        dimension = dimension or EMBED_MODEL_INFO[self.config.embed_model]["dimension"]

        new_database = DataBaseLite(database_name,
                                    description,
                                    db_type,
                                    embed_model=self.config.embed_model,
                                    dimension=dimension)

        self.knowledge_base.add_collection(new_database.metaname, dimension)
        self.data["databases"].append(new_database)
        self._save_databases()
        return self.get_databases()

    def add_files(self, db_id, files, params=None):
        db = self.get_kb_by_id(db_id)

        if db.embed_model != self.config.embed_model:
            logger.error(f"Embed model not match, {db.embed_model} != {self.config.embed_model}")
            return {"message": f"Embed model not match, cur: {self.config.embed_model}", "status": "failed"}

        # Preprocessing the files to the queue
        new_files = []
        for file in files:
            new_file = {
                "file_id": "file_" + hashstr(file + str(time.time())),
                "filename": os.path.basename(file),
                "path": file,
                "type": file.split(".")[-1].lower(),
                "status": "waiting",
                "created_at": time.time()
            }
            db.files.append(new_file)
            new_files.append(new_file)

        # 先保存一次数据库状态，确保waiting状态被记录
        self._save_databases()

        for new_file in new_files:
            file_id = new_file["file_id"]
            idx = self.get_idx_by_fileid(db, file_id)
            db.files[idx]["status"] = "processing"
            # 更新处理状态
            self._save_databases()

            try:
                if new_file["type"] == "pdf":
                    texts = self.read_text(new_file["path"])
                    nodes = chunk(texts, params=params)
                else:
                    nodes = chunk(new_file["path"], params=params)

                self.knowledge_base.add_documents(
                    file_id=file_id,
                    collection_name=db.metaname,
                    docs=[node.text for node in nodes],
                    chunk_infos=[node.dict() for node in nodes])

                idx = self.get_idx_by_fileid(db, file_id)
                db.files[idx]["status"] = "done"

            except Exception as e:
                logger.error(f"Failed to add documents to collection {db.metaname}, {e}")
                idx = self.get_idx_by_fileid(db, file_id)
                db.files[idx]["status"] = "failed"

            # 每个文件处理完成后立即保存数据库状态
            self._save_databases()


    def get_database_info(self, db_id):
        db = self.get_kb_by_id(db_id)
        if db is None:
            return None
        else:
            db.update(self.knowledge_base.get_collection_info(db.metaname))
            return db.to_dict()

    def read_text(self, file, params=None):
        support_format = [".pdf", ".txt", ".md"]
        assert os.path.exists(file), "File not found"
        logger.info(f"Try to read file {file}")

        if not os.path.isfile(file):
            logger.error(f"Directory not supported now!")
            raise NotImplementedError("Directory not supported now!")

        if file.endswith(".pdf"):
            from src.plugins import ocr
            return ocr.process_pdf(file)

        elif file.endswith(".txt") or file.endswith(".md"):
            from src.core.filereader import plainreader
            return plainreader(file)

        else:
            logger.error(f"File format not supported, only support {support_format}")
            raise Exception(f"File format not supported, only support {support_format}")

    def delete_file(self, db_id, file_id):
        db = self.get_kb_by_id(db_id)
        file_idx_to_delete = self.get_idx_by_fileid(db, file_id)

        self.knowledge_base.client.delete(
            collection_name=db.metaname,
            filter=f"file_id == '{file_id}'"),

        del db.files[file_idx_to_delete]
        self._save_databases()

    def get_file_info(self, db_id, file_id):
        db = self.get_kb_by_id(db_id)
        if db is None:
            return {"message": "database not found"}, 404
        lines = self.knowledge_base.client.query(
            collection_name=db.metaname,
            filter=f"file_id == '{file_id}'",
            output_fields=None
        )
        # 删除 vector 字段
        for line in lines:
            line.pop("vector")

        lines.sort(key=lambda x: x.get("start_char_idx", 0))
        # logger.debug(f"lines[0]: {lines[0]}")
        return {"lines": lines}

    def get_db_metanames(self):
        return [db.metaname for db in self.data["databases"]]

    def delete_database(self, db_id):
        db = self.get_kb_by_id(db_id)
        if db is None:
            return {"message": "database not found"}, 404

        self.knowledge_base.client.drop_collection(db.metaname)
        self.data["databases"] = [d for d in self.data["databases"] if d.db_id != db_id]
        self._save_databases()
        return {"message": "删除成功"}

    def get_kb_by_id(self, db_id):
        for db in self.data["databases"]:
            if db.db_id == db_id:
                return db
        return None

    def get_idx_by_fileid(self, db, file_id):
        for idx, f in enumerate(db.files):
            if f["file_id"] == file_id:
                return idx


class DataBaseLite:
    def __init__(self, name, description, db_type, dimension=None, **kwargs) -> None:
        self.name = name
        self.description = description
        self.db_type = db_type
        self.dimension = dimension
        self.db_id = kwargs.get("db_id", hashstr(name))
        self.metaname = kwargs.get("metaname", f"{db_type[:1]}{hashstr(name)}")
        self.metadata = kwargs.get("metadata", {})
        self.files = kwargs.get("files", [])
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
            "db_type": self.db_type,
            "db_id": self.db_id,
            "embed_model": self.embed_model,
            "metaname": self.metaname,
            "metadata": self.metadata,
            "files": self.files,
            "dimension": self.dimension
        }

    def to_json(self):
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def __str__(self):
        return self.to_json()