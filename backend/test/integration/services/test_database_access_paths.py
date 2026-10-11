"""隔离 PostgreSQL 的查询计划校准与物理索引审计。"""

import json

import pytest
from sqlalchemy import text

from test.integration.support.postgres_schema import create_isolated_manager as _create_isolated_manager
from test.integration.support.postgres_schema import drop_isolated_schema as _drop_isolated_schema
from yuxi.migrations.schema import create_business_tables, create_knowledge_tables, ensure_business_schema

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


async def test_fresh_schema_has_no_exact_duplicate_physical_indexes():
    """按实际键、谓词、表达式、排序和访问方法识别重复索引。"""
    schema, admin, engine, manager = await _create_isolated_manager("pytest_index_catalog")
    try:
        await create_business_tables(manager)
        await create_knowledge_tables(manager)
        await ensure_business_schema(manager)
        async with engine.connect() as conn:
            rows = await conn.execute(
                text("""
                SELECT t.relname, array_agg(x.relname ORDER BY x.relname) AS indexes
                FROM pg_index i JOIN pg_class x ON x.oid=i.indexrelid
                JOIN pg_class t ON t.oid=i.indrelid JOIN pg_namespace n ON n.oid=t.relnamespace
                WHERE n.nspname=current_schema()
                GROUP BY t.relname,x.relam,i.indkey::text,i.indclass::text,i.indcollation::text,
                         i.indoption::text,i.indnkeyatts,coalesce(pg_get_expr(i.indpred,i.indrelid),''),
                         coalesce(pg_get_expr(i.indexprs,i.indrelid),'')
                HAVING count(*)>1
            """)
            )
            duplicate = [dict(row._mapping) for row in rows]
            assert duplicate == [], duplicate
    finally:
        await _drop_isolated_schema(schema, admin, engine)


