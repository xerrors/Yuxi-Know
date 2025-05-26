from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import time

from server.models import Base

class KnowledgeDatabase(Base):
    """知识库模型"""
    __tablename__ = 'knowledge_databases'

    id = Column(Integer, primary_key=True, autoincrement=True)
    db_id = Column(String, nullable=False, unique=True, index=True)  # 数据库ID
    name = Column(String, nullable=False)  # 数据库名称
    description = Column(Text, nullable=True)  # 描述
    embed_model = Column(String, nullable=True)  # 嵌入模型名称
    dimension = Column(Integer, nullable=True)  # 向量维度
    meta_info = Column(JSON, nullable=True)  # 元数据
    created_at = Column(DateTime, default=func.now())  # 创建时间

    # 关系
    files = relationship("KnowledgeFile", back_populates="database", cascade="all, delete-orphan")

    def to_dict(self, with_nodes=True):
        """转换为字典格式，确保meta_info映射为metadata"""
        result = {
            "id": self.id,
            "db_id": self.db_id,
            "name": self.name,
            "description": self.description,
            "embed_model": self.embed_model,
            "dimension": self.dimension,
            "metadata": self.meta_info or {},
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
        # 添加文件信息
        if self.files:
            result["files"] = {file.file_id: file.to_dict(with_nodes=with_nodes) for file in self.files}
        else:
            result["files"] = {}
        return result

class KnowledgeFile(Base):
    """知识库文件模型"""
    __tablename__ = 'knowledge_files'

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(String, nullable=False, index=True)  # 文件ID
    database_id = Column(String, ForeignKey('knowledge_databases.db_id'), nullable=False)  # 所属数据库ID
    filename = Column(String, nullable=False)  # 文件名
    path = Column(String, nullable=False)  # 文件路径
    file_type = Column(String, nullable=False)  # 文件类型
    status = Column(String, nullable=False)  # 处理状态
    created_at = Column(DateTime, default=func.now())  # 创建时间

    # 关系
    database = relationship("KnowledgeDatabase", back_populates="files")
    nodes = relationship("KnowledgeNode", back_populates="file", cascade="all, delete-orphan")

    @property
    def computed_node_count(self):
        """动态计算节点数量"""
        return len(self.nodes) if self.nodes is not None else 0

    def to_dict(self, with_nodes=True):
        """转换为字典格式"""
        result = {
            "file_id": self.file_id,
            "filename": self.filename,
            "path": self.path,
            "type": self.file_type,
            "status": self.status,
            "node_count": self.computed_node_count,
            "created_at": self.created_at.timestamp() if self.created_at else time.time()
        }
        if with_nodes:
            result["nodes"] = [node.to_dict() for node in self.nodes] if self.nodes else []
        return result

class KnowledgeNode(Base):
    """知识块模型"""
    __tablename__ = 'knowledge_nodes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(String, ForeignKey('knowledge_files.file_id'), nullable=False)  # 所属文件ID
    text = Column(Text, nullable=False)  # 文本内容
    hash = Column(String, nullable=True)  # 文本哈希值
    start_char_idx = Column(Integer, nullable=True)  # 开始字符索引
    end_char_idx = Column(Integer, nullable=True)  # 结束字符索引
    meta_info = Column(JSON, nullable=True)  # 元数据

    # 关系
    file = relationship("KnowledgeFile", back_populates="nodes")

    def to_dict(self):
        """转换为字典格式，确保meta_info映射为metadata"""
        return {
            "id": self.id,
            "file_id": self.file_id,
            "text": self.text,
            "hash": self.hash,
            "start_char_idx": self.start_char_idx,
            "end_char_idx": self.end_char_idx,
            "metadata": self.meta_info or {}  # 确保映射正确
        }
