from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

# 导入所有模型文件，确保它们被注册到Base.metadata
from . import user_model
from . import kb_models
from . import thread_model