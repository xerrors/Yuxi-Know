"""Yuxi Schema 版本事实在真实 PostgreSQL 上的集成测试。"""

from __future__ import annotations

import asyncio
import os
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.infrastructure.postgres.schema import BUSINESS_SCHEMA_VERSION, KNOWLEDGE_SCHEMA_VERSION
from yuxi.migrations import main as schema_bootstrap
from yuxi.migrations.schema import (
    create_business_tables,
    create_knowledge_tables,
    create_schema_version_table,
    ensure_business_schema,
    record_schema_version,
    upgrade_feedback_schema,
)
from yuxi.infrastructure.postgres.schema import get_schema_versions, require_current_schema
from yuxi.infrastructure.postgres.manager import PostgresManager
from yuxi.modules.knowledge.models import KnowledgeBase

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_feedback_upgrade_is_atomic_repeatable_and_preserves_old_data(monkeypatch):
    """真实 8→9 失败回滚，重跑建表与索引后保留原有样本。"""
    from yuxi.modules.agents.models.feedback import AgentFeedbackRecord

    schema, admin, engine, manager = await _create_isolated_manager("pytest_feedback_upgrade")
    try:
        await create_business_tables(manager)
        await create_schema_version_table(manager)
        await record_schema_version(manager, "business", 8)
        await record_schema_version(manager, "knowledge", KNOWLEDGE_SCHEMA_VERSION)
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE agent_feedback_records"))
            await conn.execute(
                text(
                    "INSERT INTO users (username, uid, password_hash, role, login_failed_count, is_deleted) "
                    "VALUES ('upgrade-user', 'upgrade-user', 'hash', 'user', 0, 0)"
                )
            )
        create_table = AgentFeedbackRecord.__table__.create

        def fail_after_ddl(conn, **kwargs):
            """在真实 DDL 后注入中断，不能提交表或新版本。"""
            create_table(conn, **kwargs)
            raise RuntimeError("after feedback ddl")

        with monkeypatch.context() as patch:
            patch.setattr(AgentFeedbackRecord.__table__, "create", fail_after_ddl)
            with pytest.raises(RuntimeError, match="after feedback ddl"):
                await upgrade_feedback_schema(manager)
        assert (await get_schema_versions(manager))["business"] == 8
        async with engine.connect() as conn:
            assert await conn.scalar(text("SELECT to_regclass('agent_feedback_records')")) is None
        monkeypatch.setattr(schema_bootstrap, "pg_manager", manager)
        monkeypatch.setattr(manager, "initialize", lambda: None)
        monkeypatch.setattr(manager, "close", AsyncMock())
        await schema_bootstrap.main()
        await schema_bootstrap.main()
        await require_current_schema(manager)
        async with engine.connect() as conn:
            assert await conn.scalar(text("SELECT uid FROM users WHERE username='upgrade-user'")) == "upgrade-user"
            assert await conn.scalar(text("SELECT to_regclass('uq_agent_feedback_tool_call')")) is not None
            assert await conn.scalar(text("SELECT to_regclass('uq_agent_feedback_user_run')")) is not None
    finally:
        await _drop_isolated_schema(schema, admin, engine)


@pytest.fixture(scope="session", autouse=True)
def ensure_live_api_schema():
    """本文件自行创建隔离 Schema，不依赖运行中的 API。"""


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_knowledge_resources():
    """隔离 Schema 测试没有 HTTP 资源需要清理。"""
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """隔离 Schema 测试没有 Sandbox 资源需要清理。"""
    yield


def _scoped_manager(engine) -> PostgresManager:
    """创建不触碰进程单例的隔离 manager。"""
    manager = object.__new__(PostgresManager)
    PostgresManager.__init__(manager)
    manager.async_engine = engine
    manager._initialized = True
    return manager


async def _create_isolated_manager(prefix: str):
    """创建位于独立 PostgreSQL Schema 的 manager 与清理句柄。"""
    schema = f"{prefix}_{uuid.uuid4().hex[:16]}"
    admin_engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    async with admin_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped_engine = create_async_engine(
        os.environ["POSTGRES_URL"],
        pool_pre_ping=True,
        connect_args={"server_settings": {"search_path": schema}},
    )
    return schema, admin_engine, scoped_engine, _scoped_manager(scoped_engine)


