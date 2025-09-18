import os

from ..config import config
from .graphbase import GraphDatabase
from .chroma_kb import ChromaKB
from .kb_factory import KnowledgeBaseFactory
from .kb_manager import KnowledgeBaseManager
from .lightrag_kb import LightRagKB
from .milvus_kb import MilvusKB

# 注册知识库类型
KnowledgeBaseFactory.register("chroma", ChromaKB, {"description": "基于 ChromaDB 的轻量级向量知识库，适合开发和小规模"})
KnowledgeBaseFactory.register("milvus", MilvusKB, {"description": "基于 Milvus 的生产级向量知识库，适合高性能部署"})
KnowledgeBaseFactory.register("lightrag", LightRagKB, {"description": "基于图检索的知识库，支持实体关系构建和复杂查询"})

# 创建知识库管理器
work_dir = os.path.join(config.save_dir, "knowledge_base_data")
knowledge_base = KnowledgeBaseManager(work_dir)

# 创建图数据库实例
graph_base = GraphDatabase()

__all__ = ["GraphDatabase", "knowledge_base", "graph_base"]
