from src.knowledge.utils.connection import (
    MySQLConnectionManager,
)
from src.knowledge.utils.exceptions import MySQLConnectionError

def get_connection_manager(host, user, password, database, port ) -> MySQLConnectionManager:
    """获取全局连接管理器"""
    _connection_manager: MySQLConnectionManager | None = None
    # 从环境变量中读取 MySQL 配置
    mysql_config = {
        "host": host,
        "user": user,
        "password": password,
        "database": database,
        "port": int(port),
        "charset": "utf8mb4",
    }
    # 验证配置完整性
    required_keys = ["host", "user", "password", "database"]
    for key in required_keys:
        if not mysql_config[key]:
            raise MySQLConnectionError(f"MySQL configuration missing required key: {key}")

    _connection_manager = MySQLConnectionManager(mysql_config)
    return _connection_manager