"""真实 PostgreSQL 的消息、目录、代次和评估关系负向证据。"""

import os
import asyncio
import sys
import textwrap

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from test.integration.support.postgres_schema import create_isolated_manager as _create_isolated_manager
from test.integration.support.postgres_schema import drop_isolated_schema as _drop_isolated_schema
from yuxi.migrations.schema import create_business_tables, create_knowledge_tables, ensure_business_schema
from yuxi.modules.knowledge.models import KnowledgeChunk, KnowledgeGraphEntity, KnowledgeGraphTriple

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


async def test_knowledge_relationships_reject_cross_scope_and_keep_delete_semantics():
    """单 ID 都合法仍不能跨 KB 或 Dataset 归属。"""
    schema, admin, engine, manager = await _create_isolated_manager("pytest_relations")
    try:
        await create_knowledge_tables(manager)
        async with engine.begin() as conn:
            for sql in (
                "INSERT INTO knowledge_bases (kb_id,name,kb_type) VALUES ('a','A','milvus'),('b','B','milvus')",
                "INSERT INTO knowledge_files (file_id,kb_id,filename) VALUES ('fa','a','a'),('fb','b','b'),('folder','a','folder')",
                "INSERT INTO evaluation_datasets (dataset_id,kb_id,name) VALUES ('da','a','A'),('db','b','B'),('da2','a','A2')",
                "INSERT INTO evaluation_dataset_items (item_id,dataset_id,kb_id,item_index,query_text) VALUES ('ia','da','a',0,'a'),('ib','db','b',0,'b'),('ia2','da2','a',0,'a2')",
                "INSERT INTO evaluation_runs (run_id,kb_id,dataset_id,name) VALUES ('ra','a','da','run')",
            ):
                await conn.execute(text(sql))
        invalid = (
            ("fk_knowledge_files_parent_kb", "UPDATE knowledge_files SET parent_id='fa' WHERE file_id='fb'"),
            (
                "fk_evaluation_runs_dataset_kb",
                "INSERT INTO evaluation_runs (run_id,kb_id,dataset_id,name) VALUES ('bad','a','db','bad')",
            ),
            (
                "fk_evaluation_run_items_run_dataset",
                "INSERT INTO evaluation_run_items (run_id,dataset_id,dataset_item_id,item_index,query_text) VALUES ('ra','db','ib',0,'bad')",
            ),
            (
                "fk_evaluation_run_items_item_dataset",
                "INSERT INTO evaluation_run_items (run_id,dataset_id,dataset_item_id,item_index,query_text) VALUES ('ra','da','ia2',0,'bad')",
            ),
            (
                "fk_evaluation_run_items_item_dataset",
                "INSERT INTO evaluation_run_items (run_id,dataset_item_id,item_index,query_text) VALUES ('ra','ib',0,'bad')",
            ),
        )
        for constraint, sql in invalid:
            with pytest.raises(IntegrityError, match=constraint):
                async with engine.begin() as conn:
                    await conn.execute(text(sql))
        async with engine.begin() as conn:
            await conn.execute(text("UPDATE knowledge_files SET parent_id='folder' WHERE file_id='fa'"))
            await conn.execute(text("DELETE FROM knowledge_files WHERE file_id='folder'"))
            await conn.execute(
                text(
                    "INSERT INTO evaluation_run_items (run_id,dataset_id,dataset_item_id,item_index,query_text) VALUES ('ra','da','ia',0,'snapshot')"
                )
            )
            await conn.execute(text("DELETE FROM evaluation_datasets WHERE dataset_id='da'"))
        async with engine.connect() as conn:
            assert (
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='knowledge_files' AND column_name='active_version_id'"
                    )
                )
                == 0
            )
            assert (
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM information_schema.tables WHERE table_schema=current_schema() AND table_name='knowledge_file_versions'"
                    )
                )
                == 0
            )
            assert await conn.scalar(text("SELECT parent_id FROM knowledge_files WHERE file_id='fa'")) is None
            assert await conn.scalar(text("SELECT dataset_id FROM evaluation_runs WHERE run_id='ra'")) is None
            row = (
                await conn.execute(text("SELECT dataset_id,dataset_item_id,query_text FROM evaluation_run_items WHERE run_id='ra'"))
            ).one()
            assert tuple(row) == (None, None, "snapshot")
    finally:
        await _drop_isolated_schema(schema, admin, engine)