async def test_queue_history_and_membership_indexes_remove_baseline_work():
    """固定两万条合成事实，比较原查询计划与删除目标索引的负向计划。"""
    # 只比较计划形状与实际行数，不把受 planner 统计影响的估算作为性能门禁。
    schema, admin, engine, manager = await _create_isolated_manager("pytest_access_paths")
    try:
        await create_business_tables(manager)
        await ensure_business_schema(manager)
        async with engine.begin() as conn:
            for sql in (
                "INSERT INTO users (uid,username,password_hash,role,is_deleted,login_failed_count) VALUES ('u','u','fixture','user',0,0)",
                "INSERT INTO projects (id,uid,selection_status,workdir_path,directory_mode) VALUES ('p','u','implicit','projects/p','managed')",
                "INSERT INTO sessions (thread_id,tree_root_thread_id,uid,agent_id,project_id,status,is_pinned,updated_at) SELECT 't'||i,'t'||i,'u','main','p','active',false,now() FROM generate_series(0,99) i",
                "INSERT INTO agent_inputs (id,thread_id,uid,agent_slug,kind,status,messages,input_payload,source,channel,"
                "origin_metadata,created_at,cancelled_at,attachment_file_ids) SELECT 'i'||i,'t'||(i%100),'u','main','follow_up',"
                "CASE WHEN i%2=0 THEN 'pending' ELSE 'cancelled' END,'[]','{}','chat','web','{}',now(),"
                "CASE WHEN i%2=1 THEN now() END,'[]' FROM generate_series(1,20000) i",
                "INSERT INTO messages (session_record_id,role,content,delivery_status,created_at) SELECT c.id,'user','fixture','queued',now()+i*interval '1 microsecond' FROM generate_series(1,20000) i JOIN sessions c ON c.thread_id='t'||(i%100)",
                "INSERT INTO agent_input_receipts (id,idempotency_key,uid,thread_id,event_type,intent_hash,input_id,created_at) SELECT 'r'||i,'key'||i,'u','t'||(i%100),'input','fixture','i'||i,now() FROM generate_series(1,20000) i",

                "INSERT INTO agent_turns (id,thread_id,uid,status,created_at) SELECT 'turn'||i,'t'||i,'u','completed',now() FROM generate_series(0,99) i",
                "INSERT INTO agent_runs (id,thread_id,runtime_scope_id,turn_id,session_record_id,agent_slug,uid,status,source,channel,run_type,origin_metadata,input_payload,token_usage,runtime_cleanup_pending,created_at) SELECT 'run'||i,c.thread_id,c.thread_id,'turn'||(i%100),c.id,'main','u','completed','chat','web','chat','{}','{}','{}',false,now() FROM generate_series(1,20000) i JOIN sessions c ON c.thread_id='t'||(i%100)",
                "UPDATE agent_runs SET status='running',worker_id='fixture',lease_expires_at=now()-interval '1 second' WHERE id IN (SELECT 'run'||i FROM generate_series(1,100) i)",
                "INSERT INTO background_jobs (id,name,type,status,progress,message,cancel_requested,handler_version,attempt_count,timeout_seconds,lease_expires_at,created_at) SELECT 'job'||i,'fixture','knowledge_index',CASE WHEN i<=20 THEN 'running' ELSE 'success' END,0,'',0,1,1,60,now()-interval '1 second',now() FROM generate_series(1,20000) i",
                "ANALYZE",
            ):
                await conn.execute(text(sql))
        paths = (
            (
                "ix_agent_inputs_pending_head",
                "SELECT * FROM agent_inputs WHERE thread_id='t0' AND uid='u' AND app_id IS NULL AND status='pending' ORDER BY (kind='steer') DESC,received_seq LIMIT 1 FOR UPDATE",
            ),
            (
                "ix_messages_session_created_id",
                "SELECT * FROM messages WHERE session_record_id=(SELECT id FROM sessions WHERE thread_id='t0') ORDER BY created_at DESC,id DESC LIMIT 50",
            ),
            (
                "ix_agent_runs_turn_execution",
                "SELECT * FROM agent_runs WHERE turn_id='turn0' ORDER BY execution_seq,id LIMIT 50",
            ),
            (
                "ix_agent_input_receipts_input_seq",
                "SELECT max(receive_seq) FROM agent_input_receipts WHERE input_id='i100'",
            ),
        )
        for index, query in paths:
            async with engine.connect() as conn:
                raw = await conn.scalar(text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query))
                current = json.loads(raw) if isinstance(raw, str) else raw
                assert index in json.dumps(current), current
                savepoint = await conn.begin_nested()
                try:
                    await conn.execute(text(f'DROP INDEX "{index}"'))
                    raw = await conn.scalar(text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query))
                    baseline = json.loads(raw) if isinstance(raw, str) else raw
                    assert index not in json.dumps(baseline)
                    assert current[0]["Plan"]["Actual Rows"] == baseline[0]["Plan"]["Actual Rows"]
                    if index in (
                        "ix_agent_inputs_pending_head",
                        "ix_messages_session_created_id",
                        "ix_agent_runs_turn_execution",
                    ):
                        assert '"Sort"' not in json.dumps(current)
                        assert '"Sort"' in json.dumps(baseline)
                finally:
                    await savepoint.rollback()
        # 小型 Session 列表保留原索引；现有 lease/job 复合索引不重复新增。
        observed = (
            "SELECT * FROM sessions WHERE uid='u' AND app_id IS NULL AND status='active' ORDER BY is_pinned DESC,updated_at DESC,id DESC LIMIT 20",
            "SELECT * FROM agent_runs WHERE status IN ('running','cancel_requested') AND lease_expires_at < now() ORDER BY lease_expires_at LIMIT 100 FOR UPDATE SKIP LOCKED",
            "SELECT * FROM background_jobs WHERE status='running' AND lease_expires_at < now() ORDER BY lease_expires_at LIMIT 100 FOR UPDATE SKIP LOCKED",
        )
        async with engine.connect() as conn:
            for query in observed:
                raw = await conn.scalar(text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query))
                plan = json.loads(raw) if isinstance(raw, str) else raw
                assert plan[0]["Plan"]["Actual Rows"] > 0
    finally:
        await _drop_isolated_schema(schema, admin, engine)
