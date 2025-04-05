import os
import json
import time
from pathlib import Path
import traceback

from src import config
from src.utils import logger
from src.core.kb_db_manager import kb_db_manager

def migrate_json_to_sqlite():
    """将JSON文件数据迁移到SQLite数据库"""
    # 原始JSON文件路径
    json_path = os.path.join(config.save_dir, "data", "database.json")

    if not os.path.exists(json_path):
        logger.info(f"未找到原始JSON文件: {json_path}，无需迁移")
        return False

    try:
        # 读取JSON文件
        with open(json_path, "r", encoding='utf-8') as f:
            data = json.load(f)

        if not data or "databases" not in data or not data["databases"]:
            logger.info("JSON文件中没有数据库信息，无需迁移")
            return False

        # 开始迁移
        logger.info(f"开始迁移知识库数据，共 {len(data['databases'])} 个数据库")

        # 遍历所有数据库
        for db_info in data["databases"]:
            db_id = db_info["db_id"]
            name = db_info["name"]
            description = db_info["description"]
            embed_model = db_info.get("embed_model")
            dimension = db_info.get("dimension")
            metadata = db_info.get("metadata", {})

            logger.info(f"处理数据库: {name} (ID: {db_id}), metadata类型: {type(metadata)}")

            # 检查数据库是否已存在
            existing_db = kb_db_manager.get_database_by_id(db_id)
            if existing_db:
                logger.info(f"数据库 {name} (ID: {db_id}) 已存在，跳过创建")
                continue

            # 创建数据库
            db = kb_db_manager.create_database(
                db_id=db_id,
                name=name,
                description=description,
                embed_model=embed_model,
                dimension=dimension,
                metadata=metadata  # 这里传入metadata，在kb_db_manager中会被正确存储为meta_info
            )

            # 处理文件
            files = db_info.get("files", {})
            if isinstance(files, list):
                files = {f["file_id"]: f for f in files}

            for file_id, file_info in files.items():
                # 添加文件
                kb_db_manager.add_file(
                    db_id=db_id,
                    file_id=file_id,
                    filename=file_info["filename"],
                    path=file_info["path"],
                    file_type=file_info["type"],
                    status=file_info["status"]
                )

                # 处理节点
                nodes = file_info.get("nodes", [])
                for node in nodes:
                    node_metadata = node.get("metadata", {})
                    if node_metadata is None:
                        node_metadata = {}
                    logger.debug(f"节点metadata类型: {type(node_metadata)}")

                    kb_db_manager.add_node(
                        file_id=file_id,
                        text=node["text"],
                        hash_value=node.get("hash"),
                        start_char_idx=node.get("start_char_idx"),
                        end_char_idx=node.get("end_char_idx"),
                        metadata=node_metadata  # 在kb_db_manager中会被正确存储为meta_info
                    )

            logger.info(f"数据库 {name} (ID: {db_id}) 迁移完成，共 {len(files)} 个文件")

        # 备份原始JSON文件
        backup_path = json_path + f".bak.{int(time.time())}"
        os.rename(json_path, backup_path)
        logger.info(f"迁移完成，原始JSON文件已备份为: {backup_path}")

        return True

    except Exception as e:
        logger.error(f"迁移过程中出错: {e}")
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    migrate_json_to_sqlite()