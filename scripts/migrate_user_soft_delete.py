#!/usr/bin/env python3
"""
用户表软删除字段迁移脚本

该脚本用于为历史数据库添加 `is_deleted` 与 `deleted_at` 字段，
同时会执行现有的数据库迁移逻辑，确保用户表结构与最新模型保持一致。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 将项目根目录加入到 Python 路径，便于脚本在容器中执行
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.utils.migrate import DatabaseMigrator  # noqa: E402
from src import config  # noqa: E402


def main() -> None:
    db_path = Path(config.save_dir) / "database" / "server.db"
    migrator = DatabaseMigrator(str(db_path))

    print(f"检测数据库: {db_path}")
    current_version = migrator.get_current_version()
    latest_version = migrator.get_latest_migration_version()
    print(f"当前迁移版本: v{current_version}, 最新版本: v{latest_version}")

    try:
        migrator.run_migrations()
        print("✅ 迁移完成，数据库结构已更新")
    except Exception as exc:
        print(f"❌ 迁移失败: {exc}")
        raise


if __name__ == "__main__":
    main()
