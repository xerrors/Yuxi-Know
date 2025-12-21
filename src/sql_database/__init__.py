import os
from src.config import config
from src.sql_database.factory import DBConnectorBaseFactory
from src.sql_database.implementations.mysql import MySQLConnector
from src.sql_database.manager import SqlDataBaseManager

# 注册知识库类型
# KnowledgeBaseFactory.register("chroma", ChromaKB, {"description": "基于 ChromaDB 的轻量级向量知识库，适合开发和小规模"})
DBConnectorBaseFactory.register("mysql", MySQLConnector, {"description": "MySQL 数据库连接器"})
# KnowledgeBaseFactory.register("lightrag", LightRagKB, {"description": "基于图检索的知识库，支持实体关系构建和复杂查询"})

# 创建知识库管理器
work_dir = os.path.join(config.save_dir, "sql_database_data")
sql_database = SqlDataBaseManager(work_dir)

__all__ = ["db_connection_manager"]