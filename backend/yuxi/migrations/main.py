# ruff: noqa: E402  # 入口必须先加载环境。
"""建立当前 PostgreSQL Schema，并执行明确支持的增量升级。"""

from __future__ import annotations

import asyncio

from yuxi.bootstrap.environment import load_environment

load_environment()

from sqlalchemy import text

from yuxi.bootstrap.models import load_models
from yuxi.infrastructure.postgres.base import BusinessBase, KnowledgeBase
from yuxi.infrastructure.postgres.checkpointer import setup_langgraph_checkpointer
from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.infrastructure.postgres.schema import BUSINESS_SCHEMA_VERSION, KNOWLEDGE_SCHEMA_VERSION, get_schema_versions
from yuxi.migrations.schema import (
    create_business_tables,
    create_knowledge_tables,
    create_schema_version_table,
    drop_fresh_schema,
    ensure_business_schema,
    ensure_knowledge_schema,
    record_schema_version,
    schema_migration_lock,
    upgrade_feedback_schema,
    upgrade_knowledge_name_schema,
)
from yuxi.modules.system.options import ensure_options_in_db


async def _require_empty_database() -> None:
    """拒绝未版本化的旧库和上次初始化失败后留下的半成品。"""
    load_models()
    owned_tables = (
        set(BusinessBase.metadata.tables)
        | set(KnowledgeBase.metadata.tables)
        | {
            "tasks",  # 已退役的后台作业表仍属于旧库。
            "conversations",  # 已退役的业务表仍属于旧库，禁止被当作空库。
            "agent_input_messages",
            "checkpoint_writes",
            "checkpoint_blobs",
            "checkpoints",
            "checkpoint_migrations",
        }
    )
    async with pg_manager.async_engine.connect() as conn:
        rows = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"))
        existing = owned_tables.intersection(rows.scalars().all())
    if existing:
        raise RuntimeError(f"Fresh Yuxi schema requires an empty database; found {', '.join(sorted(existing))}")


async def main() -> None:
    """新库建立完整基线；任一初始化阶段失败都会清理后允许重试。"""
    pg_manager.initialize()
    try:
        async with schema_migration_lock(pg_manager):
            versions = await get_schema_versions(pg_manager)
            current = {"business": BUSINESS_SCHEMA_VERSION, "knowledge": KNOWLEDGE_SCHEMA_VERSION}
            if versions.get("initializing") == 1:
                # 该标记只在确认空库后提交；崩溃恢复只能清理本初始化器拥有的半成品。
                await drop_fresh_schema(pg_manager)
                versions = {}
            if versions == current:
                return
            if versions in (
                {"business": 8, "knowledge": 3},
                {"business": 8, "knowledge": KNOWLEDGE_SCHEMA_VERSION},
                {"business": BUSINESS_SCHEMA_VERSION, "knowledge": 3},
            ):
                if versions["business"] == 8:
                    await upgrade_feedback_schema(pg_manager)
                if versions["knowledge"] == 3:
                    await upgrade_knowledge_name_schema(pg_manager)
                return
            if versions:
                raise RuntimeError(f"Unsupported Yuxi schema versions: {versions}; required {current}")

            await _require_empty_database()
            try:
                await create_schema_version_table(pg_manager)
                await record_schema_version(pg_manager, "initializing", 1)
                await create_business_tables(pg_manager)
                await create_knowledge_tables(pg_manager)
                await ensure_business_schema(pg_manager)
                await ensure_knowledge_schema(pg_manager)
                await setup_langgraph_checkpointer(pg_manager)
                async with pg_manager.get_async_session_context() as session:
                    await ensure_options_in_db(session)
                    await session.commit()
                await create_schema_version_table(pg_manager)
                await record_schema_version(pg_manager, "business", BUSINESS_SCHEMA_VERSION)
                await record_schema_version(pg_manager, "knowledge", KNOWLEDGE_SCHEMA_VERSION)
                async with pg_manager.async_engine.begin() as conn:
                    await conn.execute(text("DELETE FROM yuxi_schema_migrations WHERE domain = 'initializing'"))
            except BaseException:
                await drop_fresh_schema(pg_manager)
                raise
    finally:
        await pg_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
