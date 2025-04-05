import os
import pathlib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, joinedload
from contextlib import contextmanager
from sqlalchemy.orm.attributes import instance_state

from src import config
from src.models.kb_models import Base, KnowledgeDatabase, KnowledgeFile, KnowledgeNode
from src.utils import logger

class KBDBManager:
    """知识库数据库管理器"""

    def __init__(self):
        self.db_path = os.path.join(config.save_dir, "data", "knowledge.db")
        self.ensure_db_dir()

        # 创建SQLAlchemy引擎
        self.engine = create_engine(f"sqlite:///{self.db_path}")

        # 创建会话工厂
        self.Session = sessionmaker(bind=self.engine)

        # 确保表存在
        self.create_tables()

    def ensure_db_dir(self):
        """确保数据库目录存在"""
        db_dir = os.path.dirname(self.db_path)
        pathlib.Path(db_dir).mkdir(parents=True, exist_ok=True)

    def create_tables(self):
        """创建数据库表"""
        Base.metadata.create_all(self.engine)

    @contextmanager
    def get_session(self):
        """获取数据库会话的上下文管理器"""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"数据库操作失败: {e}")
            raise
        finally:
            session.close()

    def _detach_safely(self, obj):
        """安全地分离对象，确保属性已加载"""
        if obj is None:
            return None

        # 确保主键已加载
        if hasattr(obj, 'id'):
            _ = obj.id
        if hasattr(obj, 'db_id'):
            _ = obj.db_id

        # 根据需要添加其他必须预加载的属性

        return obj

    # 知识库操作方法
    def get_all_databases(self):
        """获取所有知识库"""
        with self.get_session() as session:
            # 使用eager loading加载关联的files
            databases = session.query(KnowledgeDatabase).options(
                joinedload(KnowledgeDatabase.files)
            ).all()

            # 转换为字典并返回，避免后续延迟加载
            return [self._to_dict_safely(db) for db in databases]

    def get_database_by_id(self, db_id):
        """根据ID获取知识库"""
        with self.get_session() as session:
            # 使用eager loading加载关联的files
            db = session.query(KnowledgeDatabase).options(
                joinedload(KnowledgeDatabase.files).joinedload(KnowledgeFile.nodes)
            ).filter_by(db_id=db_id).first()

            # 转换为字典并返回，避免后续延迟加载
            return self._to_dict_safely(db) if db else None

    def _to_dict_safely(self, obj):
        """安全地将对象转换为字典，避免延迟加载问题"""
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        return obj

    def create_database(self, db_id, name, description, embed_model=None, dimension=None, metadata=None):
        """创建知识库"""
        with self.get_session() as session:
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

    def delete_database(self, db_id):
        """删除知识库"""
        with self.get_session() as session:
            db = session.query(KnowledgeDatabase).filter_by(db_id=db_id).first()
            if db:
                session.delete(db)
                return True
            return False

    # 文件操作方法
    def add_file(self, db_id, file_id, filename, path, file_type, status="waiting"):
        """添加文件"""
        with self.get_session() as session:
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
        with self.get_session() as session:
            file = session.query(KnowledgeFile).filter_by(file_id=file_id).first()
            if file:
                file.status = status
                return True
            return False

    def delete_file(self, file_id):
        """删除文件"""
        with self.get_session() as session:
            file = session.query(KnowledgeFile).filter_by(file_id=file_id).first()
            if file:
                session.delete(file)
                return True
            return False

    def get_files_by_database(self, db_id):
        """获取知识库下的所有文件"""
        with self.get_session() as session:
            files = session.query(KnowledgeFile).options(
                joinedload(KnowledgeFile.nodes)
            ).filter_by(database_id=db_id).all()
            return [self._to_dict_safely(file) for file in files]

    def get_file_by_id(self, file_id):
        """根据ID获取文件"""
        with self.get_session() as session:
            file = session.query(KnowledgeFile).options(
                joinedload(KnowledgeFile.nodes)
            ).filter_by(file_id=file_id).first()
            return self._to_dict_safely(file) if file else None

    # 知识块操作方法
    def add_node(self, file_id, text, hash_value=None, start_char_idx=None, end_char_idx=None, metadata=None):
        """添加知识块"""
        with self.get_session() as session:
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
        with self.get_session() as session:
            nodes = session.query(KnowledgeNode).filter_by(file_id=file_id).all()
            return [self._to_dict_safely(node) for node in nodes]

    def get_nodes_by_filter(self, file_id=None, search_text=None, limit=100):
        """根据条件筛选知识块"""
        with self.get_session() as session:
            query = session.query(KnowledgeNode)
            if file_id:
                query = query.filter_by(file_id=file_id)
            if search_text:
                query = query.filter(KnowledgeNode.text.like(f"%{search_text}%"))
            nodes = query.limit(limit).all()
            return [self._to_dict_safely(node) for node in nodes]

# 创建全局知识库数据库管理器实例
kb_db_manager = KBDBManager()