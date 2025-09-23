import os
import pathlib
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.storage.db.models import Base, User
from src import config
from src.utils import logger

try:
    from server.utils.migrate import validate_database_schema
except ImportError:
    # 如果迁移工具不存在，使用简单的占位函数
    def validate_database_schema(db_path):
        return True, []


class DBManager:
    """数据库管理器 - 只提供基础的数据库连接和会话管理"""

    def __init__(self):
        self.db_path = os.path.join(config.save_dir, "database", "server.db")
        self.ensure_db_dir()

        # 创建SQLAlchemy引擎
        self.engine = create_engine(f"sqlite:///{self.db_path}")

        # 创建会话工厂
        self.Session = sessionmaker(bind=self.engine)

        # 首先创建基本表结构
        self.create_tables()

        # 然后检查并执行数据库迁移
        self.run_migrations()

    def ensure_db_dir(self):
        """确保数据库目录存在"""
        db_dir = os.path.dirname(self.db_path)
        pathlib.Path(db_dir).mkdir(parents=True, exist_ok=True)

    def create_tables(self):
        """创建数据库表"""
        # 确保所有表都会被创建
        Base.metadata.create_all(self.engine)
        logger.info("Database tables created/checked")

    def run_migrations(self):
        """运行数据库迁移"""
        # 在创建表之前先检查结构
        if os.path.exists(self.db_path):
            is_valid, issues = validate_database_schema(self.db_path)

            if not is_valid:
                logger.warning("=" * 60)
                logger.warning("检测到数据库结构与当前模型不一致！")
                logger.warning("=" * 60)
                for issue in issues:
                    logger.warning(f"  ⚠️  {issue}")
                logger.warning("")
                logger.warning("请运行以下 scripts/migrate_user_fields.py 来修复数据库结构:")
                logger.warning("=" * 60)

    def get_session(self):
        """获取数据库会话"""
        return self.Session()

    @contextmanager
    def get_session_context(self):
        """获取数据库会话的上下文管理器"""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database operation failed: {e}")
            raise
        finally:
            session.close()

    def check_first_run(self):
        """检查是否首次运行"""
        session = self.get_session()
        try:
            # 检查是否有任何用户存在
            return session.query(User).count() == 0
        finally:
            session.close()


# 创建全局数据库管理器实例
db_manager = DBManager()
