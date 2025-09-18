import os
import pathlib
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from server.models import Base
from server.models.user_model import User
from server.utils.migrate import check_and_migrate
from src import config
from src.utils import logger


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
        try:
            success = check_and_migrate(self.db_path)
            if success:
                logger.info("数据库迁移检查完成")
            else:
                logger.warning("数据库迁移过程中出现问题")
        except Exception as e:
            logger.error(f"数据库迁移失败: {e}")
            # 不抛出异常，以防止阻断应用启动

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
