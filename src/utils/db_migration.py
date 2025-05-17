"""
数据库迁移工具：用于将独立的knowledge.db数据迁移到整合的server.db中
"""

import os
import sqlite3
import shutil
from datetime import datetime
from src import config
from src.utils import logger

def migrate_knowledge_db():
    """
    将独立的knowledge.db数据迁移到整合的server.db中

    Returns:
        bool: 迁移是否成功
    """
    # 确定数据库路径
    knowledge_db_path = os.path.join(config.save_dir, "data", "knowledge.db")
    server_db_path = os.path.join(config.save_dir, "data", "server.db")

    # 检查源数据库是否存在
    if not os.path.exists(knowledge_db_path):
        logger.info("未找到knowledge.db数据库，无需迁移")
        return False

    # 确保目标数据库目录存在
    os.makedirs(os.path.dirname(server_db_path), exist_ok=True)

    try:
        # 备份两个数据库
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        if os.path.exists(server_db_path):
            shutil.copy2(server_db_path, f"{server_db_path}.bak.{timestamp}")
            logger.info(f"已备份server.db到 {server_db_path}.bak.{timestamp}")

        shutil.copy2(knowledge_db_path, f"{knowledge_db_path}.bak.{timestamp}")
        logger.info(f"已备份knowledge.db到 {knowledge_db_path}.bak.{timestamp}")

        # 连接到两个数据库
        knowledge_conn = sqlite3.connect(knowledge_db_path)
        server_conn = sqlite3.connect(server_db_path)

        knowledge_cursor = knowledge_conn.cursor()
        server_cursor = server_conn.cursor()

        # 获取knowledge.db中的表
        knowledge_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = knowledge_cursor.fetchall()

        # 迁移每个表
        for table in tables:
            table_name = table[0]
            if table_name.startswith('sqlite_'):
                continue  # 跳过SQLite内部表

            logger.info(f"正在迁移表 {table_name}...")

            # 获取表结构
            knowledge_cursor.execute(f"PRAGMA table_info({table_name});")
            columns = knowledge_cursor.fetchall()

            # 在server.db中创建表（如果不存在）
            column_defs = ", ".join([f'"{col[1]}" {col[2]}' for col in columns])
            create_table_sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({column_defs});'
            server_cursor.execute(create_table_sql)

            # 获取数据
            knowledge_cursor.execute(f'SELECT * FROM "{table_name}";')
            rows = knowledge_cursor.fetchall()

            if rows:
                # 准备插入语句
                placeholders = ", ".join(["?" for _ in range(len(columns))])
                insert_sql = f'INSERT OR REPLACE INTO "{table_name}" VALUES ({placeholders});'

                # 批量插入数据
                server_cursor.executemany(insert_sql, rows)
                logger.info(f"已迁移 {len(rows)} 条记录到表 {table_name}")

        # 提交更改
        server_conn.commit()

        # 关闭连接
        knowledge_cursor.close()
        knowledge_conn.close()
        server_cursor.close()
        server_conn.close()

        logger.info("数据库迁移完成")
        logger.warning(f"请手动删除旧的knowledge.db文件: {knowledge_db_path}")
        return True

    except Exception as e:
        logger.error(f"数据库迁移失败: {str(e)}")
        return False

if __name__ == "__main__":
    # 当作为脚本运行时执行迁移
    result = migrate_knowledge_db()
    print(f"迁移{'成功' if result else '失败'}")