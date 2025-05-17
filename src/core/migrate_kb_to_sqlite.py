import os
import json
import time
from src import config
from src.utils import logger, hashstr
from server.db_manager import db_manager

def migrate_json_to_sqlite():
    """
    将旧的JSON格式知识库数据迁移到SQLite数据库

    Returns:
        bool: 是否成功迁移，如果没有JSON文件或已经迁移过则返回False
    """
    json_path = os.path.join(config.save_dir, "data", "database.json")

    # 检查JSON文件是否存在
    if not os.path.exists(json_path):
        logger.info("没有找到旧的JSON数据文件，无需迁移")
        return False

    try:
        # 读取旧的JSON文件
        with open(json_path, 'r', encoding='utf-8') as f:
            old_data = json.load(f)

        if not old_data or not isinstance(old_data, dict) or not old_data.get("databases"):
            logger.warning("JSON文件格式不正确或为空")
            return False

        # 获取知识库列表
        databases = old_data.get("databases", {})

        # 迁移每个知识库
        for db_id, db_info in databases.items():
            logger.info(f"正在迁移知识库: {db_info.get('name')} (ID: {db_id})")

            # 创建知识库
            db_dict = db_manager.create_database(
                db_id=db_id,
                name=db_info.get('name', '未命名知识库'),
                description=db_info.get('description', ''),
                embed_model=db_info.get('embed_model'),
                dimension=db_info.get('dimension')
            )

            # 迁移文件
            files = db_info.get('files', {})
            for file_id, file_info in files.items():
                logger.info(f"  正在迁移文件: {file_info.get('filename')} (ID: {file_id})")

                # 添加文件
                db_manager.add_file(
                    db_id=db_id,
                    file_id=file_id,
                    filename=file_info.get('filename', '未命名文件'),
                    path=file_info.get('path', ''),
                    file_type=file_info.get('type', 'unknown'),
                    status=file_info.get('status', 'done')
                )

                # 迁移节点
                nodes = file_info.get('nodes', [])
                for node in nodes:
                    db_manager.add_node(
                        file_id=file_id,
                        text=node.get('text', ''),
                        hash_value=node.get('hash'),
                        start_char_idx=node.get('start_char_idx'),
                        end_char_idx=node.get('end_char_idx'),
                        metadata=node.get('metadata', {})
                    )

        # 备份旧的JSON文件
        backup_path = f"{json_path}.bak.{int(time.time())}"
        os.rename(json_path, backup_path)
        logger.info(f"迁移完成，旧的JSON文件已备份到: {backup_path}")
        logger.warning(f"请手动删除旧的JSON文件: {json_path}")

        return True

    except Exception as e:
        logger.error(f"迁移过程中出错: {e}")
        return False