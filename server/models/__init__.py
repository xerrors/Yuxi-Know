from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

# 确保在创建表之前，所有模型都已被导入并注册到 Base.metadata
# 这样在 DBManager.create_tables() 执行时，可以创建包括 thread 在内的所有表
from server.models.user_model import User, OperationLog  # noqa: E402, F401
from server.models.thread_model import Thread  # noqa: E402, F401
from server.models.kb_models import KnowledgeDatabase, KnowledgeFile, KnowledgeNode  # noqa: E402, F401
