"""知识库运行时单例。"""

import os

from yuxi.infrastructure.runtime_settings import get_runtime_dir
from yuxi.modules.knowledge.factory import KnowledgeBaseFactory
from yuxi.modules.knowledge.implementations.dify import DifyKB
from yuxi.modules.knowledge.implementations.feishu import FeishuKB
from yuxi.modules.knowledge.implementations.milvus import MilvusKB
from yuxi.modules.knowledge.implementations.notion import NotionKB
from yuxi.modules.knowledge.manager import KnowledgeBaseManager

KnowledgeBaseFactory.register(MilvusKB)
KnowledgeBaseFactory.register(FeishuKB)
KnowledgeBaseFactory.register(DifyKB)
KnowledgeBaseFactory.register(NotionKB)

knowledge_base = KnowledgeBaseManager(os.path.join(get_runtime_dir(), "knowledge_base_data"))
