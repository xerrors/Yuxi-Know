import os
import json
import time
import traceback
import shutil
from sqlalchemy.orm import joinedload
from pathlib import Path
import asyncio
import random
from functools import lru_cache
from diskcache import Cache

from pymilvus import MilvusClient, MilvusException

from src import config
from src.utils import logger, hashstr
from src.core.indexing import chunk_with_parser, chunk_text, parse_pdf_async
from server.db_manager import db_manager
from server.models.kb_models import KnowledgeDatabase, KnowledgeFile, KnowledgeNode
from src.utils.db_migration import migrate_knowledge_db

class KnowledgeBase:

    def __init__(self) -> None:
        self.client = None
        self.work_dir = os.path.join(config.save_dir, "data")
        self.cache_dir = os.path.join(self.work_dir, ".cache")
        os.makedirs(self.cache_dir, exist_ok=True)

        # 初始化磁盘缓存
        self.disk_cache = Cache(self.cache_dir)

        # 配置缓存过期时间（秒）
        self.cache_ttl = 300  # 5分钟

        # Configuration
        self.default_distance_threshold = 0.5
        self.default_rerank_threshold = 0.1
        self.default_max_query_count = 20

        # 检查是否需要从JSON文件迁移到SQLite
        self._check_migration()

        self._load_models()

        # 检查所有 waiting 状态的文件并标记为 failed
        self._mark_waiting_files_as_failed()

    def _to_dict_safely(self, obj):
        """安全地将对象转换为字典，避免延迟加载问题"""
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        # For SQLAlchemy models not having a to_dict, or to customize
        if isinstance(obj, KnowledgeDatabase | KnowledgeFile | KnowledgeNode):
            # Basic serialization, customize as needed
            d = obj.__dict__.copy()
            d.pop('_sa_instance_state', None)
            # Convert datetime objects to string or timestamp if necessary
            for k, v in d.items():
                if isinstance(v, time.struct_time) or hasattr(v, 'isoformat'): # crude datetime check
                    d[k] = time.mktime(v.timetuple()) if isinstance(v, time.struct_time) else v.isoformat()
            return d
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
        self.embed_model = get_embedding_model()

        if config.enable_reranker:
            from src.models.rerank_model import get_reranker
            self.reranker = get_reranker()

        connected = self.connect_to_milvus()
        assert connected, ConnectionError("Failed to connect to Milvus")

    # 知识库数据库操作方法
    def get_all_databases(self):
        """获取所有知识库"""
        with db_manager.get_session_context() as session:
            databases = session.query(KnowledgeDatabase).options(
                joinedload(KnowledgeDatabase.files)
            ).all()
            return [db.to_dict() for db in databases] # Assuming to_dict handles files correctly

    def get_database_by_id(self, db_id):
        """根据ID获取知识库"""
        with db_manager.get_session_context() as session:
            db = session.query(KnowledgeDatabase).options().filter_by(db_id=db_id).first()
            return db.to_dict(with_nodes=False) if db else None # Assuming to_dict handles files and nodes

    def create_database_record(self, db_id, name, description, embed_model=None, dimension=None, metadata=None):
        """在数据库中创建知识库记录"""
        with db_manager.get_session_context() as session:
            db = KnowledgeDatabase(
                db_id=db_id,
                name=name,
                description=description,
                embed_model=embed_model,
                dimension=dimension,
                meta_info=metadata or {}
            )
            session.add(db)
            session.flush()
            db_dict = db.to_dict() # Use the model's to_dict
            return db_dict

    def delete_database_record(self, db_id):
        """从数据库中删除知识库记录"""
        with db_manager.get_session_context() as session:
            db = session.query(KnowledgeDatabase).filter_by(db_id=db_id).first()
            if db:
                # Manually delete associated files and nodes if cascade is not set up or to be sure
                files = session.query(KnowledgeFile).filter_by(database_id=db_id).all()
                for file_obj in files:
                    session.query(KnowledgeNode).filter_by(file_id=file_obj.file_id).delete()
                    session.delete(file_obj)
                session.delete(db)
                return True
            return False

    def update_database_record(self, db_id, name, description):
        """更新数据库中的知识库记录"""
        with db_manager.get_session_context() as session:
            db = session.query(KnowledgeDatabase).filter_by(db_id=db_id).first()
            if not db:
                raise ValueError(f"数据库 {db_id} 不存在")
            db.name = name
            db.description = description
            session.commit()
            return db.to_dict()

    def add_file_record(self, db_id, file_id, filename, path, file_type, status="waiting"):
        """在数据库中添加文件记录"""
        with db_manager.get_session_context() as session:
            file_obj = KnowledgeFile(
                file_id=file_id,
                database_id=db_id,
                filename=filename,
                path=path,
                file_type=file_type,
                status=status
            )
            session.add(file_obj)
            session.flush()
            return file_obj.to_dict()

    def update_file_status(self, file_id, status):
        """更新文件状态"""
        with db_manager.get_session_context() as session:
            file_obj = session.query(KnowledgeFile).filter_by(file_id=file_id).first()
            if file_obj:
                file_obj.status = status
                session.commit()
                return True
            return False

    def delete_file_record(self, file_id):
        """从数据库中删除文件记录及其关联的节点"""
        with db_manager.get_session_context() as session:
            # First, delete associated nodes
            session.query(KnowledgeNode).filter_by(file_id=file_id).delete()
            # Then, delete the file
            file_obj = session.query(KnowledgeFile).filter_by(file_id=file_id).first()
            if file_obj:
                session.delete(file_obj)
                return True
            return False

    def get_files_by_database(self, db_id):
        """获取知识库下的所有文件"""
        with db_manager.get_session_context() as session:
            files = session.query(KnowledgeFile).options(
                joinedload(KnowledgeFile.nodes) # Eager load nodes
            ).filter_by(database_id=db_id).all()
            return [f.to_dict() for f in files]

    def get_file_by_id(self, file_id):
        """根据ID获取文件及其节点"""
        with db_manager.get_session_context() as session:
            file_obj = session.query(KnowledgeFile).options(
                joinedload(KnowledgeFile.nodes) # Eager load nodes
            ).filter_by(file_id=file_id).first()
            return file_obj.to_dict() if file_obj else None

    def add_node(self, file_id, text, hash_value=None, start_char_idx=None, end_char_idx=None, metadata=None):
        """添加知识块 (原始文本节点)"""
        with db_manager.get_session_context() as session:
            node = KnowledgeNode(
                file_id=file_id,
                text=text,
                hash=hash_value or hashstr(text, with_salt=True), # Ensure hash is present
                start_char_idx=start_char_idx,
                end_char_idx=end_char_idx,
                meta_info=metadata or {}
            )
            session.add(node)
            session.flush() # To get node.id
            return node.to_dict()

    def get_nodes_by_file(self, file_id):
        """获取文件下的所有知识块"""
        with db_manager.get_session_context() as session:
            nodes = session.query(KnowledgeNode).filter_by(file_id=file_id).all()
            return [node.to_dict() for node in nodes]

    def get_nodes_by_filter(self, file_id=None, search_text=None, limit=100):
        """根据条件筛选知识块"""
        with db_manager.get_session_context() as session:
            query = session.query(KnowledgeNode)
            if file_id:
                query = query.filter_by(file_id=file_id)
            if search_text:
                query = query.filter(KnowledgeNode.text.like(f"%{search_text}%"))
            nodes = query.limit(limit).all()
            return [node.to_dict() for node in nodes]

    def create_database(self, database_name, description, dimension=None):
        """创建一个数据库（业务逻辑）"""
        dimension = dimension or self.embed_model.get_dimension()
        db_id = f"kb_{hashstr(database_name, with_salt=True)}"
        db_dict = self.create_database_record(
            db_id=db_id,
            name=database_name,
            description=description,
            embed_model=self.embed_model.embed_model_fullname,
            dimension=dimension
        )
        self._ensure_db_folders(db_id)
        self.add_collection(db_id, dimension)
        return db_dict

    def _ensure_db_folders(self, db_id):
        db_folder = os.path.join(self.work_dir, db_id)
        uploads_folder = os.path.join(db_folder, "uploads")
        os.makedirs(db_folder, exist_ok=True)
        os.makedirs(uploads_folder, exist_ok=True)
        return db_folder, uploads_folder

    def get_db_upload_path(self, db_id=None):
        if db_id:
            _, uploads_folder = self._ensure_db_folders(db_id)
            return uploads_folder
        # Fallback for general uploads if db_id is not specified during upload
        general_uploads = os.path.join(self.work_dir, "uploads")
        os.makedirs(general_uploads, exist_ok=True)
        return general_uploads

    def get_databases(self):
        assert config.enable_knowledge_base, "知识库未启用"
        databases = self.get_all_databases()
        databases_with_milvus = []
        for db_data in databases: # db_data is already a dict from to_dict()
            db_copy = db_data.copy()
            try:
                milvus_info = self.get_collection_info(db_copy["db_id"])
                # Merge Milvus info carefully, avoid overwriting existing keys like 'name', 'description'
                for k, v in milvus_info.items():
                    if k not in db_copy or k in ["row_count", "status", "error_message"]: # Milvus specific keys
                        db_copy[k] = v
            except Exception as e:
                logger.warning(f"获取知识库 {db_copy.get('name')} (ID: {db_copy.get('db_id')}) 的Milvus信息失败: {e}")
                db_copy.update({"row_count": 0, "status": "未连接", "error": str(e)})

            # files should be part of db_copy from to_dict()
            db_copy_files = db_copy.get("files", {}).values()
            processing_files_count = sum(1 for file_info in db_copy_files if file_info.get("status") in ["processing", "waiting"])
            if processing_files_count > 0:
                logger.info(f"数据库 {db_copy.get('name')} 有 {processing_files_count} 个文件正在处理中或等待处理")

            databases_with_milvus.append(db_copy)
        return {"databases": databases_with_milvus}

    def get_database_info(self, db_id):
        db_dict = self.get_database_by_id(db_id)
        if db_dict is None:
            return None
        else:
            db_copy = db_dict.copy()
            original_description = db_copy.get("description")
            try:
                milvus_info = self.get_collection_info(db_id)
                db_copy.update(milvus_info)
                if original_description: # Preserve original if Milvus info overwrote it
                    db_copy["description"] = original_description
            except Exception as e:
                logger.warning(f"获取知识库 ID: {db_id} 的Milvus信息失败: {e}")
                db_copy.update({"row_count": 0, "status": "未连接", "error": str(e)})
            return db_copy

    def get_database_id(self):
        databases = self.get_all_databases()
        return [db["db_id"] for db in databases]

    def get_file_info(self, db_id, file_id):
        # This method originally queried Milvus. For raw chunks, we query SQLite.
        # If the intention is to show indexed chunks, this might need adjustment post-indexing.
        # For now, let's assume it's for displaying raw, pre-indexed chunks if file status is 'waiting'.
        file_record = self.get_file_by_id(file_id)
        if not file_record:
            raise Exception(f"File not found: {file_id}")

        # Nodes are already part of file_record from get_file_by_id due to eager loading and to_dict
        nodes = file_record.get("nodes", [])

        if len(nodes) == 0:
            nodes = self.client.query(
                collection_name=db_id,
                filter=f"file_id == '{file_id}'",
                output_fields=None
            )
            for node in nodes:
                node.pop("vector")

        # Sort nodes if necessary, e.g., by start_char_idx or an explicit chunk_idx if available
        nodes.sort(key=lambda x: x.get("start_char_idx") or x.get("metadata", {}).get("chunk_idx", 0))
        return {"lines": nodes} # Return nodes from SQLite for consistency with frontend expectations

    def get_kb_by_id(self, db_id):
        if not config.enable_knowledge_base:
            return None
        return self.get_database_by_id(db_id)

    async def save_files_for_pending_indexing(self, db_id, files_paths, params=None):
        processed_files_info = []
        for file_path_str in files_paths:
            file_path = Path(file_path_str)
            file_id = "file_" + hashstr(str(file_path) + str(time.time()), 6) # Shorter hash
            file_type = file_path.suffix.lower().replace(".", "")

            # Initial file record with status 'waiting'
            file_record = self.add_file_record(
                db_id=db_id,
                file_id=file_id,
                filename=file_path.name,
                path=str(file_path),
                file_type=file_type,
                status="waiting"
            )

            try:
                if file_type == "pdf":
                    texts = await parse_pdf_async(file_path, params=params)
                    raw_nodes = chunk_text(texts, params=params)
                else:
                    raw_nodes = chunk_with_parser(file_path, params=params)

                parsed_nodes_data = [parse_node_data(node) for node in raw_nodes]

                for node_data in parsed_nodes_data:
                    self.add_node(
                        file_id=file_id,
                        text=node_data["text"],
                        hash_value=node_data["hash"],
                        start_char_idx=node_data.get("start_char_idx"),
                        end_char_idx=node_data.get("end_char_idx"),
                        metadata=node_data.get("metadata")
                    )

                self.update_file_status(file_id, "pending_indexing")
                file_record['status'] = "pending_indexing" # Ensure status is up-to-date

            except Exception as e:
                logger.error(f"处理文件 {file_path} 失败，无法保存待索引块: {e}, {traceback.format_exc()}")
                self.update_file_status(file_id, "failed") # Mark file as failed
                file_record['status'] = "failed"

            processed_files_info.append(file_record)
        return processed_files_info

    async def save_urls_for_pending_indexing(self, db_id, urls, params=None):
        try:
            from langchain_community.document_loaders import UnstructuredURLLoader
        except ImportError:
            logger.error("请安装 langchain_community 和 unstructured 包：pip install langchain-community unstructured")
            raise ImportError("Required packages for URL processing are missing.")

        processed_urls_info = []
        for url in urls:
            file_id = "url_" + hashstr(url + str(time.time()), 6) # Shorter hash
            filename = gen_filename_from_url(url)

            file_record = self.add_file_record(
                db_id=db_id,
                file_id=file_id,
                filename=filename,
                path=url,
                file_type="url",
                status="waiting"
            )

            try:
                single_loader = UnstructuredURLLoader(urls=[url], continue_on_failure=False)
                documents = await single_loader.aload()
                text_content = "\n\n".join([doc.page_content for doc in documents])

                raw_nodes = chunk_text(text_content, params=params)
                parsed_nodes_data = [parse_node_data(node) for node in raw_nodes]

                for node_data in parsed_nodes_data:
                    self.add_node(
                        file_id=file_id,
                        text=node_data["text"],
                        hash_value=node_data["hash"],
                        start_char_idx=node_data.get("start_char_idx"),
                        end_char_idx=node_data.get("end_char_idx"),
                        metadata=node_data.get("metadata")
                    )

                self.update_file_status(file_id, "pending_indexing")
                file_record['status'] = "pending_indexing"

            except Exception as e:
                logger.error(f"处理URL {url} 失败，无法保存待索引块: {e}, {traceback.format_exc()}")
                self.update_file_status(file_id, "failed")
                file_record['status'] = "failed"

            processed_urls_info.append(file_record)
        return processed_urls_info

    async def trigger_file_indexing(self, db_id, file_id):
        logger.info(f"开始为文件 {file_id} (数据库: {db_id}) 创建索引")
        if not self.check_embed_model(db_id):
            logger.error(f"文件 {file_id} 索引失败：向量模型不匹配。")
            self.update_file_status(file_id, "failed")
            return {"status": "failed", "message": "向量模型不匹配"}

        try:
            self.update_file_status(file_id, "processing")

            nodes_to_index = self.get_nodes_by_file(file_id)
            if not nodes_to_index:
                logger.warning(f"文件 {file_id} 没有找到需要索引的块。")
                self.update_file_status(file_id, "done") # Or 'failed' if this is an error condition
                return {"status": "success", "message": "没有需要索引的块"}

            docs_text = [node["text"] for node in nodes_to_index]

            logger.info(f"正在为文件 {file_id} 的 {len(docs_text)} 个块生成向量...")
            vectors = await self.embed_model.abatch_encode(docs_text)
            logger.info(f"文件 {file_id} 的向量生成完毕。")

            data_to_insert = []
            for i, node in enumerate(nodes_to_index):
                milvus_entry = {
                    "id": node["id"],  # Using KnowledgeNode.id as Milvus PK
                    "vector": vectors[i],
                    "text": node["text"],
                    "file_id": file_id, # Explicitly ensure file_id is present
                    "hash": node["hash"],
                     # Spread other metadata stored in node["meta_info"]
                    **(node.get("meta_info") if isinstance(node.get("meta_info"), dict) else {})
                }
                # Ensure start_char_idx and end_char_idx are included if they exist directly on node dict
                if "start_char_idx" in node and node["start_char_idx"] is not None:
                    milvus_entry["start_char_idx"] = node["start_char_idx"]
                if "end_char_idx" in node and node["end_char_idx"] is not None:
                    milvus_entry["end_char_idx"] = node["end_char_idx"]

                data_to_insert.append(milvus_entry)

            if data_to_insert:
                logger.info(f"正在将文件 {file_id} 的 {len(data_to_insert)} 个向量插入 Milvus 集合 {db_id}...")
                self.client.insert(collection_name=db_id, data=data_to_insert)
                logger.info(f"文件 {file_id} 的向量成功插入 Milvus。")

            self.update_file_status(file_id, "done")
            logger.info(f"文件 {file_id} 索引成功完成。")
            return {"status": "success", "message": "文件索引成功"}

        except Exception as e:
            logger.error(f"文件 {file_id} 索引过程中发生错误: {e}, {traceback.format_exc()}")
            self.update_file_status(file_id, "pending_indexing")
            return {"status": "failed", "message": f"索引失败: {str(e)}"}


    def delete_file(self, db_id, file_id):
        logger.info(f"Deleting file {file_id} from database {db_id}")
        try:
            # From Milvus
            logger.info(f"Deleting vectors for file_id {file_id} from Milvus collection {db_id}")
            self.client.delete(collection_name=db_id, filter=f"file_id == '{file_id}'")
            logger.info(f"Milvus deletion successful for file_id {file_id}.")
        except Exception as e:
            logger.error(f"Error deleting file {file_id} from Milvus collection {db_id}: {e}")
            # Decide if to proceed with DB deletion or not. For now, we proceed.

        # From SQLite (deletes file and its nodes)
        if self.delete_file_record(file_id):
            logger.info(f"Successfully deleted file record {file_id} and its nodes from SQLite.")
        else:
            logger.warning(f"File record {file_id} not found in SQLite for deletion or already deleted.")


    def delete_database(self, db_id):
        logger.info(f"Deleting database {db_id}")
        try:
            if self.client.has_collection(collection_name=db_id):
                logger.info(f"Dropping Milvus collection {db_id}")
                self.client.drop_collection(collection_name=db_id)
                logger.info(f"Milvus collection {db_id} dropped.")
            else:
                logger.warning(f"Milvus collection {db_id} not found, skipping drop.")
        except Exception as e:
            logger.error(f"Error dropping Milvus collection {db_id}: {e}")
            # Decide if to proceed with DB deletion. For now, we proceed.

        if self.delete_database_record(db_id): # This now also handles deleting files/nodes
            logger.info(f"Successfully deleted database record {db_id} and associated data from SQLite.")
        else:
            logger.warning(f"Database record {db_id} not found in SQLite for deletion.")

        db_folder = os.path.join(self.work_dir, db_id)
        if os.path.exists(db_folder):
            try:
                shutil.rmtree(db_folder)
                logger.info(f"Successfully deleted database folder {db_folder}.")
            except Exception as e:
                logger.error(f"Error deleting database folder {db_folder}: {e}")
        return {"message": "删除成功"}

    def restart(self):
        self._load_models()

    ###################################
    #* Below is the code for retriever #
    ###################################

    def query(self, query_text, db_id, **kwargs): # Renamed 'query' to 'query_text' to avoid clash
        distance_threshold = kwargs.get("distance_threshold", self.default_distance_threshold)
        rerank_threshold = kwargs.get("rerank_threshold", self.default_rerank_threshold)
        max_query_count = kwargs.get("max_query_count", self.default_max_query_count)

        all_db_result = self.search(query_text, db_id, limit=max_query_count) # Use query_text
        all_db_result_dicts = []
        for res_item in all_db_result: # res is a list of SearchResult objects
            # 将 Milvus SearchResult 对象转换为字典
            item_dict = {
                "id": res_item.id,
                "distance": res_item.distance,
                "entity": {}
            }
            # 安全地获取实体字段
            if hasattr(res_item, "entity"):
                entity_data = res_item.entity
                if isinstance(entity_data, dict):
                    item_dict["entity"] = entity_data.copy()
                else:
                    # 如果 entity 不是字典，尝试获取常见字段
                    for field in ["text", "file_id", "hash", "start_char_idx", "end_char_idx"]:
                        try:
                            item_dict["entity"][field] = getattr(entity_data, field, None)
                        except Exception:
                            continue

            all_db_result_dicts.append(item_dict)

        for res_dict in all_db_result_dicts:
            if res_dict.get("entity") and res_dict["entity"].get("file_id"):
                file_info = self.get_file_by_id(res_dict["entity"]["file_id"]) # get_file_by_id returns a dict
                if file_info:
                    # Add selective file info to avoid circular references or overly large objects
                    res_dict["file"] = {
                        "file_id": file_info.get("file_id"),
                        "filename": file_info.get("filename"),
                        "type": file_info.get("file_type")
                    }
            else:
                 logger.warning(f"Missing entity or file_id in Milvus result: {res_dict}")

        db_result_filtered = [r for r in all_db_result_dicts if r["distance"] > distance_threshold]

        if config.enable_reranker and len(db_result_filtered) > 0 and self.reranker:
            texts_for_rerank = [r["entity"]["text"] for r in db_result_filtered if r.get("entity") and r["entity"].get("text")]
            if texts_for_rerank: # Ensure there are texts to rerank
                rerank_scores = self.reranker.compute_score([query_text, texts_for_rerank], normalize=False) # Use query_text
                for i, r_filtered in enumerate(db_result_filtered):
                    if i < len(rerank_scores): # Check bounds
                         r_filtered["rerank_score"] = rerank_scores[i]
                db_result_filtered.sort(key=lambda x: x.get("rerank_score", -1), reverse=True) # Handle missing rerank_score
                db_result_filtered = [_res for _res in db_result_filtered if _res.get("rerank_score", -1) > rerank_threshold]

        if kwargs.get("top_k", None):
            db_result_filtered = db_result_filtered[:kwargs["top_k"]]

        return {
            "results": db_result_filtered,
            "all_results": all_db_result_dicts, # Return the full list before filtering for analysis
        }

    def get_retriever_by_db_id(self, db_id):
        retriever_params = {
            "distance_threshold": self.default_distance_threshold,
            "rerank_threshold": self.default_rerank_threshold,
            "max_query_count": self.default_max_query_count,
            "top_k": 10,
        }

        def retriever(query_text): # Renamed query to query_text
            """
            retriever_params: 检索参数
            query_text: 查询文本
            """
            response = self.query(query_text, db_id, **retriever_params) # Use query_text
            return response["results"]

        return retriever

    def get_retrievers(self):
        retrievers = {}
        all_dbs = self.get_all_databases() # Returns list of dicts
        for db_data in all_dbs:
            if self.check_embed_model(db_data["db_id"]):
                retrievers[db_data["db_id"]] = {
                    "name": db_data["name"],
                    "description": db_data["description"],
                    "retriever": self.get_retriever_by_db_id(db_data["db_id"]),
                    "embed_model": db_data["embed_model"],
                }
            else:
                logger.warning(
                    f"无法将知识库 {db_data['name']} 转换为 Tools, 因为向量模型不匹配，"
                    f"当前向量模型: {self.embed_model.embed_model_fullname}，"
                    f"知识库向量模型: {db_data['embed_model']}。"
                )
        return retrievers

    ################################
    #* Below is the code for milvus #
    ################################
    def connect_to_milvus(self):
        connected = False
        try:
            uri = os.getenv('MILVUS_URI', config.get('milvus_uri', "http://milvus:19530"))
            self.client = MilvusClient(uri=uri)
            self.client.list_collections() # Test connection
            logger.info(f"Successfully connected to Milvus at {uri}")
            connected = True
        except MilvusException as e:
            logger.error(f"Failed to connect to Milvus: {e} with {uri}。{traceback.format_exc()}")
            logger.error("请检查 milvus 的容器是否正常运行，如果已退出，请重新启动 `docker restart milvus`。")
        except Exception as e: # Catch other potential errors like requests.exceptions.ConnectionError
            logger.error(f"An unexpected error occurred while connecting to Milvus at {uri}: {e}, {traceback.format_exc()}")

        return connected

    def get_collection_names(self):
        return self.client.list_collections()

    def get_collections(self):
        collections_name = self.client.list_collections()
        collections = []
        for collection_name in collections_name:
            collection_info = self.get_collection_info(collection_name)
            collections.append(collection_info)
        return collections

    def get_collection_info(self, collection_name):
        try:
            collection_desc = self.client.describe_collection(collection_name)
            collection_stats = self.client.get_collection_stats(collection_name)
            # Combine description and stats
            # Ensure all keys from description are present, then update/add stats
            # Milvus describe_collection returns a dict like:
            # {'collection_name': ..., 'description': ..., 'fields': [...], ...}
            # Milvus get_collection_stats returns a dict like: {'row_count': ...}
            combined_info = collection_desc.copy() # Start with description
            combined_info.update(collection_stats) # Add/overwrite with stats
            return combined_info
        except MilvusException as e:
            logger.warning(f"获取集合 {collection_name} 信息失败: {e}")
            return {"name": collection_name, "row_count": 0, "status": "错误", "error_message": str(e)}

    def add_collection(self, collection_name, dimension=None):
        if self.client.has_collection(collection_name=collection_name):
            logger.warning(f"Collection {collection_name} already exists. It will be used as is or needs manual deletion if schema change is required.")
            # Not dropping by default to avoid data loss.
            # self.client.drop_collection(collection_name=collection_name)
            # self.client.create_collection(collection_name=collection_name, dimension=dimension)
            return

        self.client.create_collection(
            collection_name=collection_name,
            dimension=dimension or self.embed_model.get_dimension(),
            # Define primary key field, default is 'id' of type Int64.
            # If using KnowledgeNode.id (which is int), this is fine.
            # Example for explicit PK:
            # primary_field_name="node_id",
            # id_type="Int64"
            # Ensure vector field is also defined if not using defaults.
        )
        logger.info(f"Milvus collection {collection_name} created with dimension {dimension or self.embed_model.get_dimension()}.")




    def search(self, query_text, collection_name, limit=3): # Renamed query to query_text
        query_vectors = self.embed_model.batch_encode([query_text]) # Use query_text
        return self.search_by_vector(query_vectors[0], collection_name, limit)

    def search_by_vector(self, vector, collection_name, limit=3):

        res = self.client.search(
            collection_name=collection_name,
            data=[vector],
            limit=limit,
            output_fields=["text", "file_id"],
        )
        # res is a list of SearchResult lists. For a single query vector, it's res[0].
        return res[0] if res else []


    def examples(self, collection_name, limit=20):
        res = self.client.query(
            collection_name=collection_name,
            limit=limit, # Milvus query limit is different from search limit
            output_fields=["id", "text"],
        )
        # res is a list of dicts directly
        return res

    def search_by_id(self, collection_name, entity_id, output_fields=["id", "text"]):
        res = self.client.get(collection_name, entity_id, output_fields=output_fields)
        return res


    def check_embed_model(self, db_id):
        db = self.get_database_by_id(db_id)
        return db.get("embed_model") == self.embed_model.embed_model_fullname

    def update_database(self, db_id, name, description):
        db = self.get_database_by_id(db_id)
        if db is None:
            raise Exception(f"数据库不存在: {db_id}")
        updated_db = self.update_database_record(db_id, name, description)
        return updated_db

    def _mark_waiting_files_as_failed(self):
        """将所有 status 为 'waiting' 的文件标记为 'failed'"""
        with db_manager.get_session_context() as session:
            waiting_files = session.query(KnowledgeFile).filter_by(status="waiting").all()
            if waiting_files:
                for file_obj in waiting_files:
                    file_obj.status = "failed"
                session.commit()
                logger.info(f"已将 {len(waiting_files)} 个 waiting 状态的文件标记为 failed")