async def test_unselected_message_and_run_thread_must_match_execution_scope():
    """不被结果指针选择的审计消息也必须属于相同 Thread/Turn/Run。"""
    schema, admin, engine, manager = await _create_isolated_manager("pytest_message_scope")
    try:
        await create_business_tables(manager)
        await ensure_business_schema(manager)
        async with engine.begin() as conn:
            for sql in (
                "INSERT INTO users (uid,username,password_hash,role,is_deleted,login_failed_count) VALUES ('u','u','fixture','user',0,0)",
                "INSERT INTO projects (id,uid,selection_status,workdir_path,directory_mode) VALUES ('p','u','implicit','projects/p','managed')",
                "INSERT INTO sessions (thread_id,tree_root_thread_id,uid,agent_id,project_id,status,is_pinned) VALUES ('ta','ta','u','main','p','active',false),('tb','tb','u','main','p','active',false)",
                "INSERT INTO agent_turns (id,thread_id,uid,status,created_at) VALUES ('turn','ta','u','running',CURRENT_TIMESTAMP)",
                "INSERT INTO agent_runs (id,thread_id,runtime_scope_id,turn_id,session_record_id,agent_slug,uid,status,source,channel,run_type,origin_metadata,input_payload,token_usage,runtime_cleanup_pending) SELECT 'run','ta','ta','turn',id,'main','u','pending','chat','web','chat','{}','{}','{}',false FROM sessions WHERE thread_id='ta'",
            ):
                await conn.execute(text(sql))
        with pytest.raises(IntegrityError, match="fk_messages_run_turn_session"):
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO messages (session_record_id,role,content,run_id,turn_id,delivery_status,message_type) SELECT id,"
                        "'assistant','audit','run','turn','complete','model_audit' FROM sessions WHERE thread_id='tb'"
                    )
                )
        with pytest.raises(IntegrityError, match="fk_agent_runs_session_thread|fk_agent_runs_session_runtime_scope"):
            async with engine.begin() as conn:
                await conn.execute(
                    text("UPDATE agent_runs SET session_record_id=(SELECT id FROM sessions WHERE thread_id='tb') WHERE id='run'")
                )
        async with engine.connect() as conn:
            assert await conn.scalar(text("SELECT count(*) FROM messages")) == 0
            assert await conn.scalar(text("SELECT thread_id FROM agent_runs WHERE id='run'")) == "ta"
    finally:
        await _drop_isolated_schema(schema, admin, engine)


