import os
from dotenv import load_dotenv

load_dotenv("src/.env", override=True)

from concurrent.futures import ThreadPoolExecutor  # noqa: E402
executor = ThreadPoolExecutor()

from src.config import Config  # noqa: E402
config = Config()

# 导入知识库相关模块
from src.knowledge.kb_factory import KnowledgeBaseFactory  # noqa: E402
from src.knowledge.kb_manager import KnowledgeBaseManager  # noqa: E402
from src.knowledge.lightrag_kb import LightRagKB  # noqa: E402
from src.knowledge.chroma_kb import ChromaKB  # noqa: E402
from src.knowledge.milvus_kb import MilvusKB  # noqa: E402

# 注册知识库类型
KnowledgeBaseFactory.register("chroma", ChromaKB, {
    "chunk_size": 1000,
    "chunk_overlap": 200,
    "description": "基于 ChromaDB 的轻量级向量知识库，适合开发和小规模部署"
})

KnowledgeBaseFactory.register("milvus", MilvusKB, {
    "chunk_size": 1000,
    "chunk_overlap": 200,
    "description": "基于 Milvus 的生产级向量知识库，适合大规模高性能部署"
})


KnowledgeBaseFactory.register("lightrag", LightRagKB, {
    "description": "基于图检索的知识库，支持实体关系构建和复杂查询"
})


# 创建知识库管理器
work_dir = os.path.join(config.save_dir, "knowledge_base_data")
knowledge_base = KnowledgeBaseManager(work_dir)

from src.knowledge import GraphDatabase  # noqa: E402
graph_base = GraphDatabase()
