"""真实 HTTP 与 PostgreSQL 下 Turn 结果只来自明确绑定的 Run。"""

import os
import json
import uuid

import asyncpg
import pytest

from yuxi.infrastructure.postgres.models import load_models
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from test.live_api_cleanup import make_test_session_title
from yuxi.modules.agents.scope import ActorScope
from yuxi.modules.agents.services.turns import get_turn_snapshot

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_turn_result_follows_only_its_bound_run(test_client, admin_headers, standard_user):
    """相邻 Turn 的输出与 Run 不得代替本轮最终结果。"""
    agents = await test_client.get("/api/agent", headers=admin_headers)
    assert agents.status_code == 200, agents.text
    agent = next(item for item in agents.json()["agents"] if item.get("is_default"))
    agent_slug = agent.get("slug") or agent["agent_id"]
    created = await test_client.post(
        "/api/v1/agents/sessions",
        json={"agent_id": agent_slug, "title": make_test_session_title("turn-result")},
        headers={**admin_headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert created.status_code == 201, created.text
    thread_id = created.json()["id"]
    me = await test_client.get("/api/auth/me", headers=admin_headers)
    uid = str(me.json()["uid"])
    turn_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    run_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    first_run_id = str(uuid.uuid4())
    conn = await asyncpg.connect(os.environ["POSTGRES_URL"].replace("+asyncpg", ""))
    load_models()
    engine = create_async_engine(os.environ["POSTGRES_URL"])
    try:
        session_record_id = await conn.fetchval("SELECT id FROM sessions WHERE thread_id = $1", thread_id)
        assert session_record_id
        async with conn.transaction():
            for turn_id, run_id, content in zip(turn_ids, run_ids, ("first output", "second output")):
                await conn.execute(
                    "INSERT INTO agent_turns (id, thread_id, uid, status, created_at) VALUES ($1, $2, $3, 'completed', NOW())",
                    turn_id,
                    thread_id,
                    uid,
                )
                await conn.execute(
                    "INSERT INTO agent_runs "
                    "(id, thread_id, runtime_scope_id, agent_slug, uid, turn_id, status, "
                    "run_type, source, channel, input_payload, token_usage, origin_metadata, session_record_id) "
                    "VALUES ($1, $2, $2, $3, $4, $5, 'completed', 'chat', 'public_api', 'api', "
                    "'{}'::jsonb, '{}'::jsonb, '{}'::jsonb, $6)",
                    run_id,
                    thread_id,
                    agent_slug,
                    uid,
                    turn_id,
                    session_record_id,
                )
                message_id = await conn.fetchval(
                    "INSERT INTO messages (session_record_id, role, content, run_id, turn_id, delivery_status) "
                    "VALUES ($1, 'assistant', $2, $3, $4, 'complete') RETURNING id",
                    session_record_id,
                    content,
                    run_id,
                    turn_id,
                )
                await conn.execute(
                    "UPDATE messages SET extra_metadata=$2::json WHERE id=$1",
                    message_id,
                    json.dumps(
                        {
                            "public_items": {
                                "message": {
                                    "id": f"item_{message_id}",
                                    "type": "message",
                                    "turn_id": turn_id,
                                    "role": "assistant",
                                    "content": [{"type": "output_text", "text": content}],
                                    "status": "completed",
                                    "phase": "commentary",
                                    "yuxi": {"run_id": run_id, "message_id": message_id, "output_index": 0},
                                }
                            }
                        }
                    ),
                )
                await conn.execute("UPDATE agent_runs SET output_message_id = $2 WHERE id = $1", run_id, message_id)
                await conn.execute(
                    "UPDATE agent_turns SET current_run_id = $2, result_run_id = $2 WHERE id = $1",
                    turn_id,
                    run_id,
                )

        await conn.execute(
            "INSERT INTO agent_runs "
            "(id, thread_id, runtime_scope_id, agent_slug, uid, turn_id, status, run_type, source, channel, "
            "input_payload, token_usage, origin_metadata, session_record_id, started_at) "
            "VALUES ($1, $2, $2, $3, $4, $5, 'yielded', 'chat', 'public_api', 'api', "
            "'{}'::jsonb, '{}'::jsonb, '{}'::jsonb, $6, '2026-10-08T00:00:00Z')",
            first_run_id,
            thread_id,
            agent_slug,
            uid,
            turn_ids[1],
            session_record_id,
        )
        await conn.execute("UPDATE agent_runs SET started_at='2026-10-09T00:00:00Z' WHERE id=$1", run_ids[1])
        url = f"/api/v1/agents/sessions/{thread_id}/turns/{turn_ids[1]}"
        result = await test_client.get(url, headers=admin_headers)
        assert result.status_code == 200, result.text
        assert result.json()["yuxi"]["result_run_id"] == run_ids[1]
        assert result.json()["yuxi"]["output"][0]["content"] == [{"type": "output_text", "text": "second output"}]
        assert result.json()["yuxi"]["output"][0]["phase"] == "final_answer"
        assert result.json()["started_at"] == 1791417600
        assert (await test_client.get(url, headers=standard_user["headers"])).status_code == 404

        with pytest.raises(asyncpg.ForeignKeyViolationError):
            async with conn.transaction():
                await conn.execute("UPDATE agent_turns SET result_run_id = $2 WHERE id = $1", turn_ids[1], run_ids[0])

        wrong_message_id = await conn.fetchval("SELECT output_message_id FROM agent_runs WHERE id = $1", run_ids[0])
        with pytest.raises(asyncpg.ForeignKeyViolationError, match="fk_agent_runs_output_message_scope"):
            async with conn.transaction():
                await conn.execute("UPDATE agent_runs SET output_message_id = $2 WHERE id = $1", run_ids[1], wrong_message_id)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as db:
            snapshot = await get_turn_snapshot(db=db, scope=ActorScope(uid=uid, app_id=None), thread_id=thread_id, turn_id=turn_ids[1])
            assert snapshot["output"][0]["content"] == [{"type": "output_text", "text": "second output"}]
    finally:
        async with conn.transaction():
            await conn.execute(
                "UPDATE agent_turns SET current_run_id = NULL, result_run_id = NULL WHERE id = ANY($1::text[])",
                turn_ids,
            )
            await conn.execute("DELETE FROM messages WHERE run_id = ANY($1::text[])", run_ids)
            await conn.execute("DELETE FROM agent_runs WHERE id = ANY($1::text[])", [*run_ids, first_run_id])
            await conn.execute("DELETE FROM agent_turns WHERE id = ANY($1::text[])", turn_ids)
        await conn.close()
        await engine.dispose()
