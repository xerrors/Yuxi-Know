"""PostgreSQL engine、session 和连接生命周期。"""

import json
import os
from contextlib import asynccontextmanager

from psycopg_pool import AsyncConnectionPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from yuxi.infrastructure.observability.logging import logger
from yuxi.infrastructure.postgres.connection import postgres_conninfo
from yuxi.infrastructure.runtime_settings import get_int_env
from yuxi.shared.singleton import SingletonMeta


class PostgresManager(metaclass=SingletonMeta):
    """PostgreSQL 数据库管理器 - 支持知识库和业务数据"""

    KB_DATABASE_URL_ENV = "POSTGRES_URL"

    def __init__(self):
        self.async_engine = None
        self.AsyncSession = None
        self.langgraph_pool = None
        self.langgraph_checkpointer = None
        self._langgraph_checkpointer_setup = False
        self._initialized = False

    def initialize(self):
        """初始化数据库连接"""
        if self._initialized:
            return

        db_url = os.getenv(self.KB_DATABASE_URL_ENV)
        if not db_url:
            logger.error(f"环境变量 {self.KB_DATABASE_URL_ENV} 未设置，请在 docker-compose.yml 或 .env 中配置 PostgreSQL 连接字符串")
            return

        try:
            # 创建异步 SQLAlchemy 引擎
            self.async_engine = create_async_engine(
                db_url,
                json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
                json_deserializer=json.loads,
                pool_pre_ping=True,
                pool_recycle=1800,
                pool_size=get_int_env("POSTGRES_POOL_SIZE", 10),
                max_overflow=get_int_env("POSTGRES_MAX_OVERFLOW", 20, minimum=0),
                pool_timeout=get_int_env("POSTGRES_POOL_TIMEOUT_SECONDS", 30),
            )

            # 创建异步会话工厂
            self.AsyncSession = async_sessionmaker(
                bind=self.async_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

            # ==========================================
            # 2. 为 LangGraph 专门初始化一个原生 psycopg_pool
            # ==========================================
            # ⚠️ 注意：psycopg 不认识 "+asyncpg" 这样的 SQLAlchemy 方言标识。
            # 如果你的 db_url 是 "postgresql+asyncpg://user:pwd@host/db"，
            # 需要把它清洗成标准的 "postgresql://user:pwd@host/db"
            langgraph_db_url = postgres_conninfo(db_url)

            # 创建 LangGraph 专属连接池
            self.langgraph_pool = AsyncConnectionPool(
                conninfo=langgraph_db_url,
                max_size=get_int_env("LANGGRAPH_POSTGRES_POOL_SIZE", 10),
                timeout=get_int_env("LANGGRAPH_POSTGRES_POOL_TIMEOUT_SECONDS", 30),
                kwargs={"autocommit": True},  # LangGraph Checkpoint 强依赖 autocommit
                check=AsyncConnectionPool.check_connection,
            )

            self._initialized = True
            logger.info("PostgreSQL manager initialized for knowledge base")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL manager: {e}")

    @property
    def is_postgresql(self) -> bool:
        """检查是否是 PostgreSQL 数据库"""
        if not self._initialized:
            return False
        return self.async_engine.dialect.name == "postgresql"

    @asynccontextmanager
    async def schema_migration_lock(self):
        """为测试与迁移调用方提供统一的 Schema advisory lock。"""
        from yuxi.migrations.schema import schema_migration_lock

        async with schema_migration_lock(self):
            yield

    async def get_async_session(self) -> AsyncSession:
        """获取异步数据库会话"""
        self.initialize()  # 确保已初始化
        return self.AsyncSession()

    @asynccontextmanager
    async def get_async_session_context(self):
        """获取异步数据库会话的上下文管理器"""
        self.initialize()  # 确保已初始化
        session = self.AsyncSession()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            # HTTP 校验和 SQL 异常可携带密码、授权码与参数，只记录异常类型。
            logger.error(f"PostgreSQL async operation failed: {type(e).__name__}")
            raise
        finally:
            await session.close()

    async def close(self):
        """关闭引擎"""
        if self.async_engine:
            await self.async_engine.dispose()

        if self.langgraph_pool:
            await self.langgraph_pool.close()

        self.async_engine = None
        self.AsyncSession = None
        self.langgraph_pool = None
        self.langgraph_checkpointer = None
        self._langgraph_checkpointer_setup = False
        self._initialized = False

    async def async_check_first_run(self):
        """检查是否首次运行（异步版本）- 检查用户表是否有数据"""
        from sqlalchemy import func, select

        self._check_initialized()
        async with self.get_async_session_context() as session:
            from yuxi.modules.identity.models import User

            result = await session.execute(select(func.count(User.id)))
            count = result.scalar()
            return count == 0

    async def commit(self):
        """提交当前会话"""
        self._check_initialized()
        async with self.get_async_session_context():
            pass  # commit is automatic in context manager

    def _check_initialized(self):
        """检查是否已初始化"""
        if not self._initialized:
            raise RuntimeError("PostgreSQL manager not initialized. Please check configuration.")


pg_manager = PostgresManager()
