import os
import json
import time
from utils import hashstr, setup_logger
from core.knowledgebase import KnowledgeBase
from core.filereader import pdfreader, plainreader
from core.graphbase import GraphDatabase

logger = setup_logger("DataBaseManager")


class DataBaseLite:
    def __init__(self, name, description, db_type, **kwargs) -> None:
        self.name = name
        self.description = description
        self.db_type = db_type
        self.db_id = kwargs.get("db_id", hashstr(name))
        self.metaname = kwargs.get("metaname", f"{db_type}_{hashstr(name)}")
        self.metadata = kwargs.get("metaname", {})
        self.files = kwargs.get("files", [])

    def update(self, metadata):
        self.metadata = metadata

    def to_dict(self):
        return {
            "name": self.name,
            "description": self.description,
            "db_type": self.db_type,
            "db_id": self.db_id,
            "metaname": self.metaname,
            "metadata": self.metadata,
            "files": self.files
        }

    def to_json(self):
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def __str__(self):
        return self.to_json()

class DataBaseManager:

    def __init__(self, config=None) -> None:
        self.config = config
        self.database_path = "data/databases.json"
        self.knowledge_base = KnowledgeBase(config)
        self.data = {"databases": [], "graph": {}}

        if self.config.enable_knowledge_graph:
            self.graph_base = GraphDatabase(self.config)
            self.graph_base.start()

        self._load_databases()

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

    def _save_databases(self):
        """将数据库的信息保存到本地的文件里面"""
        with open(self.database_path, "w+") as f:
            json.dump({
                "databases": [db.to_dict() for db in self.data["databases"]],
                "graph": self.data["graph"]
            }, f, ensure_ascii=False, indent=4)

    def get_databases(self):

        knowledge_base_collections = self.knowledge_base.get_collection_names()
        if len(self.data["databases"]) != len(knowledge_base_collections):
            logger.warning(f"Database number not match, {knowledge_base_collections}")

        for db in self.data["databases"]:
            db.update(self.knowledge_base.get_collection_info(db.metaname))

        return {"databases": [db.to_dict() for db in self.data["databases"]]}

    def get_graph(self):
        if self.config.enable_knowledge_graph:
            self.data["graph"].update(self.graph_base.get_database_info("neo4j"))
            return {"graph": self.data["graph"]}
        else:
            return {"graph": {}, "message": "Graph database is not enabled"}

    def create_database(self, database_name, description, db_type):
        new_database = DataBaseLite(database_name, description, db_type)

        self.knowledge_base.add_collection(new_database.metaname)
        self.data["databases"].append(new_database)
        self._save_databases()
        return self.get_databases()

    def add_files(self, db_id, files):
        db = self.get_kb_by_id(db_id)
        new_files = []
        for file in files:
            # filenames = [f["filename"] for f in db.files]
            # if os.path.basename(file) in filenames:
            #     continue
            db.files.append({
                "file_id": "file_" + hashstr(file + str(time.time())),
                "filename": os.path.basename(file),
                "path": file,
                "type": file.split(".")[-1],
                "status": "waiting",
                "created_at": time.time()
            })
            new_files.append((len(db.files) - 1, file))

        for idx, file in new_files:
            db.files[idx]["status"] = "processing"

            text = self.read_text(file)
            chunks = self.chunking(text)

            try:
                self.knowledge_base.add_documents(
                    docs=chunks,
                    collection_name=db.metaname,
                    file_id=db.files[idx]["file_id"])
                db.files[idx]["status"] = "done"
            except Exception as e:
                logger.error(f"Failed to add documents to collection {db.metaname}, {e}")
                db.files[idx]["status"] = "failed"

            self._save_databases()

    def get_database_info(self, db_id):
        db = self.get_kb_by_id(db_id)
        if db is None:
            return None
        else:
            db.update(self.knowledge_base.get_collection_info(db.metaname))
            return db.to_dict()

    def read_text(self, file):
        support_format = [".pdf", ".txt", "*.md"]
        assert os.path.exists(file), "File not found"
        logger.info(f"Try to read file {file}")
        if os.path.isfile(file):
            if file.endswith(".pdf"):
                return pdfreader(file)
            elif file.endswith(".txt") or file.endswith(".md"):
                return plainreader(file)
            else:
                logger.error(f"File format not supported, only support {support_format}")
                raise Exception(f"File format not supported, only support {support_format}")
        else:
            logger.error(f"Directory not supported now!")
            raise NotImplementedError("Directory not supported now!")

    def delete_file(self, db_id, file_id):
        db = self.get_kb_by_id(db_id)
        file_idx_to_delete = [idx for idx, f in enumerate(db.files) if f["file_id"] == file_id][0]

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
            output_fields=["id", "text", "file_id", "hash"]
        )
        return {"lines": lines}

    def chunking(self, text, chunk_size=1024):
        """将文本切分成固定大小的块"""
        chunks = []
        for i in range(0, len(text), chunk_size):
            chunks.append(text[i:i + chunk_size])
        return chunks

    def get_kb_by_id(self, db_id):
        for db in self.data["databases"]:
            if db.db_id == db_id:
                return db