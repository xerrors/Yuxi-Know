#!/usr/bin/env python3
"""
用户表字段迁移脚本
为现有用户添加新字段：user_id, phone_number, avatar
将现有的 username 作为 user_id 的默认值
"""

# ruff: noqa: E402

import sys
from pathlib import Path

from sqlalchemy import text

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.storage.db.manager import db_manager
from src.storage.db.models import User as User


def migrate_user_fields():
    """执行用户字段迁移"""
    print("开始用户字段迁移...")

    try:
        # 获取数据库会话
        db = db_manager.get_session()

        # 1. 添加新字段（如果不存在）
        print("检查并添加新字段...")

        # 检查字段是否存在的SQL
        check_columns_sql = """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'users' AND table_schema = DATABASE()
        """

        try:
            result = db.execute(text(check_columns_sql))
            existing_columns = [row[0] for row in result.fetchall()]
            print(f"现有字段: {existing_columns}")

            # 添加缺失的字段
            if "user_id" not in existing_columns:
                print("添加 user_id 字段...")
                db.execute(text("ALTER TABLE users ADD COLUMN user_id VARCHAR(255)"))

            if "phone_number" not in existing_columns:
                print("添加 phone_number 字段...")
                db.execute(text("ALTER TABLE users ADD COLUMN phone_number VARCHAR(255)"))

            if "avatar" not in existing_columns:
                print("添加 avatar 字段...")
                db.execute(text("ALTER TABLE users ADD COLUMN avatar VARCHAR(500)"))

            db.commit()
            print("字段添加完成")

        except Exception as e:
            print(f"字段检查/添加失败: {e}")
            # 对于SQLite，尝试直接添加字段
            try:
                db.execute(text("ALTER TABLE users ADD COLUMN user_id TEXT"))
                db.execute(text("ALTER TABLE users ADD COLUMN phone_number TEXT"))
                db.execute(text("ALTER TABLE users ADD COLUMN avatar TEXT"))
                db.commit()
                print("字段添加完成（SQLite模式）")
            except Exception as sqlite_e:
                print(f"SQLite字段添加也失败: {sqlite_e}")
                print("字段可能已存在，继续执行...")

        # 2. 为现有用户设置默认 user_id
        print("为现有用户设置默认 user_id...")

        # 查询所有没有 user_id 的用户
        users_without_user_id = db.execute(
            text("SELECT id, username FROM users WHERE user_id IS NULL OR user_id = ''")
        ).fetchall()

        print(f"找到 {len(users_without_user_id)} 个需要设置 user_id 的用户")

        for user_id, username in users_without_user_id:
            # 将 username 作为默认的 user_id
            print(f"为用户 {username} (ID: {user_id}) 设置 user_id: {username}")
            db.execute(text("UPDATE users SET user_id = :user_id WHERE id = :id"), {"user_id": username, "id": user_id})

        db.commit()

        # 3. 添加唯一索引
        print("添加唯一索引...")
        try:
            # 先检查索引是否存在
            try:
                db.execute(text("CREATE UNIQUE INDEX idx_users_user_id ON users(user_id)"))
                print("创建 user_id 唯一索引")
            except Exception:
                print("user_id 索引可能已存在")

            try:
                db.execute(
                    text(
                        "CREATE UNIQUE INDEX idx_users_phone_number ON users(phone_number) "
                        "WHERE phone_number IS NOT NULL"
                    )
                )
                print("创建 phone_number 唯一索引")
            except Exception:
                print("phone_number 索引可能已存在")

            db.commit()

        except Exception as e:
            print(f"索引创建失败: {e}")
            print("继续执行...")

        # 4. 验证迁移结果
        print("验证迁移结果...")
        total_users = db.execute(text("SELECT COUNT(*) FROM users")).scalar()
        users_with_user_id = db.execute(
            text("SELECT COUNT(*) FROM users WHERE user_id IS NOT NULL AND user_id != ''")
        ).scalar()

        print(f"总用户数: {total_users}")
        print(f"已设置 user_id 的用户数: {users_with_user_id}")

        if total_users == users_with_user_id:
            print("✅ 迁移成功完成！")
        else:
            print("❌ 迁移可能有问题，请检查数据库")

    except Exception as e:
        print(f"迁移过程中发生错误: {e}")
        if "db" in locals():
            db.rollback()
        raise
    finally:
        if "db" in locals():
            db.close()


if __name__ == "__main__":
    migrate_user_fields()
