import asyncio
import json
import os
import pathlib
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy import create_engine, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from server.utils.singleton import SingletonMeta
from src import config
from src.storage.db.models import Base, User
from src.utils import logger

try:
    from server.utils.migrate import DatabaseMigrator, validate_database_schema
except ImportError:
    DatabaseMigrator = None

    # 如果迁移工具不存在，使用简单的占位函数
    def validate_database_schema(db_path):
        return True, []


class DBManager(metaclass=SingletonMeta):
    """数据库管理器 - 提供异步数据库连接和会话管理"""

    def __init__(self):
        self.db_path = os.path.join(config.save_dir, "database", "server.db")
        self.ensure_db_dir()

        # 创建异步SQLAlchemy引擎，配置JSON序列化器以支持中文
        # 使用 ensure_ascii=False 确保中文字符不被转义为 Unicode 序列
        self.async_engine = create_async_engine(
            f"sqlite+aiosqlite:///{self.db_path}",
            json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
            json_deserializer=json.loads,
        )

        # 创建异步会话工厂
        self.AsyncSession = async_sessionmaker(bind=self.async_engine, class_=AsyncSession, expire_on_commit=False)

        # 保留同步引擎用于迁移等特殊操作
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
            json_deserializer=json.loads,
        )
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
        if not os.path.exists(self.db_path):
            return

        if DatabaseMigrator is not None:
            migrator = DatabaseMigrator(self.db_path)
            try:
                migrator.run_migrations()
            except Exception as exc:
                logger.error(f"数据库迁移执行失败: {exc}")
        else:
            logger.warning("数据库迁移工具缺失，无法自动执行迁移")

        is_valid, issues = validate_database_schema(self.db_path)

        if not is_valid:
            logger.warning("=" * 60)
            logger.warning("检测到数据库结构与当前模型不一致！")
            logger.warning("=" * 60)
            for issue in issues:
                logger.warning(f"  ⚠️  {issue}")
            logger.warning("")
            logger.warning("请运行 scripts/migrate_user_soft_delete.py 手动修复数据库结构")
            logger.warning("=" * 60)

    def get_session(self):
        """获取同步数据库会话"""
        return self.Session()

    @contextmanager
    def get_session_context(self):
        """获取同步数据库会话的上下文管理器"""
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

    async def get_async_session(self):
        """获取异步数据库会话"""
        return self.AsyncSession()

    @asynccontextmanager
    async def get_async_session_context(self):
        """获取异步数据库会话的上下文管理器"""
        session = self.AsyncSession()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Async database operation failed: {e}")
            raise
        finally:
            # Shield close operation to ensure connection is properly closed even if task is cancelled
            # This prevents aiosqlite from raising errors during cancellation
            await asyncio.shield(session.close())

    def check_first_run(self):
        """检查是否首次运行（同步版本）"""
        session = self.get_session()
        try:
            # 检查是否有任何用户存在
            return session.query(User).count() == 0
        finally:
            session.close()

    async def async_check_first_run(self):
        """检查是否首次运行（异步版本）"""
        async with self.get_async_session_context() as session:
            # 检查是否有任何用户存在
            result = await session.execute(select(func.count(User.id)))
            count = result.scalar()
            return count == 0


# 创建全局数据库管理器实例
db_manager = DBManager()