async def _drop_isolated_schema(schema: str, admin_engine, scoped_engine) -> None:
    """释放隔离 Schema 及其 engine。"""
    await scoped_engine.dispose()
    async with admin_engine.begin() as connection:
        await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    await admin_engine.dispose()


async def test_schema_migration_lock_serializes_real_postgres_sessions() -> None:
    """两个 migrator 竞争同一 advisory lock 时只允许一个进入临界区。"""
    engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    manager = _scoped_manager(engine)
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    second_entered = asyncio.Event()

    async def first_migrator() -> None:
        async with manager.schema_migration_lock():
            first_entered.set()
            await release_first.wait()

    async def second_migrator() -> None:
        await first_entered.wait()
        async with manager.schema_migration_lock():
            second_entered.set()

    first_task = asyncio.create_task(first_migrator())
    second_task = asyncio.create_task(second_migrator())
    try:
        await asyncio.wait_for(first_entered.wait(), timeout=2)
        await asyncio.sleep(0.1)
        assert second_entered.is_set() is False
        release_first.set()
        await asyncio.wait_for(asyncio.gather(first_task, second_task), timeout=2)
        assert second_entered.is_set() is True
    finally:
        release_first.set()
        for task in (first_task, second_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(first_task, second_task, return_exceptions=True)
        await engine.dispose()


async def test_fresh_business_schema_contains_input_lifecycle_without_request_table() -> None:
    """新环境直接建立 Input、Receipt、Turn 和 Run 当前结构，不执行历史补列。"""
    schema, admin_engine, scoped_engine, manager = await _create_isolated_manager("pytest_agent_schema")
    try:
        await create_business_tables(manager)
        await ensure_business_schema(manager)
        async with scoped_engine.connect() as connection:
            tables = set(
                (
                    await connection.execute(
                        text("SELECT table_name FROM information_schema.tables WHERE table_schema = :schema"),
                        {"schema": schema},
                    )
                ).scalars()
            )
            run_columns = set(
                (
                    await connection.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns WHERE table_schema = :schema AND table_name = 'agent_runs'"
                        ),
                        {"schema": schema},
                    )
                ).scalars()
            )
            input_columns = set(
                (
                    await connection.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns WHERE table_schema = :schema AND table_name = 'agent_inputs'"
                        ),
                        {"schema": schema},
                    )
                ).scalars()
            )
            execution_seq_nullable = await connection.scalar(
                text(
                    "SELECT is_nullable FROM information_schema.columns WHERE table_schema = :schema AND table_name = 'agent_runs' AND column_name = 'execution_seq'"
                ),
                {"schema": schema},
            )
            execution_seq_default = await connection.scalar(
                text(
                    "SELECT column_default FROM information_schema.columns WHERE table_schema = :schema AND table_name = 'agent_runs' AND column_name = 'execution_seq'"
                ),
                {"schema": schema},
            )
        assert {
            "sessions",
            "agent_turns",
            "agent_runs",
            "agent_inputs",
            "agent_input_receipts",
        } <= tables
        assert "agent_input_messages" not in tables
        assert "conversations" not in tables
        assert "agent_run_requests" not in tables
        assert "agent_session_input_receipts" not in tables
        assert {"turn_id", "resume_from_run_id", "session_record_id", "thread_id"} <= run_columns
        assert {"conversation_id", "conversation_thread_id"}.isdisjoint(run_columns)
        assert execution_seq_nullable == "NO"
        assert execution_seq_default and "nextval" in execution_seq_default
        assert "agent_runs_execution_seq" in execution_seq_default
        assert "input_id" not in run_columns
        assert "cutoff_seq" not in input_columns
        assert "request_id" not in run_columns
        assert {
            "kind",
            "status",
            "turn_id",
            "consumed_run_id",
            "messages",
            "received_seq",
            "thread_id",
        } <= input_columns
        assert "conversation_thread_id" not in input_columns
        assert BUSINESS_SCHEMA_VERSION == 9
        assert KNOWLEDGE_SCHEMA_VERSION == 3
    finally:
        await _drop_isolated_schema(schema, admin_engine, scoped_engine)