async def test_input_consumption_and_receipt_references_stay_in_owning_thread():
    """合法单 ID 不能把 Input 消费或接收回执连接到其他 Thread。"""
    schema, admin, engine, manager = await _create_isolated_manager("pytest_input_scope")
    try:
        await create_business_tables(manager)
        await ensure_business_schema(manager)
        async with engine.begin() as conn:
            for sql in (
                "INSERT INTO users (uid,username,password_hash,role,is_deleted,login_failed_count) VALUES ('u','u','fixture','user',0,0)",
                "INSERT INTO projects (id,uid,selection_status,workdir_path,directory_mode) VALUES ('p','u','implicit','projects/p','managed')",
                "INSERT INTO sessions (thread_id,tree_root_thread_id,uid,agent_id,project_id,status,is_pinned) VALUES ('ta','ta','u','main','p','active',false),('tb','tb','u','main','p','active',false)",
                "INSERT INTO agent_turns (id,thread_id,uid,status,created_at) VALUES ('turn-a','ta','u','completed',now()),('turn-b','tb','u','completed',now()),('turn-a2','ta','u','completed',now())",
                "INSERT INTO agent_runs (id,thread_id,runtime_scope_id,turn_id,session_record_id,agent_slug,uid,status,source,channel,run_type,origin_metadata,input_payload,token_usage,runtime_cleanup_pending) SELECT 'run-a','ta','ta','turn-a',id,'main','u','completed','chat','web','chat','{}','{}','{}',false FROM sessions WHERE thread_id='ta'",
                "INSERT INTO agent_inputs (id,thread_id,uid,agent_slug,kind,status,messages,input_payload,source,channel,"
                "origin_metadata,created_at,attachment_file_ids) VALUES "
                "('input-a','ta','u','main','follow_up','pending','[]','{}','chat','web','{}',now(),'[]'),"
                "('input-b','tb','u','main','follow_up','pending','[]','{}','chat','web','{}',now(),'[]')",
            ):
                await conn.execute(text(sql))
        invalid = (
            (
                "fk_agent_inputs_turn_thread",
                "UPDATE agent_inputs SET status='consumed',turn_id='turn-a',consumed_run_id='run-a',consumed_at=now() WHERE id='input-b'",
            ),
            (
                "fk_agent_input_receipts_input_thread",
                "INSERT INTO agent_input_receipts (id,idempotency_key,uid,thread_id,event_type,intent_hash,input_id,created_at) VALUES ('bad','bad','u','ta','input','fixture','input-b',now())",
            ),
            (
                "fk_agent_input_receipts_turn_thread",
                "INSERT INTO agent_input_receipts (id,idempotency_key,uid,thread_id,event_type,intent_hash,turn_id,created_at) VALUES ('bad','bad','u','ta','cancel','fixture','turn-b',now())",
            ),
            (
                "fk_agent_input_receipts_run_turn",
                "INSERT INTO agent_input_receipts (id,idempotency_key,uid,thread_id,event_type,intent_hash,turn_id,run_id,created_at) VALUES ('bad','bad','u','ta','cancel','fixture','turn-a2','run-a',now())",
            ),
            (
                "ck_agent_input_receipts_run_turn",
                "INSERT INTO agent_input_receipts (id,idempotency_key,uid,thread_id,event_type,intent_hash,run_id,created_at) VALUES ('bad','bad','u','tb','cancel','fixture','run-a',now())",
            ),
            (
                "ck_agent_input_receipts_target",
                "INSERT INTO agent_input_receipts (id,idempotency_key,uid,thread_id,event_type,intent_hash,"
                "input_id,turn_id,run_id,created_at) VALUES ('bad','bad','u','ta','input','fixture','input-a','turn-a','run-a',now())",
            ),
        )
        for constraint, sql in invalid:
            with pytest.raises(IntegrityError, match=constraint):
                async with engine.begin() as conn:
                    await conn.execute(text(sql))
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE agent_inputs SET status='consumed',turn_id='turn-a',consumed_run_id='run-a',consumed_at=now() WHERE id='input-a'"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO agent_input_receipts (id,idempotency_key,uid,thread_id,event_type,intent_hash,input_id,"
                    "created_at) VALUES ('ok','ok','u','ta','input','fixture','input-a',now())"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO agent_input_receipts (id,idempotency_key,uid,thread_id,event_type,intent_hash,turn_id,run_id,"
                    "created_at) VALUES ('control','control','u','ta','cancel','fixture','turn-a','run-a',now())"
                )
            )
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT i.thread_id,t.thread_id,r.thread_id FROM agent_inputs i JOIN agent_turns t ON t.id=i.turn_id JOIN "
                        "agent_runs r ON r.id=i.consumed_run_id WHERE i.id='input-a'"
                    )
                )
            ).one()
            assert tuple(row) == ("ta", "ta", "ta")
            assert await conn.scalar(text("SELECT status FROM agent_inputs WHERE id='input-b'")) == "pending"
            assert await conn.scalar(text("SELECT count(*) FROM agent_input_receipts")) == 2
            assert (await conn.execute(text("SELECT turn_id,run_id FROM agent_input_receipts WHERE id='ok'"))).one() == (None, None)
            assert (await conn.execute(text("SELECT turn_id,run_id FROM agent_input_receipts WHERE id='control'"))).one() == (
                "turn-a",
                "run-a",
            )
    finally:
        await _drop_isolated_schema(schema, admin, engine)