def parse_node_data(node):
    # Handles both LlamaIndex NodeWithScore and simple dicts/BaseModel instances
    if hasattr(node, 'node'): # Likely LlamaIndex NodeWithScore
        node_obj = node.node
    else:
        node_obj = node

    if hasattr(node_obj, 'model_dump'): # Pydantic BaseModel
        node_data = node_obj.model_dump()
    elif hasattr(node_obj, 'dict'):
        node_data = node_obj.dict()
    elif isinstance(node_obj, dict):
        node_data = node_obj
    else: # Fallback for other types, e.g. Langchain Document
        node_data = {
            "text": getattr(node_obj, 'page_content', str(node_obj)),
            "metadata": getattr(node_obj, 'metadata', {})
        }

    # 获取文本内容
    node_text = node_data.get("text", node_data.get("page_content", "")) # page_content for Langchain docs

    # 清理文本内容
    try:
        # 尝试编码解码来清理无效字符
        cleaned_text = node_text.encode('utf-8', errors='replace').decode('utf-8')
    except (UnicodeError, AttributeError):
        # 如果出现编码错误，使用更激进的清理方法
        cleaned_text = ''.join(char for char in str(node_text) if ord(char) < 0x10000)

    # Extract start_char_idx and end_char_idx from metadata if present (common for LlamaIndex)
    metadata = node_data.get("metadata", {})
    start_char_idx = metadata.get("start_char_idx", node_data.get("start_char_idx"))
    end_char_idx = metadata.get("end_char_idx", node_data.get("end_char_idx"))

    node_dict = {
        "text": cleaned_text,
        "hash": hashstr(cleaned_text, with_salt=True),
        "start_char_idx": start_char_idx,
        "end_char_idx": end_char_idx,
        "metadata": metadata, # Keep all original metadata
    }
    return node_dict


def gen_filename_from_url(url):
    from urllib.parse import urlparse, unquote
    parsed_url = urlparse(unquote(url))

    # Attempt to get a meaningful name from the last path segment
    path_segments = [seg for seg in parsed_url.path.split('/') if seg]
    if path_segments:
        last_segment = path_segments[-1]
        # Remove common extensions if they are part of the segment
        name_part, _ = os.path.splitext(last_segment)
        if name_part: # Use name part if it's not empty after removing extension
            filename = name_part
        else: # Fallback to domain if path is just '/' or ends with extension only
            filename = parsed_url.netloc or "unknown_url"
    else: # If no path, use domain
        filename = parsed_url.netloc or "unknown_url"

    # Sanitize and shorten
    filename = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in filename)
    filename = filename[:100] # Limit length

    # Add a common URL extension if none obvious
    if not any(filename.endswith(ext) for ext in ['.html', '.htm', '.php', '.asp']):
         filename += ".urlpage" # Generic extension

    return filename