async def test_knowledge_child_cannot_cross_database_boundaries() -> None:
    """Chunk 的 file_id 与 kb_id 不一致时由复合外键拒绝写入。"""
    schema, admin_engine, scoped_engine, manager = await _create_isolated_manager("pytest_knowledge_boundary")
    try:
        await create_knowledge_tables(manager)
        async with scoped_engine.begin() as connection:
            await connection.execute(
                text("INSERT INTO knowledge_bases (kb_id, name, kb_type) VALUES ('kb-a', 'A', 'milvus'), ('kb-b', 'B', 'milvus')")
            )
            await connection.execute(text("INSERT INTO knowledge_files (file_id, kb_id, filename) VALUES ('file-a', 'kb-a', 'a.txt')"))

        with pytest.raises(IntegrityError):
            async with scoped_engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO knowledge_chunks (chunk_id, file_id, kb_id, chunk_index, content) VALUES ('chunk-cross', 'file-a', 'kb-b', 0, 'invalid')"
                    )
                )
    finally:
        await _drop_isolated_schema(schema, admin_engine, scoped_engine)


async def test_knowledge_timestamp_defaults_match_database_clock_in_non_utc_session() -> None:
    """带时区字段不依赖 PostgreSQL 会话时区解释无时区 UTC。"""
    schema, admin_engine, scoped_engine, manager = await _create_isolated_manager("pytest_knowledge_clock")
    try:
        await create_knowledge_tables(manager)
        session_factory = async_sessionmaker(scoped_engine, expire_on_commit=False)
        async with session_factory.begin() as session:
            await session.execute(text("SET TIME ZONE 'Asia/Shanghai'"))
            database = KnowledgeBase(kb_id="clock-kb", name="clock", kb_type="milvus")
            session.add(database)
            await session.flush()
            database_now = await session.scalar(text("SELECT clock_timestamp()"))

        async with session_factory() as verify_session:
            await verify_session.execute(text("SET TIME ZONE 'UTC'"))
            persisted_at = await verify_session.scalar(text("SELECT created_at FROM knowledge_bases WHERE kb_id = 'clock-kb'"))

        assert persisted_at.tzinfo is not None
        assert abs((persisted_at - database_now).total_seconds()) < 2
    finally:
        await _drop_isolated_schema(schema, admin_engine, scoped_engine)