async def test_graph_mentions_reject_wrong_file_inside_same_knowledge_base():
    """实体和三元组来源必须指向 Chunk 所属文件，删除只级联该文件。"""
    schema, admin, engine, manager = await _create_isolated_manager("pytest_mention_file")
    try:
        await create_knowledge_tables(manager)
        async with engine.begin() as conn:
            await conn.execute(text("INSERT INTO knowledge_bases (kb_id,name,kb_type) VALUES ('k','K','milvus')"))
            await conn.execute(text("INSERT INTO knowledge_files (file_id,kb_id,filename) VALUES ('fa','k','A'),('fb','k','B')"))
            await conn.execute(insert(KnowledgeChunk).values(chunk_id="c", file_id="fa", kb_id="k", chunk_index=0, content="fixture"))
            await conn.execute(insert(KnowledgeGraphEntity).values(entity_id="e", kb_id="k", name="E", normalized_name="e", label="E"))
            await conn.execute(
                insert(KnowledgeGraphTriple).values(
                    triple_id="t",
                    kb_id="k",
                    source_entity_id="e",
                    target_entity_id="e",
                    relation_type="fixture",
                    content="fixture",
                )
            )
        for table, identity, value, constraint in (
            ("knowledge_graph_entity_mentions", "entity_id", "e", "fk_knowledge_graph_entity_mentions_chunk_file_kb"),
            ("knowledge_graph_triple_mentions", "triple_id", "t", "fk_knowledge_graph_triple_mentions_chunk_file_kb"),
        ):
            with pytest.raises(IntegrityError, match=constraint):
                async with engine.begin() as conn:
                    await conn.execute(
                        text(f"INSERT INTO {table} ({identity},kb_id,file_id,chunk_id) VALUES (:identity,'k','fb','c')"),
                        {"identity": value},
                    )
            async with engine.begin() as conn:
                await conn.execute(
                    text(f"INSERT INTO {table} ({identity},kb_id,file_id,chunk_id) VALUES (:identity,'k','fa','c')"),
                    {"identity": value},
                )
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM knowledge_files WHERE file_id='fb'"))
        async with engine.connect() as conn:
            assert await conn.scalar(text("SELECT count(*) FROM knowledge_graph_entity_mentions")) == 1
            assert await conn.scalar(text("SELECT count(*) FROM knowledge_graph_triple_mentions")) == 1
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM knowledge_files WHERE file_id='fa'"))
        async with engine.connect() as conn:
            assert await conn.scalar(text("SELECT count(*) FROM knowledge_graph_entity_mentions")) == 0
            assert await conn.scalar(text("SELECT count(*) FROM knowledge_graph_triple_mentions")) == 0
    finally:
        await _drop_isolated_schema(schema, admin, engine)


async def test_killed_fresh_initializer_is_recoverable_without_adopting_old_data(monkeypatch):
    """真实终止建表后的进程，持久初始化标记使第二次运行可安全重试。"""
    from yuxi.migrations import main as migration
    from yuxi.infrastructure.postgres.schema import (
        get_schema_versions,
        BUSINESS_SCHEMA_VERSION,
        KNOWLEDGE_SCHEMA_VERSION,
    )

    schema, admin, engine, manager = await _create_isolated_manager("pytest_killed_initializer")
    code = textwrap.dedent("""
        import asyncio, os
        from sqlalchemy.ext.asyncio import create_async_engine
        from yuxi.infrastructure.postgres.manager import PostgresManager
        from yuxi.migrations import main
        manager = PostgresManager()
        manager.async_engine = create_async_engine(os.environ['POSTGRES_URL'], connect_args={'server_settings': {'search_path': os.environ['INITIALIZER_TEST_SCHEMA']}})
        manager._initialized = True
        async def stop_after_tables(manager):
            os._exit(23)
        main.setup_langgraph_checkpointer = stop_after_tables
        asyncio.run(main.initialize_schema(manager))
    """)
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            env={**os.environ, "INITIALIZER_TEST_SCHEMA": schema},
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, error = await asyncio.wait_for(process.communicate(), timeout=30)
        assert process.returncode == 23, error.decode()
        assert await get_schema_versions(manager) == {"initializing": 1}
        async with engine.connect() as conn:
            assert await conn.scalar(text("SELECT to_regclass('agent_runs') IS NOT NULL"))
        manager.AsyncSession = async_sessionmaker(engine, expire_on_commit=False)

        async def checkpoint_setup(manager):
            """本例只验证初始化进程恢复；checkpoint 装配由真实 E2E 覆盖。"""

        monkeypatch.setattr(migration, "setup_langgraph_checkpointer", checkpoint_setup)
        await migration.initialize_schema(manager)
        assert await get_schema_versions(manager) == {
            "business": BUSINESS_SCHEMA_VERSION,
            "knowledge": KNOWLEDGE_SCHEMA_VERSION,
        }
    finally:
        await _drop_isolated_schema(schema, admin, engine)


