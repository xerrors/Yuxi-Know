from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

# 导入所有模型，确保它们被注册到 Base.metadata
# 导入数据库管理器
from src.storage.db.manager import db_manager  # noqa: E402
from src.storage.db.models import (  # noqa: E402, F401
    OperationLog,
    User,
)  # noqa: E402
from src.storage.db.models_knowledge import (  # noqa: E402, F401
    EvaluationBenchmark,
    EvaluationResult,
    EvaluationResultDetail,
    KnowledgeBase,
    KnowledgeFile,
)

__all__ = [
    "Base",
    "User",
    "OperationLog",
    "KnowledgeBase",
    "KnowledgeFile",
    "EvaluationBenchmark",
    "EvaluationResult",
    "EvaluationResultDetail",
    "db_manager",
]
