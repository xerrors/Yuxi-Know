"""PostgreSQL 数据库管理器 - 专门用于知识库数据"""

import json
import os
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.utils.singleton import SingletonMeta
from src.storage.db.models_knowledge import (
    Base,
)
from src.utils import logger


class PostgresManager(metaclass=SingletonMeta):
    """PostgreSQL 数据库管理器 - 专门用于知识库元数据"""

    # 知识库 PostgreSQL URL 环境变量名
    KB_DATABASE_URL_ENV = "YUXI_KNOWLEDGE_DATABASE_URL"

    def __init__(self):
        self.async_engine = None
        self.AsyncSession = None
        self._initialized = False

    def initialize(self):
        """初始化数据库连接"""
        if self._initialized:
            return

        db_url = os.getenv(self.KB_DATABASE_URL_ENV)
        if not db_url:
            logger.error(
                f"环境变量 {self.KB_DATABASE_URL_ENV} 未设置，"
                "请在 docker-compose.yml 或 .env 中配置 PostgreSQL 连接字符串"
            )
            return

        try:
            # 创建异步 SQLAlchemy 引擎
            self.async_engine = create_async_engine(
                db_url,
                json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
                json_deserializer=json.loads,
            )

            # 创建异步会话工厂
            self.AsyncSession = async_sessionmaker(
                bind=self.async_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

            self._initialized = True
            logger.info(f"PostgreSQL manager initialized for knowledge base: {db_url.split('@')[0]}://***")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL manager: {e}")
            # 不抛出异常，允许应用启动，但在使用时会报错

    def _check_initialized(self):
        """检查是否已初始化"""
        if not self._initialized:
            raise RuntimeError("PostgreSQL manager not initialized. Please check configuration.")

    async def create_tables(self):
        """创建所有知识库相关表"""
        self._check_initialized()
        async with self.async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("PostgreSQL tables created/checked")

    async def drop_tables(self):
        """删除所有知识库相关表（慎用！）"""
        self._check_initialized()
        async with self.async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.info("PostgreSQL tables dropped")

    async def ensure_knowledge_schema(self):
        """确保知识库 schema 包含所有必要字段"""
        self._check_initialized()
        stmts = [
            "ALTER TABLE IF EXISTS knowledge_bases ADD COLUMN IF NOT EXISTS embed_info JSONB",
            "ALTER TABLE IF EXISTS knowledge_bases ADD COLUMN IF NOT EXISTS llm_info JSONB",
            "ALTER TABLE IF EXISTS knowledge_bases ADD COLUMN IF NOT EXISTS query_params JSONB",
            "ALTER TABLE IF EXISTS knowledge_bases ADD COLUMN IF NOT EXISTS additional_params JSONB",
            "ALTER TABLE IF EXISTS knowledge_bases ADD COLUMN IF NOT EXISTS share_config JSONB",
            "ALTER TABLE IF EXISTS knowledge_bases ADD COLUMN IF NOT EXISTS mindmap JSONB",
            "ALTER TABLE IF EXISTS knowledge_bases ADD COLUMN IF NOT EXISTS sample_questions JSONB",
            "ALTER TABLE IF EXISTS knowledge_bases ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ",
            "ALTER TABLE IF EXISTS knowledge_files ADD COLUMN IF NOT EXISTS parent_id VARCHAR(64)",
            "ALTER TABLE IF EXISTS knowledge_files ADD COLUMN IF NOT EXISTS original_filename VARCHAR(512)",
            "ALTER TABLE IF EXISTS knowledge_files ADD COLUMN IF NOT EXISTS file_type VARCHAR(64)",
            "ALTER TABLE IF EXISTS knowledge_files ADD COLUMN IF NOT EXISTS path VARCHAR(1024)",
            "ALTER TABLE IF EXISTS knowledge_files ADD COLUMN IF NOT EXISTS minio_url VARCHAR(1024)",
            "ALTER TABLE IF EXISTS knowledge_files ADD COLUMN IF NOT EXISTS markdown_file VARCHAR(1024)",
            "ALTER TABLE IF EXISTS knowledge_files ADD COLUMN IF NOT EXISTS status VARCHAR(32)",
            "ALTER TABLE IF EXISTS knowledge_files ADD COLUMN IF NOT EXISTS content_hash VARCHAR(128)",
            "ALTER TABLE IF EXISTS knowledge_files ADD COLUMN IF NOT EXISTS file_size BIGINT",
            "ALTER TABLE IF EXISTS knowledge_files ADD COLUMN IF NOT EXISTS content_type VARCHAR(64)",
            "ALTER TABLE IF EXISTS knowledge_files ADD COLUMN IF NOT EXISTS processing_params JSONB",
            "ALTER TABLE IF EXISTS knowledge_files ADD COLUMN IF NOT EXISTS is_folder BOOLEAN",
            "ALTER TABLE IF EXISTS knowledge_files ADD COLUMN IF NOT EXISTS error_message TEXT",
            "ALTER TABLE IF EXISTS knowledge_files ADD COLUMN IF NOT EXISTS created_by VARCHAR(64)",
            "ALTER TABLE IF EXISTS knowledge_files ADD COLUMN IF NOT EXISTS updated_by VARCHAR(64)",
            "ALTER TABLE IF EXISTS knowledge_files ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ",
            "ALTER TABLE IF EXISTS evaluation_benchmarks ADD COLUMN IF NOT EXISTS data_file_path VARCHAR(1024)",
            "ALTER TABLE IF EXISTS evaluation_benchmarks ADD COLUMN IF NOT EXISTS created_by VARCHAR(64)",
            "ALTER TABLE IF EXISTS evaluation_benchmarks ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ",
            "ALTER TABLE IF EXISTS evaluation_results ADD COLUMN IF NOT EXISTS metrics JSONB",
            "ALTER TABLE IF EXISTS evaluation_results ADD COLUMN IF NOT EXISTS overall_score DOUBLE PRECISION",
            "ALTER TABLE IF EXISTS evaluation_results ADD COLUMN IF NOT EXISTS total_questions INTEGER",
            "ALTER TABLE IF EXISTS evaluation_results ADD COLUMN IF NOT EXISTS completed_questions INTEGER",
            "ALTER TABLE IF EXISTS evaluation_results ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ",
            "ALTER TABLE IF EXISTS evaluation_results ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ",
            "ALTER TABLE IF EXISTS evaluation_results ADD COLUMN IF NOT EXISTS created_by VARCHAR(64)",
            "ALTER TABLE IF EXISTS evaluation_result_details ADD COLUMN IF NOT EXISTS gold_chunk_ids JSONB",
            "ALTER TABLE IF EXISTS evaluation_result_details ADD COLUMN IF NOT EXISTS gold_answer TEXT",
            "ALTER TABLE IF EXISTS evaluation_result_details ADD COLUMN IF NOT EXISTS generated_answer TEXT",
            "ALTER TABLE IF EXISTS evaluation_result_details ADD COLUMN IF NOT EXISTS retrieved_chunks JSONB",
            "ALTER TABLE IF EXISTS evaluation_result_details ADD COLUMN IF NOT EXISTS metrics JSONB",
            "CREATE INDEX IF NOT EXISTS idx_kb_type ON knowledge_bases(kb_type)",
            "CREATE INDEX IF NOT EXISTS idx_kb_name ON knowledge_bases(name)",
            "CREATE INDEX IF NOT EXISTS idx_kf_db_id ON knowledge_files(db_id)",
            "CREATE INDEX IF NOT EXISTS idx_kf_parent ON knowledge_files(parent_id)",
            "CREATE INDEX IF NOT EXISTS idx_kf_status ON knowledge_files(status)",
            "CREATE INDEX IF NOT EXISTS idx_kf_hash ON knowledge_files(content_hash)",
            "CREATE INDEX IF NOT EXISTS idx_eb_db_id ON evaluation_benchmarks(db_id)",
            "CREATE INDEX IF NOT EXISTS idx_er_db_id ON evaluation_results(db_id)",
            "CREATE INDEX IF NOT EXISTS idx_er_status ON evaluation_results(status)",
            "CREATE INDEX IF NOT EXISTS idx_er_started ON evaluation_results(started_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_erd_task ON evaluation_result_details(task_id)",
        ]

        async with self.async_engine.begin() as conn:
            for stmt in stmts:
                await conn.execute(text(stmt))

    @property
    def is_postgresql(self) -> bool:
        """检查是否是 PostgreSQL 数据库"""
        if not self._initialized:
            return False
        return self.async_engine.dialect.name == "postgresql"

    async def get_async_session(self) -> AsyncSession:
        """获取异步数据库会话"""
        self._check_initialized()
        return self.AsyncSession()

    @asynccontextmanager
    async def get_async_session_context(self):
        """获取异步数据库会话的上下文管理器"""
        self._check_initialized()
        session = self.AsyncSession()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"PostgreSQL async operation failed: {e}")
            raise
        finally:
            await session.close()

    async def close(self):
        """关闭引擎"""
        if self.async_engine:
            await self.async_engine.dispose()


# 创建全局 PostgreSQL 管理器实例
pg_manager = PostgresManager()