async def test_persisted_timestamps_keep_the_same_instant_across_session_timezones():
    """所有业务时间列带时区；带偏移写入不受数据库 session 时区影响。"""
    from datetime import UTC, datetime, timedelta, timezone

    from yuxi.modules.identity.models import User

    schema, admin, engine, manager = await _create_isolated_manager("pytest_utc")
    instant = datetime(2026, 10, 4, 10, 30, tzinfo=timezone(timedelta(hours=8)))
    try:
        await create_business_tables(manager)
        await create_knowledge_tables(manager)
        async with engine.begin() as conn:
            assert (
                list(
                    await conn.scalars(
                        text(
                            "SELECT table_name || '.' || column_name FROM information_schema.columns "
                            "WHERE table_schema=current_schema() AND data_type='timestamp without time zone'"
                        )
                    )
                )
                == []
            )
            await conn.execute(text("SET LOCAL TIME ZONE 'America/Los_Angeles'"))
            await conn.execute(insert(User).values(uid="utc-user", username="utc-user", password_hash="fixture", last_login=instant))
        async with engine.begin() as conn:
            await conn.execute(text("SET LOCAL TIME ZONE 'Asia/Shanghai'"))
            stored = await conn.scalar(select(User.last_login).where(User.uid == "utc-user"))
            assert stored.tzinfo is not None
            assert stored == instant.astimezone(UTC)
            assert await conn.scalar(text("SELECT EXTRACT(EPOCH FROM last_login) FROM users WHERE uid='utc-user'")) == instant.timestamp()
            created = await conn.scalar(select(User.created_at).where(User.uid == "utc-user"))
            assert created.tzinfo is not None
    finally:
        await _drop_isolated_schema(schema, admin, engine)


async def test_job_and_cleanup_intent_reject_unknown_states():
    """未知状态不能绕过任务恢复或清理扫描；合法状态仍可写入。"""
    from yuxi.modules.knowledge.models import KnowledgeProjectionOutbox
    from yuxi.modules.background_jobs.models import BackgroundJobRecord

    schema, admin, engine, manager = await _create_isolated_manager("pytest_states")
    job = insert(BackgroundJobRecord).values(id="job", name="fixture", type="fixture")
    cleanup = insert(KnowledgeProjectionOutbox).values(
        event_key="cleanup", kb_id="kb", aggregate_id="file", generation=1, operation="generation_cleanup"
    )
    try:
        await create_business_tables(manager)
        await create_knowledge_tables(manager)
        for constraint, statement in (
            ("ck_background_jobs_status", job),
            ("ck_knowledge_projection_outbox_status", cleanup),
        ):
            with pytest.raises(IntegrityError, match=constraint):
                async with engine.begin() as conn:
                    await conn.execute(statement.values(status="unknown"))
        async with engine.begin() as conn:
            await conn.execute(job.values(status="pending"))
            await conn.execute(cleanup.values(status="pending"))
        async with engine.connect() as conn:
            assert await conn.scalar(select(BackgroundJobRecord.status)) == "pending"
            assert await conn.scalar(select(KnowledgeProjectionOutbox.status)) == "pending"
    finally:
        await _drop_isolated_schema(schema, admin, engine)