async def test_open_attempt_is_unique_in_fresh_business_schema() -> None:
    """结果消息必须是已存在记录，且同一 Run 不能有两个开放 Attempt。"""
    schema, admin_engine, scoped_engine, manager = await _create_isolated_manager("pytest_execution_constraints")
    try:
        await create_business_tables(manager)
        await ensure_business_schema(manager)
        async with scoped_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO users (username, uid, password_hash, role, user_kind, is_deleted, login_failed_count) "
                    "VALUES ('constraint-user', 'constraint-user', 'test', 'user', 'human', 0, 0)"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO projects "
                    "(id, uid, selection_status, workdir_path, directory_mode, status) "
                    "VALUES ('constraint-project', 'constraint-user', 'implicit', '/tmp/constraint', "
                    "'managed', 'active')"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO sessions "
                    "(thread_id, tree_root_thread_id, uid, agent_id, project_id, status, is_pinned) "
                    "VALUES ('constraint-thread', 'constraint-thread', 'constraint-user', 'default', 'constraint-project', 'active', false)"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO agent_turns "
                    "(id, thread_id, uid, status, created_at) "
                    "VALUES ('constraint-turn', 'constraint-thread', 'constraint-user', 'running', CURRENT_TIMESTAMP)"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO agent_runs "
                    "(id, thread_id, runtime_scope_id, agent_slug, uid, status, turn_id, "
                    "source, channel, run_type, origin_metadata, input_payload, token_usage, runtime_cleanup_pending) "
                    "VALUES ('constraint-run', 'constraint-thread', 'constraint-thread', 'default', 'constraint-user', "
                    "'pending', 'constraint-turn', 'chat', 'web', 'chat', '{}', '{}', '{}', false)"
                )
            )

        async with scoped_engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE agent_runs SET session_record_id = (SELECT id FROM sessions WHERE thread_id = 'constraint-thread') WHERE id = 'constraint-run'"
                )
            )
            message_id = await connection.scalar(
                text(
                    "INSERT INTO messages (session_record_id, role, content, delivery_status) "
                    "SELECT id, 'assistant', 'unbound candidate', 'complete' FROM sessions "
                    "WHERE thread_id = 'constraint-thread' RETURNING id"
                )
            )
        for column in ("input_message_id", "output_message_id"):
            with pytest.raises(IntegrityError, match=f"fk_agent_runs_{column.split('_')[0]}_message_scope"):
                async with scoped_engine.begin() as connection:
                    await connection.execute(
                        text(f"UPDATE agent_runs SET {column} = :message_id WHERE id = 'constraint-run'"),
                        {"message_id": message_id},
                    )
        async with scoped_engine.begin() as connection:
            await connection.execute(
                text("UPDATE messages SET run_id = 'constraint-run', turn_id = 'constraint-turn' WHERE id = :message_id"),
                {"message_id": message_id},
            )
            await connection.execute(
                text("UPDATE agent_runs SET output_message_id = :message_id WHERE id = 'constraint-run'"),
                {"message_id": message_id},
            )
        with pytest.raises(IntegrityError, match="ck_messages_execution_scope"):
            async with scoped_engine.begin() as connection:
                await connection.execute(text("UPDATE messages SET turn_id = NULL WHERE id = :message_id"), {"message_id": message_id})

        async with scoped_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO agent_run_attempts (run_id, attempt_no, worker_id, started_at) VALUES ('constraint-run', 1, 'worker-a', CURRENT_TIMESTAMP)"
                )
            )

        with pytest.raises(IntegrityError):
            async with scoped_engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO agent_run_attempts (run_id, attempt_no, worker_id, started_at) VALUES ('constraint-run', 2, 'worker-b', CURRENT_TIMESTAMP)"
                    )
                )
    finally:
        await _drop_isolated_schema(schema, admin_engine, scoped_engine)


async def test_failed_fresh_initialization_cleans_checkpoint_tables_and_can_retry(monkeypatch):
    """在 checkpoint 建表后注入故障，回读空 Schema 并重新运行初始化。"""
    schema, admin, engine, manager = await _create_isolated_manager("pytest_bootstrap_retry")
    manager.AsyncSession = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(manager, "initialize", lambda: None)
    monkeypatch.setattr(manager, "close", AsyncMock())
    monkeypatch.setattr(schema_bootstrap, "pg_manager", manager)

    async def checkpoint_stage(_manager):
        """模拟跨连接 checkpoint 阶段已经提交的四张持久表。"""
        async with engine.begin() as connection:
            for name in ("checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"):
                await connection.execute(text(f"CREATE TABLE {name} (id INTEGER)"))

    monkeypatch.setattr(schema_bootstrap, "setup_langgraph_checkpointer", checkpoint_stage)
    monkeypatch.setattr(schema_bootstrap, "ensure_options_in_db", AsyncMock(side_effect=RuntimeError("after checkpoint")))
    try:
        with pytest.raises(RuntimeError, match="after checkpoint"):
            await schema_bootstrap.main()
        async with engine.connect() as connection:
            assert (await connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"))).all() == []
        monkeypatch.setattr(schema_bootstrap, "ensure_options_in_db", AsyncMock())
        await schema_bootstrap.main()
        await require_current_schema(manager)
        assert await get_schema_versions(manager) == {
            "business": BUSINESS_SCHEMA_VERSION,
            "knowledge": KNOWLEDGE_SCHEMA_VERSION,
        }
    finally:
        await _drop_isolated_schema(schema, admin, engine)


@pytest.mark.parametrize("table_name", ["sessions", "conversations", "tasks"])
async def test_unversioned_existing_yuxi_table_blocks_fresh_schema_initialization(monkeypatch, table_name) -> None:
    """未版本化的旧表不得被空库初始化误认为全新部署。"""
    schema, admin_engine, scoped_engine, manager = await _create_isolated_manager("pytest_fresh_only")
    monkeypatch.setattr(schema_bootstrap, "pg_manager", manager)
    try:
        await schema_bootstrap._require_empty_database()
        async with scoped_engine.begin() as connection:
            await connection.execute(text(f"CREATE TABLE {table_name} (id integer PRIMARY KEY)"))
        with pytest.raises(RuntimeError, match=table_name):
            await schema_bootstrap._require_empty_database()
    finally:
        await _drop_isolated_schema(schema, admin_engine, scoped_engine)


async def test_schema_version_is_persisted_and_runtime_validation_fails_closed() -> None:
    """版本表缺失、错误和正确三种状态必须形成精确启动结论。"""
    schema, admin_engine, scoped_engine, manager = await _create_isolated_manager("pytest_schema_version")

    try:
        with pytest.raises(RuntimeError, match="business=missing"):
            await require_current_schema(manager)

        await create_schema_version_table(manager)
        for incompatible_version in (7, BUSINESS_SCHEMA_VERSION + 1):
            await record_schema_version(manager, "business", incompatible_version)
            with pytest.raises(RuntimeError, match=f"business={incompatible_version}"):
                await require_current_schema(manager)
            assert (await get_schema_versions(manager))["business"] == incompatible_version

        await record_schema_version(manager, "business", BUSINESS_SCHEMA_VERSION)
        with pytest.raises(RuntimeError, match="knowledge=missing"):
            await require_current_schema(manager)

        await record_schema_version(manager, "knowledge", KNOWLEDGE_SCHEMA_VERSION)
        await require_current_schema(manager)
        assert await get_schema_versions(manager) == {
            "business": BUSINESS_SCHEMA_VERSION,
            "knowledge": KNOWLEDGE_SCHEMA_VERSION,
        }
    finally:
        await _drop_isolated_schema(schema, admin_engine, scoped_engine)


async def test_background_job_baseline_replaces_task_table_and_knowledge_owner_column() -> None:
    """新库只建立后台作业模型，文件执行关联使用作业 ID。"""
    schema, admin_engine, scoped_engine, manager = await _create_isolated_manager("pytest_background_job_schema")
    try:
        await create_business_tables(manager)
        await create_knowledge_tables(manager)
        await ensure_business_schema(manager)
        async with scoped_engine.connect() as connection:
            tables = set(
                (
                    await connection.execute(
                        text("SELECT table_name FROM information_schema.tables WHERE table_schema = :schema"),
                        {"schema": schema},
                    )
                ).scalars()
            )
            columns = set(
                (
                    await connection.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns WHERE table_schema = :schema AND table_name = 'knowledge_files'"
                        ),
                        {"schema": schema},
                    )
                ).scalars()
            )
            constraints = set(
                (
                    await connection.execute(
                        text(
                            "SELECT constraint_name FROM information_schema.table_constraints WHERE table_schema = :schema AND table_name = 'background_jobs'"
                        ),
                        {"schema": schema},
                    )
                ).scalars()
            )
        assert "background_jobs" in tables
        assert {"tasks", "jobs"}.isdisjoint(tables)
        assert "processing_job_id" in columns and "processing_task_id" not in columns
        assert {"ck_background_jobs_status", "uq_background_jobs_active_dedupe"} <= constraints
        await create_schema_version_table(manager)
        await record_schema_version(manager, "business", 2)
        await record_schema_version(manager, "knowledge", 1)
        with pytest.raises(RuntimeError, match="business=2.*knowledge=1"):
            await require_current_schema(manager)
    finally:
        await _drop_isolated_schema(schema, admin_engine, scoped_engine)
