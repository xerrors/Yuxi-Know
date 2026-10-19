"""真实 API、PostgreSQL、Redis 和 worker 的输入到 Turn 结果链。"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import UTC, datetime

import asyncpg
import httpx
import pytest

from test.e2e.e2e_helpers import (
    DETERMINISTIC_MODEL as MODEL,
)
from test.e2e.e2e_helpers import (
    DETERMINISTIC_OUTPUT as OUTPUT,
)
from test.e2e.e2e_helpers import (
    create_lifecycle_agent as _agent,
)
from test.e2e.e2e_helpers import (
    delete_agent,
    output_text,
    postgres_dsn,
    wait_for_consumed_input,
    wait_for_blocked_response,
)
from test.e2e.e2e_helpers import (
    public_message as _message,
)
from test.e2e.e2e_helpers import (
    register_replay_provider as _provider,
)
from test.e2e.e2e_helpers import (
    wait_for_terminal_turn as _turn,
)
from test.live_api_cleanup import make_test_session_title
from test.support.public_events import read_events
from yuxi.modules.agents.runtime.sandbox import UserSandboxBackend
from yuxi.modules.agents.services.tracing import get_langfuse_client
from yuxi.modules.agents.services.transport import get_redis_client
from yuxi.modules.workspace.paths import user_workspace_dir

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e, pytest.mark.slow, pytest.mark.timeout(240)]


async def _continue_queued_input(client, headers, receipt: dict, request_tag: str) -> dict:
    """显式继续暂停队列，等待唯一队头输入完成。"""
    thread_id = receipt["session_id"]
    continued = await client.post(
        f"/api/v1/agents/sessions/{thread_id}/events",
        headers={**headers, "Idempotency-Key": f"{request_tag}-{uuid.uuid4().hex}"},
        json={"events": [{"type": "yuxi.session.input.continue"}]},
    )
    assert continued.status_code == 202, continued.text
    consumed = await wait_for_consumed_input(client, headers, receipt, timeout=20)
    turn = await _turn(client, headers, thread_id, consumed["turn_id"])
    assert turn["status"] == "completed", turn
    assert OUTPUT in output_text(turn["yuxi"]["output"])
    return turn


@pytest.mark.parametrize("input_kind,stream", [("text", False), ("text", True), ("long_parts", False)])
async def test_public_session_initial_text_stream_and_saved_items(e2e_client, e2e_headers, input_kind, stream):
    """真实 worker 执行字符串输入，创建流和持久 Items 绑定相同 Turn 结果。"""
    from test.e2e.e2e_helpers import archive_public_thread

    await _provider(e2e_client, e2e_headers)
    uid = str((await e2e_client.get("/api/auth/me", headers=e2e_headers)).json()["uid"])
    slug = await _agent(e2e_client, e2e_headers, uid)
    session_id = turn_id = None
    key = str(uuid.uuid4())
    text = OUTPUT
    initial_input = text
    if input_kind == "long_parts":
        parts = [{"type": "input_text", "text": character * 20_000} for character in ["a", "b"]]
        text = "\n".join(part["text"] for part in parts)
        initial_input = [{"role": "user", "content": parts}]
    body = {
        "agent_id": slug,
        "agent": {"model": MODEL},
        "input": initial_input,
        "title": make_test_session_title("session-text"),
        "stream": stream,
    }
    headers = {**e2e_headers, "Idempotency-Key": key}
    terminal_event = None
    try:
        if stream:
            async with e2e_client.stream("POST", "/api/v1/agents/sessions", headers=headers, json=body) as response:
                assert response.status_code == 201
                assert response.headers["content-type"].startswith("text/event-stream")
                events = read_events(response)
                _, event = await anext(events)
                assert event["type"] == "agent.session.created"
                session = event["session"]
                async with asyncio.timeout(45):
                    async for _, event in events:
                        if event["type"] in {
                            "agent.session.turn.completed",
                            "agent.session.turn.failed",
                            "agent.session.turn.cancelled",
                        }:
                            terminal_event = event["turn"]
                            break
        else:
            response = await e2e_client.post("/api/v1/agents/sessions", headers=headers, json=body)
            assert response.status_code == 201, response.text
            session = response.json()
        session_id = session["id"]
        consumed = await wait_for_consumed_input(e2e_client, e2e_headers, session["yuxi"]["receipt"])
        turn_id = consumed["turn_id"]
        assert session["object"] == "agent.session" and session["agent"]["model"] == MODEL
        assert isinstance(session["created_at"], int)
        replay = await e2e_client.post(
            "/api/v1/agents/sessions",
            headers=headers,
            json={**body, "stream": False, "input": initial_input if input_kind == "long_parts" else [_message(text)]},
        )
        assert replay.status_code == 201, replay.text
        assert replay.json()["id"] == session_id
        assert replay.json()["yuxi"]["receipt"]["event_id"] == session["yuxi"]["receipt"]["event_id"]
        accepted_input = await e2e_client.get(
            f"/api/v1/agents/sessions/{session_id}/inputs/{session['yuxi']['receipt']['input_id']}", headers=e2e_headers
        )
        assert accepted_input.status_code == 200, accepted_input.text
        assert accepted_input.json()["items"][0]["content"] == [{"type": "input_text", "text": text}]
        result = await _turn(e2e_client, e2e_headers, session_id, turn_id)
        assert result["status"] == "completed", result
        if stream:
            assert terminal_event == {key: value for key, value in result.items() if key != "yuxi"}
        items_response = await e2e_client.get(
            f"/api/v1/agents/sessions/{session_id}/items", headers=e2e_headers, params={"order": "asc", "limit": 100}
        )
        assert items_response.status_code == 200, items_response.text
        items = items_response.json()["data"]
        inputs = [item for item in items if item.get("role") == "user"]
        assert len(inputs) == 1 and inputs[0]["content"] == [{"type": "input_text", "text": text}]
        final = [item for item in items if item.get("phase") == "final_answer"]
        assert len(final) == 1 and final[0]["yuxi"]["run_id"] == result["yuxi"]["result_run_id"]
        assert output_text(final) == OUTPUT
        conn = await asyncpg.connect(postgres_dsn())
        try:
            assert await conn.fetchval("SELECT count(*) FROM agent_inputs WHERE thread_id=$1", session_id) == 1
            origin = await conn.fetchrow(
                """
                SELECT run.id, run.agent_slug, run.source, run.channel, input.id AS input_id,
                       input.source AS input_source, input.channel AS input_channel,
                       input.status, input.turn_id, turn.result_run_id, session.extra_metadata->>'source' AS session_source,
                       message.source_input_id, message.extra_metadata->'agent_invocation_meta' AS invocation
                FROM agent_runs run
                JOIN agent_inputs input ON input.consumed_run_id=run.id
                JOIN agent_turns turn ON turn.id=run.turn_id
                JOIN messages message ON message.id=run.input_message_id
                JOIN sessions session ON session.id=run.session_record_id
                WHERE run.id=$1 AND run.thread_id=$2
                """,
                consumed["run_id"],
                session_id,
            )
            assert origin["agent_slug"] == slug
            assert origin["id"] == origin["result_run_id"] == result["yuxi"]["result_run_id"]
            assert origin["input_id"] == origin["source_input_id"] == consumed["input_id"]
            assert origin["status"] == "consumed" and origin["turn_id"] == turn_id
            assert origin["source"] == origin["input_source"] == origin["session_source"] == "public_api"
            assert origin["channel"] == origin["input_channel"] == "web"
            assert origin["invocation"] is None
            if input_kind == "text" and not stream:
                rejected = await e2e_client.post(
                    f"/api/v1/agents/sessions/{session_id}/events",
                    headers={**e2e_headers, "Idempotency-Key": str(uuid.uuid4())},
                    json={
                        "events": [
                            {
                                "type": "agent.session.input.message",
                                "input": [_message("invalid")],
                                "evaluation": {"dataset_name": "removed"},
                            }
                        ]
                    },
                )
                assert rejected.status_code == 422, rejected.text
                assert await conn.fetchval("SELECT count(*) FROM agent_inputs WHERE thread_id=$1", session_id) == 1
        finally:
            await conn.close()
    finally:
        if session_id:
            await archive_public_thread(e2e_client, e2e_headers, session_id, turn_id=turn_id)
        await delete_agent(e2e_client, e2e_headers, slug)


async def test_concurrent_thread_session_creation_replays_one_receipt(e2e_client, e2e_headers):
    """两条入口并发穿过回执预检后，唯一约束冲突仍须重放同一接收事实。"""
    directory_name = f"pytest-thread-race-{uuid.uuid4().hex[:10]}"
    project_id = None
    blocker = None
    observer = None
    blocked_transaction = None
    requests = []
    try:
        directory = await e2e_client.post(
            "/api/workspace/directory",
            headers=e2e_headers,
            json={"parent_path": "/", "name": directory_name},
        )
        assert directory.status_code == 200, directory.text
        project = await e2e_client.post(
            "/api/projects",
            headers=e2e_headers,
            json={
                "request_id": f"thread-race-project-{uuid.uuid4()}",
                "name": make_test_session_title("thread-race-project"),
                "workdir": {"mode": "linked", "path": directory_name},
            },
        )
        assert project.status_code == 200, project.text
        project_id = str(project.json()["id"])
        directory = await e2e_client.get("/api/v1/agents", headers=e2e_headers)
        assert directory.status_code == 200, directory.text
        agent = directory.json()["data"][0]
        agent_slug = agent.get("id") or agent.get("slug") or agent["agent_id"]
        key = f"concurrent-thread-create-{uuid.uuid4()}"
        body = {
            "agent_id": agent_slug,
            "project_id": project_id,
            "title": make_test_session_title("thread-create-race"),
        }
        headers = {**e2e_headers, "Idempotency-Key": key}

        blocker = await asyncpg.connect(postgres_dsn())
        observer = await asyncpg.connect(postgres_dsn())
        blocked_transaction = blocker.transaction()
        await blocked_transaction.start()
        await blocker.fetchval("SELECT id FROM projects WHERE id = $1 FOR UPDATE", project_id)
        requests = [asyncio.create_task(e2e_client.post("/api/v1/agents/sessions", headers=headers, json=body)) for _ in range(2)]
        for _ in range(100):
            waiting = await observer.fetchval(
                "SELECT COUNT(*) FROM pg_stat_activity WHERE state = 'active' AND wait_event_type = 'Lock' AND query ILIKE '%projects%'"
            )
            if waiting == 2:
                break
            await asyncio.sleep(0.1)
        assert waiting == 2, "两条创建请求未同时到达 Project 锁，无法证明冲突路径"
        await blocked_transaction.commit()
        blocked_transaction = None
        first, second = await asyncio.wait_for(asyncio.gather(*requests), timeout=30)
        assert (first.status_code, second.status_code) == (201, 201), (first.text, second.text)
        assert first.json()["id"] == second.json()["id"]
        assert first.json()["yuxi"]["receipt"]["event_id"] == second.json()["yuxi"]["receipt"]["event_id"]

        counts = await blocker.fetchrow(
            "SELECT "
            "(SELECT COUNT(*) FROM sessions WHERE thread_id = $1) AS threads, "
            "(SELECT COUNT(*) FROM agent_input_receipts WHERE thread_id = $1) AS receipts, "
            "(SELECT COUNT(*) FROM agent_inputs WHERE thread_id = $1) AS inputs, "
            "(SELECT COUNT(*) FROM agent_turns WHERE thread_id = $1) AS turns, "
            "(SELECT COUNT(*) FROM agent_runs WHERE thread_id = $1) AS runs",
            first.json()["id"],
        )
        assert dict(counts) == {"threads": 1, "receipts": 1, "inputs": 0, "turns": 0, "runs": 0}
        conflict = await e2e_client.post("/api/v1/agents/sessions", headers=headers, json={**body, "title": "different intent"})
        assert conflict.status_code == 409, conflict.text
    finally:
        for request in requests:
            if not request.done():
                request.cancel()
        if blocked_transaction is not None:
            await blocked_transaction.rollback()
        if blocker is not None:
            await blocker.close()
        if observer is not None:
            await observer.close()
        if project_id is not None:
            deleted = await e2e_client.delete(f"/api/projects/{project_id}", headers=e2e_headers)
            assert deleted.status_code == 200, deleted.text
        removed = await e2e_client.request("DELETE", "/api/workspace/file", headers=e2e_headers, params={"path": directory_name})
        assert removed.status_code in {200, 404}, removed.text


async def test_first_input_and_follow_up_fifo_cross_worker(e2e_client, e2e_headers):
    """第一输入完成后领取排队输入，PG 与 Public 快照都保持固定因果归属。"""
    me = await e2e_client.get("/api/auth/me", headers=e2e_headers)
    assert me.status_code == 200, me.text
    await _provider(e2e_client, e2e_headers)
    slug = await _agent(e2e_client, e2e_headers, str(me.json()["uid"]))
    gate = str(uuid.uuid4())
    creation_key = f"lifecycle-{uuid.uuid4().hex}"
    title = make_test_session_title("lifecycle-fifo")
    try:
        created = await e2e_client.post(
            "/api/v1/agents/sessions",
            headers={**e2e_headers, "Idempotency-Key": creation_key},
            json={
                "agent_id": slug,
                "title": title,
                "agent": {"model": MODEL},
                "tool_approval_mode": "default",
                "input": [_message(f"只输出 {OUTPUT} DETERMINISTIC_BLOCK_BEFORE_RESPONSE:{gate}")],
            },
        )
        assert created.status_code == 201, created.text
        receipt = created.json()["yuxi"]["receipt"]
        first = await wait_for_consumed_input(e2e_client, e2e_headers, receipt)
        thread_id = first["session_id"]
        recovered = await e2e_client.get(
            f"/api/v1/agents/sessions/{thread_id}/receipt",
            headers=e2e_headers,
            params={"idempotency_key": creation_key},
        )
        assert recovered.status_code == 200 and recovered.json() == receipt
        replay = await e2e_client.post(
            "/api/v1/agents/sessions",
            headers={**e2e_headers, "Idempotency-Key": creation_key},
            json={
                "agent_id": slug,
                "title": title,
                "agent": {"model": MODEL},
                "tool_approval_mode": "default",
                "input": [_message(f"只输出 {OUTPUT} DETERMINISTIC_BLOCK_BEFORE_RESPONSE:{gate}")],
            },
        )
        assert replay.status_code == 201, replay.text
        assert replay.json()["id"] == thread_id

        async with httpx.AsyncClient(base_url=os.environ["OPENAI_REPLAY_URL"].removesuffix("/v1"), timeout=5) as replay_client:
            await wait_for_blocked_response(replay_client, gate, timeout=10)

            queued = await e2e_client.post(
                f"/api/v1/agents/sessions/{thread_id}/events",
                headers={**e2e_headers, "Idempotency-Key": f"next-{uuid.uuid4().hex}"},
                json={
                    "events": [
                        {
                            "type": "agent.session.input.message",
                            "input": [_message(OUTPUT)],
                            "yuxi": {"mode": "follow_up"},
                        }
                    ]
                },
            )
            assert queued.status_code == 202, queued.text
            next_input = queued.json()
            assert next_input["input_id"] and next_input["turn_id"] is None and next_input["run_id"] is None
            queue = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/queue", headers=e2e_headers)
            assert queue.status_code == 200, queue.text
            assert [item["input_id"] for item in queue.json()["inputs"]] == [next_input["input_id"]]
            history = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/items?order=asc&limit=100", headers=e2e_headers)
            assert history.status_code == 200, history.text
            assert not any(item["yuxi"].get("input_id") == next_input["input_id"] for item in history.json()["data"])
            changed = await e2e_client.post(
                f"/api/v1/agents/sessions/{thread_id}",
                headers=e2e_headers,
                json={"yuxi": {"tool_approval_mode": "always_trust"}},
            )
            assert changed.status_code == 200, changed.text
            assert changed.json()["yuxi"]["tool_approval_mode"] == "always_trust"
            conn = await asyncpg.connect(postgres_dsn())
            try:
                frozen = await conn.fetchval("SELECT input_payload FROM agent_inputs WHERE id = $1", next_input["input_id"])
            finally:
                await conn.close()
            frozen = json.loads(frozen) if isinstance(frozen, str) else frozen
            assert frozen["context_snapshot"]["tool_approval_mode"] == "default"
            assert frozen["context_snapshot"]["model"] == MODEL
            released = await replay_client.get("/release-blocking", params={"token": gate})
            assert released.status_code == 200

        first_turn = await _turn(e2e_client, e2e_headers, thread_id, first["turn_id"])
        assert first_turn["status"] == "completed", first_turn
        assert first_turn["yuxi"]["result_run_id"] == first["run_id"]
        assert OUTPUT in output_text(first_turn["yuxi"]["output"])
        run_snapshot = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/runs/{first['run_id']}", headers=e2e_headers)
        assert run_snapshot.status_code == 200, run_snapshot.text
        assert run_snapshot.json()["thread_id"] == thread_id
        assert "conversation_thread_id" not in run_snapshot.json()
        assert "conversation_id" not in run_snapshot.json()
        assert first_turn["yuxi"]["usage"]["complete"] is True
        assert first_turn["yuxi"]["usage"]["total_tokens"] == (
            first_turn["yuxi"]["usage"]["input_tokens"] + first_turn["yuxi"]["usage"]["output_tokens"]
        )
        conn = await asyncpg.connect(postgres_dsn())
        try:
            model_facts = await conn.fetch(
                "SELECT id, message_type, operation_id, usage FROM messages WHERE run_id = $1 AND role = "
                "'assistant' AND operation_id IS NOT NULL ORDER BY id",
                first["run_id"],
            )
            tool_count = await conn.fetchval(
                "SELECT COUNT(*) FROM messages WHERE run_id = $1 AND message_type = 'tool_audit'",
                first["run_id"],
            )
            run_count = await conn.fetchval("SELECT COUNT(*) FROM agent_runs WHERE turn_id = $1", first["turn_id"])
            output_message_id = await conn.fetchval("SELECT output_message_id FROM agent_runs WHERE id = $1", first["run_id"])
        finally:
            await conn.close()
        assert len(model_facts) == 2 and tool_count >= 1 and run_count == 1
        assert [row["message_type"] for row in model_facts] == ["model_audit", "text"]
        assert model_facts[-1]["id"] == output_message_id
        assert model_facts[0]["operation_id"] != model_facts[1]["operation_id"]
        assert first_turn["yuxi"]["usage"]["operations"] == len(model_facts)
        consumed = await wait_for_consumed_input(e2e_client, e2e_headers, next_input, timeout=20)
        second_turn = await _turn(e2e_client, e2e_headers, thread_id, consumed["turn_id"])
        assert second_turn["status"] == "completed", second_turn
        assert second_turn["yuxi"]["result_run_id"] == consumed["run_id"]
        assert OUTPUT in output_text(second_turn["yuxi"]["output"])
        assert second_turn["id"] != first_turn["id"]
        conn = await asyncpg.connect(postgres_dsn())
        try:
            claimed = await conn.fetchval("SELECT input_payload FROM agent_runs WHERE id = $1", consumed["run_id"])
        finally:
            await conn.close()
        claimed = json.loads(claimed) if isinstance(claimed, str) else claimed
        assert claimed["context_snapshot"]["tool_approval_mode"] == "default"
        assert claimed["context_snapshot"]["model"] == MODEL

        streamed = []
        cursors = {}
        cursor = None
        async with e2e_client.stream("GET", f"/api/v1/agents/sessions/{thread_id}/events", headers=e2e_headers) as response:
            assert response.status_code == 200, await response.aread()
            async for cursor, event in read_events(response):
                cursors[event["event_id"]] = cursor
                streamed.append(event)
                if event["type"] == "agent.session.turn.completed" and event["turn_id"] == second_turn["id"]:
                    break
        terminal_events = [event for event in streamed if event["type"] == "agent.session.turn.completed"]
        assert [event["turn_id"] for event in terminal_events] == [first_turn["id"], second_turn["id"]]
        assert [event["input_ids"] for event in streamed if event["type"] == "yuxi.session.run.created"] == [
            [first["input_id"]],
            [next_input["input_id"]],
        ]
        resumed = []
        async with e2e_client.stream(
            "GET",
            f"/api/v1/agents/sessions/{thread_id}/events",
            headers={**e2e_headers, "Last-Event-ID": cursors[terminal_events[0]["event_id"]]},
        ) as response:
            assert response.status_code == 200, await response.aread()
            async for cursor, event in read_events(response):
                cursors[event["event_id"]] = cursor
                resumed.append(event)
                if event["type"] == "agent.session.turn.completed":
                    break
        assert [event["turn_id"] for event in resumed if event["type"] == "agent.session.turn.completed"] == [second_turn["id"]]
        first_delta = next(
            event
            for event in streamed
            if event["type"] == "agent.session.turn.output_text.delta" and event["yuxi"]["run_id"] == first["run_id"]
        )
        redis = await get_redis_client()
        await redis.delete(f"run:events:v2:{first['run_id']}")
        async with e2e_client.stream(
            "GET",
            f"/api/v1/agents/sessions/{thread_id}/events",
            headers={**e2e_headers, "Last-Event-ID": cursors[first_delta["event_id"]]},
        ) as response:
            assert response.status_code == 200, await response.aread()
            async for cursor, event in read_events(response):
                cursors[event["event_id"]] = cursor
                if event["type"] == "yuxi.session.resync":
                    assert event["reason"] == "run_events_expired"
                    snapshot = await e2e_client.get(
                        f"/api/v1/agents/sessions/{thread_id}/turns/{first_turn['id']}/items?order=asc&limit=100",
                        headers=e2e_headers,
                    )
                    assert OUTPUT in output_text(snapshot.json()["data"])
                    assert {item["turn_id"] for item in snapshot.json()["data"]} == {first_turn["id"]}
                    break
            else:
                pytest.fail("Redis 增量过期后未发送持久快照 resync")

        rejected = await e2e_client.get(
            f"/api/v1/agents/sessions/{thread_id}/turns/{second_turn['id']}/items",
            headers=e2e_headers,
            params={"after": first_turn["yuxi"]["output"][0]["id"]},
        )
        assert rejected.status_code == 400 and "当前 Turn" in rejected.json()["detail"]
        turns = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/turns", headers=e2e_headers, params={"limit": 1})
        assert turns.json()["data"][0]["id"] == second_turn["id"] and turns.json()["has_more"]

        pg = await asyncpg.connect(postgres_dsn())
        try:
            rows = await pg.fetch(
                "SELECT id, turn_id, consumed_run_id, status FROM agent_inputs WHERE thread_id = $1 ORDER BY received_seq",
                thread_id,
            )
            assert [(row["id"], row["turn_id"], row["consumed_run_id"], row["status"]) for row in rows] == [
                (first["input_id"], first["turn_id"], first["run_id"], "consumed"),
                (next_input["input_id"], consumed["turn_id"], consumed["run_id"], "consumed"),
            ]
        finally:
            await pg.close()
    finally:
        async with httpx.AsyncClient(base_url=os.environ["OPENAI_REPLAY_URL"].removesuffix("/v1"), timeout=5) as replay_client:
            await replay_client.get("/release-blocking", params={"token": gate})
        await delete_agent(e2e_client, e2e_headers, slug)
        deleted = await e2e_client.delete("/api/system/model-providers/ci-replay", headers=e2e_headers)
        assert deleted.status_code in {200, 404}, deleted.text


async def test_tool_cycle_without_steer_stays_in_one_run(e2e_client, e2e_headers):
    """工具执行后的第二次模型调用仍属于首段 Run，Turn 用量逐次汇总。"""
    me = await e2e_client.get("/api/auth/me", headers=e2e_headers)
    assert me.status_code == 200, me.text
    await _provider(e2e_client, e2e_headers)
    slug = await _agent(
        e2e_client,
        e2e_headers,
        str(me.json()["uid"]),
        system_prompt_suffix="DETERMINISTIC_LARGE_TOOL_RESULT",
    )
    try:
        created = await e2e_client.post(
            "/api/v1/agents/sessions",
            headers={**e2e_headers, "Idempotency-Key": f"tool-cycle-{uuid.uuid4().hex}"},
            json={
                "agent_id": slug,
                "title": make_test_session_title("lifecycle-tool-cycle"),
                "agent": {"model": MODEL},
                "tool_approval_mode": "always_trust",
                "input": [_message(OUTPUT)],
            },
        )
        assert created.status_code == 201, created.text
        accepted = await wait_for_consumed_input(e2e_client, e2e_headers, created.json()["yuxi"]["receipt"])
        completed = await _turn(e2e_client, e2e_headers, accepted["session_id"], accepted["turn_id"])
        assert completed["status"] == "completed", completed
        assert completed["yuxi"]["result_run_id"] == accepted["run_id"]
        assert OUTPUT in output_text(completed["yuxi"]["output"])
        conn = await asyncpg.connect(postgres_dsn())
        try:
            runs = await conn.fetchval("SELECT COUNT(*) FROM agent_runs WHERE turn_id = $1", accepted["turn_id"])
            model_facts = await conn.fetch(
                "SELECT id, message_type, operation_id, execution_status, usage, content FROM messages "
                "WHERE run_id = $1 AND role = 'assistant' AND operation_id IS NOT NULL ORDER BY id",
                accepted["run_id"],
            )
            output_message_id = await conn.fetchval("SELECT output_message_id FROM agent_runs WHERE id = $1", accepted["run_id"])
            tool_audit = await conn.fetchrow(
                "SELECT execution_status, turn_id FROM messages WHERE run_id = $1 AND message_type = "
                "'tool_audit' AND operation_id = 'call-large-tool-result'",
                accepted["run_id"],
            )
        finally:
            await conn.close()
        assert runs == 1
        assert len(model_facts) == 2 and all(row["execution_status"] == "completed" for row in model_facts)
        assert [row["message_type"] for row in model_facts] == ["model_audit", "text"]
        assert model_facts[-1]["id"] == output_message_id
        assert completed["yuxi"]["usage"] == {
            "available": True,
            "complete": True,
            "operations": 2,
            "missing_operations": 0,
            "input_tokens": 16,
            "output_tokens": 6,
            "total_tokens": 22,
        }
        assert model_facts[0]["operation_id"] != model_facts[1]["operation_id"]
        assert tool_audit and tool_audit["execution_status"] == "completed"
        assert tool_audit["turn_id"] == accepted["turn_id"]
    finally:
        await delete_agent(e2e_client, e2e_headers, slug)
        deleted = await e2e_client.delete("/api/system/model-providers/ci-replay", headers=e2e_headers)
        assert deleted.status_code in {200, 404}, deleted.text


async def test_steer_aggregates_and_yields_into_same_turn(e2e_client, e2e_headers):
    """Steer 合批优先于已排队 follow-up，接续同 Turn 后再领取 follow-up。"""
    me = await e2e_client.get("/api/auth/me", headers=e2e_headers)
    assert me.status_code == 200, me.text
    await _provider(e2e_client, e2e_headers)
    slug = await _agent(e2e_client, e2e_headers, str(me.json()["uid"]))
    gate = str(uuid.uuid4())
    thread_id = None
    try:
        created = await e2e_client.post(
            "/api/v1/agents/sessions",
            headers={**e2e_headers, "Idempotency-Key": f"steer-create-{uuid.uuid4().hex}"},
            json={
                "agent_id": slug,
                "title": make_test_session_title("lifecycle-steer"),
                "agent": {"model": MODEL},
                "input": [_message(f"{OUTPUT} DETERMINISTIC_BLOCK_BEFORE_RESPONSE:{gate}")],
            },
        )
        assert created.status_code == 201, created.text
        initial = await wait_for_consumed_input(e2e_client, e2e_headers, created.json()["yuxi"]["receipt"])
        thread_id = initial["session_id"]
        async with httpx.AsyncClient(base_url=os.environ["OPENAI_REPLAY_URL"].removesuffix("/v1"), timeout=5) as replay_client:
            await wait_for_blocked_response(replay_client, gate, timeout=10)

            follow_up = await e2e_client.post(
                f"/api/v1/agents/sessions/{thread_id}/events",
                headers={**e2e_headers, "Idempotency-Key": f"steer-follow-up-{uuid.uuid4().hex}"},
                json={
                    "events": [
                        {
                            "type": "agent.session.input.message",
                            "input": [_message(f"{OUTPUT} queued F1")],
                            "yuxi": {"mode": "follow_up"},
                        }
                    ]
                },
            )
            assert follow_up.status_code == 202, follow_up.text
            follow_up_id = follow_up.json()["input_id"]
            second_follow_up = await e2e_client.post(
                f"/api/v1/agents/sessions/{thread_id}/events",
                headers={**e2e_headers, "Idempotency-Key": f"second-follow-up-{uuid.uuid4().hex}"},
                json={
                    "events": [
                        {"type": "agent.session.input.message", "input": [_message(f"{OUTPUT} queued F2")], "yuxi": {"mode": "follow_up"}}
                    ]
                },
            )
            assert second_follow_up.status_code == 202, second_follow_up.text
            second_follow_id = second_follow_up.json()["input_id"]

            steer_ids = []
            for text in ("STEER 一：请按新要求回答", "STEER 二：保留之前工具结果"):
                response = await e2e_client.post(
                    f"/api/v1/agents/sessions/{thread_id}/events",
                    headers={**e2e_headers, "Idempotency-Key": f"steer-{uuid.uuid4().hex}"},
                    json={
                        "events": [
                            {
                                "type": "agent.session.input.message",
                                "input": [_message(text)],
                                "yuxi": {"mode": "steer"},
                            }
                        ]
                    },
                )
                assert response.status_code == 202, response.text
                steer_ids.append(response.json()["input_id"])
            assert len(set(steer_ids)) == 2
            steer_input_id = steer_ids[0]
            pending = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/inputs/{steer_input_id}", headers=e2e_headers)
            assert pending.status_code == 200, pending.text
            assert pending.json()["status"] == "pending"
            assert pending.json()["turn_id"] is None
            assert pending.json()["items"] == []
            assert [
                "".join(part["text"] for part in message["content"] if part["type"] == "text") for message in pending.json()["messages"]
            ] == [
                "STEER 一：请按新要求回答",
            ]
            queue = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/queue", headers=e2e_headers)
            assert queue.status_code == 200, queue.text
            assert [item["input_id"] for item in queue.json()["inputs"]] == [*steer_ids, follow_up_id, second_follow_id]
            assert [item["kind"] for item in queue.json()["inputs"]] == ["steer", "steer", "follow_up", "follow_up"]
            released = await replay_client.get("/release-blocking", params={"token": gate})
            assert released.status_code == 200

        for _ in range(100):
            original = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/runs/{initial['run_id']}", headers=e2e_headers)
            assert original.status_code == 200, original.text
            if original.json()["status"] == "yielded":
                break
            await asyncio.sleep(0.2)
        else:
            pytest.fail("旧 Run 未在安全点 yielded")
        consumed = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/inputs/{steer_input_id}", headers=e2e_headers)
        assert consumed.status_code == 200, consumed.text
        assert consumed.json()["status"] == "consumed"
        assert consumed.json()["turn_id"] == initial["turn_id"]
        replacement_id = consumed.json()["run_id"]
        assert replacement_id and replacement_id != initial["run_id"]
        replacement = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/runs/{replacement_id}", headers=e2e_headers)
        assert replacement.status_code == 200, replacement.text
        assert replacement.json()["resume_from_run_id"] == initial["run_id"]
        assert replacement.json()["input_ids"] == steer_ids
        second_steer = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/inputs/{steer_ids[1]}", headers=e2e_headers)
        assert second_steer.json()["run_id"] == replacement_id
        assert second_steer.json()["status"] == "consumed"
        turn = await _turn(e2e_client, e2e_headers, thread_id, initial["turn_id"])
        assert turn["status"] == "completed", turn
        assert turn["yuxi"]["result_run_id"] == replacement_id
        assert OUTPUT in output_text(turn["yuxi"]["output"])
        next_input = await wait_for_consumed_input(e2e_client, e2e_headers, follow_up.json(), timeout=20)
        assert next_input["turn_id"] != initial["turn_id"]
        next_turn = await _turn(e2e_client, e2e_headers, thread_id, next_input["turn_id"])
        assert next_turn["status"] == "completed", next_turn
        assert next_turn["yuxi"]["result_run_id"] == next_input["run_id"]
        assert OUTPUT in output_text(next_turn["yuxi"]["output"])
        last_input = await wait_for_consumed_input(e2e_client, e2e_headers, second_follow_up.json(), timeout=30)
        last_turn = await _turn(e2e_client, e2e_headers, thread_id, last_input["turn_id"])
        assert last_turn["status"] == "completed"
        assert last_input["turn_id"] not in {initial["turn_id"], next_input["turn_id"]}
        conn = await asyncpg.connect(postgres_dsn())
        try:
            projected = await conn.fetch(
                "SELECT source_input_id, created_at, received_at FROM messages WHERE source_input_id=ANY($1::varchar[]) ORDER BY id",
                [initial["input_id"], *steer_ids, follow_up_id, second_follow_id],
            )
            assert [row["source_input_id"] for row in projected] == [initial["input_id"], *steer_ids, follow_up_id, second_follow_id]
            assert all(row["created_at"] >= row["received_at"] for row in projected)
            old_output = await conn.fetchval(
                "SELECT m.created_at FROM messages m JOIN agent_runs r ON r.output_message_id=m.id WHERE r.id=$1", initial["run_id"]
            )
            assert old_output is not None and old_output <= projected[1]["created_at"]
        finally:
            await conn.close()
    finally:
        try:
            async with httpx.AsyncClient(base_url=os.environ["OPENAI_REPLAY_URL"].removesuffix("/v1"), timeout=5) as replay_client:
                await replay_client.get("/release-blocking", params={"token": gate})
        except httpx.HTTPError:
            pass
        await delete_agent(e2e_client, e2e_headers, slug)
        deleted = await e2e_client.delete("/api/system/model-providers/ci-replay", headers=e2e_headers)
        assert deleted.status_code in {200, 404}, deleted.text


async def test_waiting_turn_requires_complete_answers_and_resumes_same_turn(e2e_client, e2e_headers):
    """两个问题必须按等待点完整回答，续跑与结果仍属于原 Turn。"""
    me = await e2e_client.get("/api/auth/me", headers=e2e_headers)
    assert me.status_code == 200, me.text
    await _provider(e2e_client, e2e_headers)
    slug = await _agent(e2e_client, e2e_headers, str(me.json()["uid"]), tools=["ask_user_question"])
    thread_id = None
    turn_id = None
    try:
        created = await e2e_client.post(
            "/api/v1/agents/sessions",
            headers={**e2e_headers, "Idempotency-Key": f"waiting-create-{uuid.uuid4().hex}"},
            json={
                "agent_id": slug,
                "title": make_test_session_title("lifecycle-waiting"),
                "agent": {"model": MODEL},
                "input": [_message(f"{OUTPUT} DETERMINISTIC_ASK_USER")],
            },
        )
        assert created.status_code == 201, created.text
        initial = await wait_for_consumed_input(e2e_client, e2e_headers, created.json()["yuxi"]["receipt"])
        thread_id = initial["session_id"]
        turn_id = initial["turn_id"]
        for _ in range(100):
            response = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/turns/{turn_id}", headers=e2e_headers)
            assert response.status_code == 200, response.text
            waiting = response.json()
            if waiting["status"] == "requires_action":
                break
            assert waiting["status"] not in {"failed", "cancelled", "completed"}, waiting
            await asyncio.sleep(0.2)
        else:
            pytest.fail("Turn 未进入等待")
        waitpoint = waiting["yuxi"]["waitpoint"]
        waiting_at = datetime.now(UTC)
        assert waitpoint["run_id"] == initial["run_id"]
        assert waitpoint["questions"] == [
            {"question_id": "q-1", "question": "第一题？", "options": [], "multi_select": False, "allow_other": True},
            {"question_id": "q-2", "question": "第二题？", "options": [], "multi_select": False, "allow_other": True},
        ]

        def resume_event(answers: list[dict]) -> dict:
            """构建与等待点绑定的多题回答事件。"""
            return {
                "events": [
                    {
                        "type": "yuxi.session.input.resume",
                        "turn_id": turn_id,
                        "waitpoint_id": waitpoint["id"],
                        "response": {"type": "answer", "answers": answers},
                    }
                ]
            }

        invalid = await e2e_client.post(
            f"/api/v1/agents/sessions/{thread_id}/events",
            headers={**e2e_headers, "Idempotency-Key": f"partial-answer-{uuid.uuid4().hex}"},
            json=resume_event([{"question_id": "q-1", "answer": "是"}]),
        )
        assert invalid.status_code == 422, invalid.text
        still_waiting = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/turns/{turn_id}", headers=e2e_headers)
        assert still_waiting.status_code == 200
        assert still_waiting.json()["status"] == "requires_action"
        resumed_at = datetime.now(UTC)
        accepted = await e2e_client.post(
            f"/api/v1/agents/sessions/{thread_id}/events",
            headers={**e2e_headers, "Idempotency-Key": f"complete-answer-{uuid.uuid4().hex}"},
            json=resume_event(
                [
                    {"question_id": "q-1", "answer": "是"},
                    {"question_id": "q-2", "answer": "继续"},
                ]
            ),
        )
        assert accepted.status_code == 202, accepted.text
        resume_id = accepted.json()["run_id"]
        assert resume_id and resume_id != initial["run_id"]
        conn = await asyncpg.connect(postgres_dsn())
        try:
            resume_message = await conn.fetchrow(
                "SELECT m.run_id, m.turn_id, m.message_type, c.thread_id FROM agent_runs r "
                "JOIN messages m ON m.id = r.input_message_id AND m.session_record_id = r.session_record_id "
                "JOIN sessions c ON c.id = m.session_record_id WHERE r.id = $1",
                resume_id,
            )
            assert resume_message is not None
            assert dict(resume_message) == {
                "run_id": resume_id,
                "turn_id": turn_id,
                "message_type": "resume",
                "thread_id": thread_id,
            }
        finally:
            await conn.close()
        completed = await _turn(e2e_client, e2e_headers, thread_id, turn_id)
        assert completed["status"] == "completed", completed
        assert completed["yuxi"]["result_run_id"] == resume_id
        assert completed["yuxi"]["waitpoint"] is None
        assert OUTPUT in output_text(completed["yuxi"]["output"])
        run_response = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/runs/{resume_id}", headers=e2e_headers)
        assert run_response.status_code == 200, run_response.text
        assert run_response.json()["resume_from_run_id"] == initial["run_id"]
        streamed = []
        async with asyncio.timeout(8):
            async with e2e_client.stream("GET", f"/api/v1/agents/sessions/{thread_id}/events", headers=e2e_headers) as response:
                assert response.status_code == 200, await response.aread()
                async for cursor, event in read_events(response):
                    streamed.append(event)
                    if event["type"] == "agent.session.turn.completed":
                        break
        assert any(
            event["type"] == "yuxi.session.run.settled"
            and event["status"] == "interrupted"
            and event["yuxi"]["run_id"] == initial["run_id"]
            for event in streamed
        )
        assert streamed[-1]["type"] == "agent.session.turn.completed"
        assert streamed[-1]["yuxi"]["run_id"] == resume_id
        if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
            langfuse = get_langfuse_client()
            assert langfuse is not None
            conn = await asyncpg.connect(postgres_dsn())
            try:
                turn_trace = await conn.fetchrow("SELECT langfuse_root_observation_id FROM agent_turns WHERE id = $1", turn_id)
                traced_runs = await conn.fetch(
                    "SELECT id, langfuse_trace_id, langfuse_observation_id FROM agent_runs WHERE turn_id = $1 "
                    "AND run_type IN ('chat', 'resume') ORDER BY execution_seq",
                    turn_id,
                )
            finally:
                await conn.close()
            assert [row["id"] for row in traced_runs] == [initial["run_id"], resume_id]
            root_id = turn_trace["langfuse_root_observation_id"]
            trace_id = traced_runs[0]["langfuse_trace_id"]
            assert (
                root_id and trace_id and all(row["langfuse_trace_id"] == trace_id and row["langfuse_observation_id"] for row in traced_runs)
            )
            for _ in range(60):
                observations = await asyncio.to_thread(langfuse.api.observations.get_many, trace_id=trace_id, limit=100)
                by_id = {item.id: item for item in observations.data}
                root = by_id.get(root_id)
                children = [by_id.get(row["langfuse_observation_id"]) for row in traced_runs]
                if root is not None and root.end_time is not None and all(children):
                    break
                await asyncio.sleep(0.5)
            assert root is not None and root.end_time is not None, "Langfuse Turn 根观察未导出"
            assert root.name == "agent.turn" and root.type == "AGENT"
            assert root.start_time <= waiting_at <= resumed_at <= root.end_time
            assert all(child.parent_observation_id == root_id for child in children)
            assert root.start_time <= min(child.start_time for child in children)
            assert root.end_time >= max(child.end_time for child in children)
        replay = await e2e_client.post(
            f"/api/v1/agents/sessions/{thread_id}/events",
            headers={**e2e_headers, "Idempotency-Key": f"late-answer-{uuid.uuid4().hex}"},
            json=resume_event(
                [
                    {"question_id": "q-1", "answer": "是"},
                    {"question_id": "q-2", "answer": "继续"},
                ]
            ),
        )
        assert replay.status_code == 409, replay.text
    finally:
        if thread_id is not None and turn_id is not None:
            current = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/turns/{turn_id}", headers=e2e_headers)
            if current.status_code == 200 and current.json()["yuxi"].get("waitpoint") is not None:
                cancelled = await e2e_client.post(
                    f"/api/v1/agents/sessions/{thread_id}/events",
                    headers={**e2e_headers, "Idempotency-Key": f"waiting-cleanup-{uuid.uuid4().hex}"},
                    json={"events": [{"type": "agent.session.input.cancel", "yuxi": {"turn_id": turn_id}}]},
                )
                assert cancelled.status_code == 202, cancelled.text
        await delete_agent(e2e_client, e2e_headers, slug)
        deleted = await e2e_client.delete("/api/system/model-providers/ci-replay", headers=e2e_headers)
        assert deleted.status_code in {200, 404}, deleted.text


async def test_invalid_question_parameters_return_tool_error_without_waitpoint(e2e_client, e2e_headers, openai_replay_url):
    """真实工具入口拒绝字符串布尔值，工具错误落库且不产生人工等待。"""
    me = await e2e_client.get("/api/auth/me", headers=e2e_headers)
    assert me.status_code == 200, me.text
    provider_id = f"ci-replay-question-{uuid.uuid4().hex[:8]}"
    model_spec = f"{provider_id}:deterministic-chat"
    await _provider(e2e_client, e2e_headers, base_url=openai_replay_url, provider_id=provider_id)
    slug = await _agent(e2e_client, e2e_headers, str(me.json()["uid"]), tools=["ask_user_question"], model_spec=model_spec)
    try:
        created = await e2e_client.post(
            "/api/v1/agents/sessions",
            headers={**e2e_headers, "Idempotency-Key": f"invalid-question-{uuid.uuid4().hex}"},
            json={
                "agent_id": slug,
                "title": make_test_session_title("invalid-question"),
                "agent": {"model": model_spec},
                "input": [_message(f"{OUTPUT} DETERMINISTIC_ASK_USER_INVALID")],
            },
        )
        assert created.status_code == 201, created.text
        accepted = await wait_for_consumed_input(e2e_client, e2e_headers, created.json()["yuxi"]["receipt"])
        for _ in range(150):
            response = await e2e_client.get(
                f"/api/v1/agents/sessions/{accepted['session_id']}/turns/{accepted['turn_id']}",
                headers=e2e_headers,
            )
            assert response.status_code == 200, response.text
            turn = response.json()
            assert turn["yuxi"].get("waitpoint") is None, "非法问题参数不能被兼容解析成等待点"
            if turn["status"] in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.2)
        else:
            pytest.fail("非法工具参数处理未终结")
        assert turn["status"] == "completed" and turn["yuxi"]["waitpoint"] is None, turn
        assert turn["yuxi"]["result_run_id"] == accepted["run_id"] and OUTPUT in output_text(turn["yuxi"]["output"])
        conn = await asyncpg.connect(postgres_dsn())
        try:
            audit = await conn.fetchrow(
                "SELECT execution_status, content, extra_metadata, turn_id FROM messages WHERE run_id = $1 AND message_type = "
                "'tool_audit' AND operation_id = 'call-ask-user'",
                accepted["run_id"],
            )
        finally:
            await conn.close()
        assert audit and audit["execution_status"] == "failed"
        assert audit["turn_id"] == accepted["turn_id"]
        assert audit["content"] == ""
        metadata = json.loads(audit["extra_metadata"])
        assert "ValidationError" in metadata["output"]["content"] or "multi_select" in metadata["output"]["content"]
    finally:
        await delete_agent(e2e_client, e2e_headers, slug)
        deleted = await e2e_client.delete(f"/api/system/model-providers/{provider_id}", headers=e2e_headers)
        assert deleted.status_code in {200, 404}, deleted.text


async def test_cancel_waiting_turn_pauses_queue_until_continue(e2e_client, e2e_headers):
    """取消等待点仅清理旧 checkpoint，保留 FIFO 输入并要求显式继续。"""
    me = await e2e_client.get("/api/auth/me", headers=e2e_headers)
    assert me.status_code == 200, me.text
    await _provider(e2e_client, e2e_headers)
    slug = await _agent(e2e_client, e2e_headers, str(me.json()["uid"]), tools=["ask_user_question"])
    gate = str(uuid.uuid4())
    thread_id = None
    turn_id = None
    try:
        created = await e2e_client.post(
            "/api/v1/agents/sessions",
            headers={**e2e_headers, "Idempotency-Key": f"cancel-create-{uuid.uuid4().hex}"},
            json={
                "agent_id": slug,
                "title": make_test_session_title("lifecycle-cancel-waiting"),
                "agent": {"model": MODEL},
                "input": [_message(f"{OUTPUT} DETERMINISTIC_ASK_USER DETERMINISTIC_BLOCK_BEFORE_RESPONSE:{gate}")],
            },
        )
        assert created.status_code == 201, created.text
        initial = await wait_for_consumed_input(e2e_client, e2e_headers, created.json()["yuxi"]["receipt"])
        thread_id, turn_id = initial["session_id"], initial["turn_id"]
        async with httpx.AsyncClient(base_url=os.environ["OPENAI_REPLAY_URL"].removesuffix("/v1"), timeout=5) as replay_client:
            await wait_for_blocked_response(replay_client, gate)
            queued = await e2e_client.post(
                f"/api/v1/agents/sessions/{thread_id}/events",
                headers={**e2e_headers, "Idempotency-Key": f"cancel-followup-{uuid.uuid4().hex}"},
                json={
                    "events": [
                        {
                            "type": "agent.session.input.message",
                            "input": [_message(f"{OUTPUT} DETERMINISTIC_CANCEL_FOLLOWUP")],
                            "yuxi": {"mode": "follow_up"},
                        }
                    ]
                },
            )
            assert queued.status_code == 202, queued.text
            queued_id = queued.json()["input_id"]
            released = await replay_client.get("/release-blocking", params={"token": gate})
            assert released.status_code == 200
        for _ in range(100):
            response = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/turns/{turn_id}", headers=e2e_headers)
            assert response.status_code == 200, response.text
            waiting = response.json()
            if waiting["status"] == "requires_action":
                break
            await asyncio.sleep(0.2)
        else:
            pytest.fail("Turn 未进入等待")

        cancelled = await e2e_client.post(
            f"/api/v1/agents/sessions/{thread_id}/events",
            headers={**e2e_headers, "Idempotency-Key": f"cancel-turn-{uuid.uuid4().hex}"},
            json={"events": [{"type": "agent.session.input.cancel", "yuxi": {"turn_id": turn_id}}]},
        )
        assert cancelled.status_code == 202, cancelled.text
        first_turn = await _turn(e2e_client, e2e_headers, thread_id, turn_id)
        assert first_turn["status"] == "cancelled"
        assert first_turn["yuxi"]["result_run_id"] is None
        state = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/state", headers=e2e_headers)
        assert state.status_code == 200, state.text
        assert "interrupt" not in state.json()
        queue = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/queue", headers=e2e_headers)
        assert queue.status_code == 200, queue.text
        assert queue.json()["queue_paused"] is True
        assert [item["input_id"] for item in queue.json()["inputs"]] == [queued_id]
        late = await e2e_client.post(
            f"/api/v1/agents/sessions/{thread_id}/events",
            headers={**e2e_headers, "Idempotency-Key": f"cancel-late-{uuid.uuid4().hex}"},
            json={
                "events": [
                    {
                        "type": "yuxi.session.input.resume",
                        "turn_id": turn_id,
                        "waitpoint_id": waiting["yuxi"]["waitpoint"]["id"],
                        "response": {
                            "type": "answer",
                            "answers": [
                                {"question_id": "q-1", "answer": "是"},
                                {"question_id": "q-2", "answer": "继续"},
                            ],
                        },
                    }
                ]
            },
        )
        assert late.status_code == 409, late.text

        await _continue_queued_input(e2e_client, e2e_headers, queued.json(), "cancel-continue")
    finally:
        try:
            async with httpx.AsyncClient(base_url=os.environ["OPENAI_REPLAY_URL"].removesuffix("/v1"), timeout=5) as replay_client:
                await replay_client.get("/release-blocking", params={"token": gate})
        except httpx.HTTPError:
            pass
        if thread_id is not None and turn_id is not None:
            current = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/turns/{turn_id}", headers=e2e_headers)
            if current.status_code == 200 and current.json()["yuxi"].get("waitpoint") is not None:
                await e2e_client.post(
                    f"/api/v1/agents/sessions/{thread_id}/events",
                    headers={**e2e_headers, "Idempotency-Key": f"cancel-cleanup-{uuid.uuid4().hex}"},
                    json={"events": [{"type": "agent.session.input.cancel", "yuxi": {"turn_id": turn_id}}]},
                )
        await delete_agent(e2e_client, e2e_headers, slug)
        deleted = await e2e_client.delete("/api/system/model-providers/ci-replay", headers=e2e_headers)
        assert deleted.status_code in {200, 404}, deleted.text


@pytest.mark.parametrize("with_queue", [False, True])
async def test_cancel_running_model_closes_audit_without_foreign_output(e2e_client, e2e_headers, with_queue):
    """模型响应中途取消仍关闭唯一 Model 审计并保留当前 Run trace。"""
    me = await e2e_client.get("/api/auth/me", headers=e2e_headers)
    assert me.status_code == 200, me.text
    await _provider(e2e_client, e2e_headers)
    token = str(uuid.uuid4())
    slug = await _agent(
        e2e_client,
        e2e_headers,
        str(me.json()["uid"]),
        system_prompt_suffix=f"DETERMINISTIC_BLOCK_BEFORE_RESPONSE:{token}",
    )
    thread_id = turn_id = run_id = None
    try:
        created = await e2e_client.post(
            "/api/v1/agents/sessions",
            headers={**e2e_headers, "Idempotency-Key": f"cancel-model-{uuid.uuid4().hex}"},
            json={
                "agent_id": slug,
                "title": make_test_session_title("lifecycle-cancel-model"),
                "agent": {"model": MODEL},
                "input": [_message(OUTPUT)],
            },
        )
        assert created.status_code == 201, created.text
        consumed = await wait_for_consumed_input(e2e_client, e2e_headers, created.json()["yuxi"]["receipt"])
        thread_id, turn_id, run_id = consumed["session_id"], consumed["turn_id"], consumed["run_id"]
        async with httpx.AsyncClient(base_url=os.environ["OPENAI_REPLAY_URL"].removesuffix("/v1"), timeout=5) as replay:
            await wait_for_blocked_response(replay, token, timeout=10)

        conn = await asyncpg.connect(postgres_dsn())
        try:
            for _ in range(100):
                audit_status = await conn.fetchval(
                    "SELECT execution_status FROM messages WHERE run_id = $1 AND message_type = 'model_audit'",
                    run_id,
                )
                if audit_status == "running":
                    break
                await asyncio.sleep(0.1)
            else:
                pytest.fail("取消前没有持久的 running Model 审计")
        finally:
            await conn.close()

        queued_id = None
        if with_queue:
            queued = await e2e_client.post(
                f"/api/v1/agents/sessions/{thread_id}/events",
                headers={**e2e_headers, "Idempotency-Key": f"old-queue-{uuid.uuid4().hex}"},
                json={
                    "events": [
                        {
                            "type": "agent.session.input.message",
                            "input": [_message(f"{OUTPUT} DETERMINISTIC_CANCEL_FOLLOWUP")],
                            "yuxi": {"mode": "steer"},
                        }
                    ]
                },
            )
            assert queued.status_code == 202, queued.text
            queued_id = queued.json()["input_id"]
        cancelled = await e2e_client.post(
            f"/api/v1/agents/sessions/{thread_id}/events",
            headers={**e2e_headers, "Idempotency-Key": f"cancel-model-control-{uuid.uuid4().hex}"},
            json={"events": [{"type": "agent.session.input.cancel", "yuxi": {"turn_id": turn_id}}]},
        )
        assert cancelled.status_code == 202, cancelled.text
        terminal = await _turn(e2e_client, e2e_headers, thread_id, turn_id, timeout=10)
        assert terminal["status"] == "cancelled", terminal
        conn = await asyncpg.connect(postgres_dsn())
        try:
            run = await conn.fetchrow(
                "SELECT langfuse_trace_id, output_message_id, first_model_request_at FROM agent_runs WHERE id = $1",
                run_id,
            )
            audits = await conn.fetch(
                "SELECT turn_id, run_id, execution_status FROM messages WHERE run_id = $1 AND message_type = 'model_audit'",
                run_id,
            )
            visible = await conn.fetchval(
                "SELECT COUNT(*) FROM messages WHERE run_id = $1 AND role = 'assistant' AND message_type != 'model_audit'",
                run_id,
            )
        finally:
            await conn.close()
        assert run["first_model_request_at"]
        if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
            assert run["langfuse_trace_id"]
        assert run["output_message_id"] is None and visible == 0
        assert [(row["turn_id"], row["run_id"], row["execution_status"]) for row in audits] == [(turn_id, run_id, "interrupted")]
        queue = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/queue", headers=e2e_headers)
        assert queue.json()["queue_paused"] is with_queue
        async with httpx.AsyncClient(base_url=os.environ["OPENAI_REPLAY_URL"].removesuffix("/v1"), timeout=5) as replay:
            await replay.get("/release-blocking", params={"token": token})
        fresh = await e2e_client.post(
            f"/api/v1/agents/sessions/{thread_id}/events",
            headers={**e2e_headers, "Idempotency-Key": f"new-message-{uuid.uuid4().hex}"},
            json={
                "events": [
                    {
                        "type": "agent.session.input.message",
                        "input": [_message(f"{OUTPUT} DETERMINISTIC_CANCEL_FOLLOWUP new")],
                        "yuxi": {"mode": "follow_up"},
                    }
                ]
            },
        )
        assert fresh.status_code == 202, fresh.text
        consumed = await wait_for_consumed_input(e2e_client, e2e_headers, fresh.json())
        resumed = await _turn(e2e_client, e2e_headers, thread_id, consumed["turn_id"])
        assert resumed["status"] == "completed" and consumed["turn_id"] != turn_id
        if queued_id:
            old = await wait_for_consumed_input(e2e_client, e2e_headers, queued.json())
            assert old["turn_id"] != consumed["turn_id"], "新用户消息不能与旧引导合批"
            assert (await _turn(e2e_client, e2e_headers, thread_id, old["turn_id"]))["status"] == "completed"
            conn = await asyncpg.connect(postgres_dsn())
            try:
                assert await conn.fetchval(
                    "SELECT (SELECT consumed_at FROM agent_inputs WHERE id=$1) < (SELECT consumed_at FROM agent_inputs WHERE id=$2)",
                    fresh.json()["input_id"],
                    queued_id,
                )
            finally:
                await conn.close()
    finally:
        async with httpx.AsyncClient(base_url=os.environ["OPENAI_REPLAY_URL"].removesuffix("/v1"), timeout=5) as replay:
            await replay.get("/release-blocking", params={"token": token})
        if thread_id is not None and turn_id is not None:
            current = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/turns/{turn_id}", headers=e2e_headers)
            if current.status_code == 200 and current.json()["status"] in {"running", "waiting", "cancelling"}:
                await e2e_client.post(
                    f"/api/v1/agents/sessions/{thread_id}/events",
                    headers={**e2e_headers, "Idempotency-Key": f"cancel-model-cleanup-{uuid.uuid4().hex}"},
                    json={"events": [{"type": "agent.session.input.cancel", "yuxi": {"turn_id": turn_id}}]},
                )
        await delete_agent(e2e_client, e2e_headers, slug)
        deleted = await e2e_client.delete("/api/system/model-providers/ci-replay", headers=e2e_headers)
        assert deleted.status_code in {200, 404}, deleted.text


async def test_attachment_reads_live_bytes_across_backends(e2e_client, e2e_headers):
    """输入附件由 Project Workdir 持有，文件工具与公开 HTTP 读取同一份字节。"""
    me = await e2e_client.get("/api/auth/me", headers=e2e_headers)
    assert me.status_code == 200, me.text
    uid = str(me.json()["uid"])
    await _provider(e2e_client, e2e_headers)
    slug = await _agent(e2e_client, e2e_headers, uid)
    thread_id = workdir_path = None
    try:
        created = await e2e_client.post(
            "/api/v1/agents/sessions",
            headers={**e2e_headers, "Idempotency-Key": f"attachment-thread-{uuid.uuid4().hex}"},
            json={"agent_id": slug, "title": make_test_session_title("lifecycle-attachment")},
        )
        assert created.status_code == 201, created.text
        thread_id = created.json()["id"]
        conn = await asyncpg.connect(postgres_dsn())
        try:
            workdir_path = await conn.fetchval(
                "SELECT project.workdir_path FROM sessions AS thread JOIN projects AS project ON project.id = "
                "thread.project_id WHERE thread.thread_id = $1",
                thread_id,
            )
        finally:
            await conn.close()
        assert workdir_path
        content = f"attachment persisted {uuid.uuid4()}"
        uploaded = await e2e_client.post(
            "/api/v1/agents/files",
            files={"file": ("source.txt", content.encode(), "text/plain")},
            headers=e2e_headers,
        )
        assert uploaded.status_code == 201, uploaded.text
        accepted = await e2e_client.post(
            f"/api/v1/agents/sessions/{thread_id}/events",
            headers={**e2e_headers, "Idempotency-Key": f"attachment-input-{uuid.uuid4().hex}"},
            json={
                "events": [
                    {
                        "type": "agent.session.input.message",
                        "input": [_message(OUTPUT)],
                        "yuxi": {"mode": "follow_up", "attachment_file_ids": [uploaded.json()["id"]]},
                    }
                ]
            },
        )
        assert accepted.status_code == 202, accepted.text
        assert accepted.json()["turn_id"] is None and accepted.json()["run_id"] is None
        consumed = await wait_for_consumed_input(e2e_client, e2e_headers, accepted.json())
        completed = await _turn(e2e_client, e2e_headers, thread_id, consumed["turn_id"])
        assert completed["status"] == "completed", completed
        [attachment] = (await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/attachments", headers=e2e_headers)).json()["attachments"]
        path = str(attachment["original_path"])
        assert path.startswith(f"/home/user/workspace/{workdir_path}/uploads/")
        sandbox = UserSandboxBackend(uid=uid, workdir_path=workdir_path)
        assert sandbox.read(path).file_data["content"] == content
        edited = f"edited {uuid.uuid4()}"
        assert sandbox.edit(path, content, edited).error is None
        artifact = await e2e_client.get(attachment["original_artifact_url"], headers=e2e_headers)
        assert artifact.status_code == 200 and artifact.text.strip() == edited
        received = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/inputs/{accepted.json()['input_id']}", headers=e2e_headers)
        assert received.status_code == 200, received.text
        user_item = received.json()["items"][0]
        assert user_item["yuxi"]["attachments"][0]["file_id"] == attachment["file_id"]
        assert user_item["yuxi"]["attachments"][0]["input_id"] == accepted.json()["input_id"]
        completed = await _turn(e2e_client, e2e_headers, thread_id, received.json()["turn_id"])
        assert completed["status"] == "completed", completed
        history = (await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/items?order=asc&limit=100", headers=e2e_headers)).json()
        restored = next(item for item in history["data"] if item["id"] == user_item["id"])
        assert restored["yuxi"]["delivery_status"] == "complete"
        assert restored == {**user_item, "yuxi": {**user_item["yuxi"], "delivery_status": "complete"}}
        another_backend = UserSandboxBackend(uid=uid, workdir_path=workdir_path)
        assert another_backend.read(path).file_data["content"] == edited

        removed = await e2e_client.delete(f"/api/v1/agents/sessions/{thread_id}/attachments/{attachment['file_id']}", headers=e2e_headers)
        assert removed.status_code == 200, removed.text
        assert another_backend.read(path).file_data is None
        deleted_input = await e2e_client.get(
            f"/api/v1/agents/sessions/{thread_id}/inputs/{accepted.json()['input_id']}",
            headers=e2e_headers,
        )
        assert deleted_input.status_code == 200, deleted_input.text
        assert deleted_input.json()["attachment_file_ids"] == [attachment["file_id"]]
        assert deleted_input.json()["attachments"] == []
        assert not deleted_input.json()["items"][0]["yuxi"].get("attachments")
        deleted_history = await e2e_client.get(
            f"/api/v1/agents/sessions/{thread_id}/items?order=asc&limit=100",
            headers=e2e_headers,
        )
        assert not next(item for item in deleted_history.json()["data"] if item["id"] == user_item["id"])["yuxi"].get("attachments")
    finally:
        await delete_agent(e2e_client, e2e_headers, slug)
        deleted = await e2e_client.delete("/api/system/model-providers/ci-replay", headers=e2e_headers)
        assert deleted.status_code in {200, 404}, deleted.text


async def test_model_rate_limit_failure_preserves_error_and_queue_can_continue(e2e_client, e2e_headers):
    """模型重试耗尽持久失败，空队列不暂停，下一条用户输入可直接完成。"""
    me = await e2e_client.get("/api/auth/me", headers=e2e_headers)
    assert me.status_code == 200, me.text
    await _provider(e2e_client, e2e_headers)
    slug = await _agent(e2e_client, e2e_headers, str(me.json()["uid"]))
    thread_id = first_turn_id = None
    try:
        created = await e2e_client.post(
            "/api/v1/agents/sessions",
            headers={**e2e_headers, "Idempotency-Key": f"rate-limit-{uuid.uuid4().hex}"},
            json={
                "agent_id": slug,
                "title": make_test_session_title("lifecycle-rate-limit"),
                "agent": {"model": MODEL},
                "input": [_message(f"{OUTPUT} DETERMINISTIC_RATE_LIMIT RATE_LIMIT_FIRST_CALL")],
            },
        )
        assert created.status_code == 201, created.text
        thread_id = created.json()["id"]
        consumed = await wait_for_consumed_input(e2e_client, e2e_headers, created.json()["yuxi"]["receipt"])
        first_turn_id, first_run_id = consumed["turn_id"], consumed["run_id"]
        failed = await _turn(e2e_client, e2e_headers, thread_id, first_turn_id)
        assert failed["status"] == "failed", failed
        first_run = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/runs/{first_run_id}", headers=e2e_headers)
        assert first_run.status_code == 200, first_run.text
        assert first_run.json()["status"] == "failed"
        assert "DETERMINISTIC_RATE_LIMIT" in first_run.json()["error_message"]
        conn = await asyncpg.connect(postgres_dsn())
        try:
            row = await conn.fetchrow(
                "SELECT status, error_message, output_message_id FROM agent_runs WHERE id = $1",
                first_run_id,
            )
            attempts = await conn.fetchval("SELECT COUNT(*) FROM agent_run_attempts WHERE run_id = $1", first_run_id)
            output = await conn.fetchrow("SELECT run_id, turn_id, extra_metadata FROM messages WHERE id = $1", row["output_message_id"])
        finally:
            await conn.close()
        assert row["status"] == "failed" and "DETERMINISTIC_RATE_LIMIT" in row["error_message"]
        assert attempts == 1
        metadata = json.loads(output["extra_metadata"])
        assert output["run_id"] == first_run_id and output["turn_id"] == first_turn_id
        assert metadata["is_error"] is True

        queued = await e2e_client.post(
            f"/api/v1/agents/sessions/{thread_id}/events",
            headers={**e2e_headers, "Idempotency-Key": f"rate-limit-next-{uuid.uuid4().hex}"},
            json={"events": [{"type": "agent.session.input.message", "input": [_message(OUTPUT)], "yuxi": {"mode": "follow_up"}}]},
        )
        assert queued.status_code == 202, queued.text
        assert queued.json()["turn_id"] is None
        queue = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/queue", headers=e2e_headers)
        assert queue.status_code == 200 and queue.json()["queue_paused"] is False
        next_input = await wait_for_consumed_input(e2e_client, e2e_headers, queued.json())
        completed = await _turn(e2e_client, e2e_headers, thread_id, next_input["turn_id"])
        assert completed["status"] == "completed" and next_input["turn_id"] != first_turn_id
    finally:
        if thread_id and first_turn_id:
            current = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/turns/{first_turn_id}", headers=e2e_headers)
            if current.status_code == 200 and current.json()["status"] in {"running", "waiting", "cancelling"}:
                await e2e_client.post(
                    f"/api/v1/agents/sessions/{thread_id}/events",
                    headers={**e2e_headers, "Idempotency-Key": f"rate-limit-cleanup-{uuid.uuid4().hex}"},
                    json={"events": [{"type": "agent.session.input.cancel", "yuxi": {"turn_id": first_turn_id}}]},
                )
        await delete_agent(e2e_client, e2e_headers, slug)
        deleted = await e2e_client.delete("/api/system/model-providers/ci-replay", headers=e2e_headers)
        assert deleted.status_code in {200, 404}, deleted.text


async def test_large_tool_approval_resume_keeps_original_audit(e2e_client, e2e_headers):
    """审批恢复后的大工具结果只由恢复段 Tool 审计写一次，文件仍可读取。"""
    me = await e2e_client.get("/api/auth/me", headers=e2e_headers)
    assert me.status_code == 200, me.text
    uid = str(me.json()["uid"])
    await _provider(e2e_client, e2e_headers)
    slug = await _agent(e2e_client, e2e_headers, uid, system_prompt_suffix="DETERMINISTIC_LARGE_TOOL_RESULT")
    thread_id = turn_id = workdir_path = None
    try:
        created = await e2e_client.post(
            "/api/v1/agents/sessions",
            headers={**e2e_headers, "Idempotency-Key": f"large-tool-{uuid.uuid4().hex}"},
            json={
                "agent_id": slug,
                "title": make_test_session_title("lifecycle-large-tool"),
                "agent": {"model": MODEL},
                "tool_approval_mode": "default",
                "input": [_message(OUTPUT)],
            },
        )
        assert created.status_code == 201, created.text
        consumed = await wait_for_consumed_input(e2e_client, e2e_headers, created.json()["yuxi"]["receipt"])
        thread_id, turn_id, first_run_id = consumed["session_id"], consumed["turn_id"], consumed["run_id"]
        for _ in range(100):
            pending = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/turns/{turn_id}", headers=e2e_headers)
            assert pending.status_code == 200, pending.text
            if pending.json()["status"] == "requires_action":
                break
            assert pending.json()["status"] not in {"failed", "cancelled", "completed"}, pending.text
            await asyncio.sleep(0.2)
        else:
            pytest.fail("大工具结果未进入审批等待")
        waitpoint = pending.json()["yuxi"]["waitpoint"]
        assert waitpoint["run_id"] == first_run_id
        assert len(waitpoint["calls"]) == 1
        approval_call_id = waitpoint["calls"][0]["call_id"]
        assert approval_call_id
        conn = await asyncpg.connect(postgres_dsn())
        try:
            workdir_path = await conn.fetchval(
                "SELECT project.workdir_path FROM sessions AS thread JOIN projects AS project ON project.id = "
                "thread.project_id WHERE thread.thread_id = $1",
                thread_id,
            )
        finally:
            await conn.close()
        assert workdir_path

        unavailable = await e2e_client.delete("/api/system/model-providers/ci-replay", headers=e2e_headers)
        assert unavailable.status_code == 200, unavailable.text
        snapshot = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}", headers=e2e_headers)
        assert snapshot.status_code == 200, snapshot.text
        assert snapshot.json()["yuxi"]["current_turn"]["waitpoint"]["id"] == waitpoint["id"]
        await _provider(e2e_client, e2e_headers)

        response = {"type": "approval", "decisions": [{"call_id": approval_call_id, "decision": "approve"}]}
        resume_body = {
            "events": [
                {
                    "type": "yuxi.session.input.resume",
                    "turn_id": turn_id,
                    "waitpoint_id": waitpoint["id"],
                    "response": response,
                }
            ]
        }
        resume_headers = {**e2e_headers, "Idempotency-Key": f"large-tool-resume-{uuid.uuid4().hex}"}
        resumed = await e2e_client.post(f"/api/v1/agents/sessions/{thread_id}/events", headers=resume_headers, json=resume_body)
        assert resumed.status_code == 202, resumed.text
        resumed_again = await e2e_client.post(f"/api/v1/agents/sessions/{thread_id}/events", headers=resume_headers, json=resume_body)
        assert resumed_again.status_code == 202 and resumed_again.json() == resumed.json()
        resume_run_id = resumed.json()["run_id"]
        assert resume_run_id != first_run_id and resumed.json()["turn_id"] == turn_id
        completed = await _turn(e2e_client, e2e_headers, thread_id, turn_id)
        assert completed["status"] == "completed", completed
        assert completed["yuxi"]["result_run_id"] == resume_run_id
        assert OUTPUT in output_text(completed["yuxi"]["output"])

        conn = await asyncpg.connect(postgres_dsn())
        try:
            runs = await conn.fetch(
                "SELECT id, input_payload, resume_from_run_id FROM agent_runs WHERE turn_id = $1 ORDER BY execution_seq",
                turn_id,
            )
            audit = await conn.fetchrow(
                "SELECT turn_id, run_id, execution_status, content, extra_metadata "
                "FROM messages WHERE run_id = $1 AND message_type = 'tool_audit' "
                "AND operation_id = 'call-large-tool-result'",
                resume_run_id,
            )
        finally:
            await conn.close()
        assert [row["id"] for row in runs] == [first_run_id, resume_run_id]
        assert runs[1]["resume_from_run_id"] == first_run_id
        assert runs[1]["input_payload"] == runs[0]["input_payload"]
        assert audit and audit["turn_id"] == turn_id and audit["run_id"] == resume_run_id
        assert audit["execution_status"] == "completed" and audit["content"] == ""
        metadata = json.loads(audit["extra_metadata"]) if isinstance(audit["extra_metadata"], str) else audit["extra_metadata"]
        assert metadata["tool_name"] == "execute"
        assert len(metadata["output"]["content"]) > 12_000
        offloaded = user_workspace_dir(uid) / workdir_path / "outputs/large_tool_results/call-large-tool-result"
        assert offloaded.is_file()
        assert metadata["output"]["content"] == offloaded.read_text()
    finally:
        if thread_id and turn_id:
            current = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/turns/{turn_id}", headers=e2e_headers)
            if current.status_code == 200 and current.json()["status"] in {"running", "waiting", "cancelling"}:
                await e2e_client.post(
                    f"/api/v1/agents/sessions/{thread_id}/events",
                    headers={**e2e_headers, "Idempotency-Key": f"large-tool-cancel-{uuid.uuid4().hex}"},
                    json={"events": [{"type": "agent.session.input.cancel", "yuxi": {"turn_id": turn_id}}]},
                )
        await delete_agent(e2e_client, e2e_headers, slug)
        deleted = await e2e_client.delete("/api/system/model-providers/ci-replay", headers=e2e_headers)
        assert deleted.status_code in {200, 404}, deleted.text


@pytest.mark.parametrize("creation_stream", [False, True])
async def test_thread_sse_releases_validation_transaction(e2e_client, e2e_headers, creation_stream):
    """等待模型的 SSE 不持有入口 PostgreSQL 空闲事务，普通状态读取仍可进行。"""
    me = await e2e_client.get("/api/auth/me", headers=e2e_headers)
    assert me.status_code == 200, me.text
    await _provider(e2e_client, e2e_headers)
    token = str(uuid.uuid4())
    slug = await _agent(
        e2e_client,
        e2e_headers,
        str(me.json()["uid"]),
        system_prompt_suffix=f"DETERMINISTIC_BLOCK_BEFORE_RESPONSE:{token}",
    )
    thread_id = turn_id = None
    try:
        key = f"sse-transaction-{uuid.uuid4().hex}"
        body = {
            "agent_id": slug,
            "title": make_test_session_title("lifecycle-sse-transaction"),
            "agent": {"model": MODEL},
            "input": [_message(OUTPUT)],
        }
        created = await e2e_client.post("/api/v1/agents/sessions", headers={**e2e_headers, "Idempotency-Key": key}, json=body)
        assert created.status_code == 201, created.text
        consumed = await wait_for_consumed_input(e2e_client, e2e_headers, created.json()["yuxi"]["receipt"])
        thread_id, turn_id = consumed["session_id"], consumed["turn_id"]
        async with httpx.AsyncClient(base_url=os.environ["OPENAI_REPLAY_URL"].removesuffix("/v1"), timeout=5) as replay:
            await wait_for_blocked_response(replay, token, timeout=10)

        conn = await asyncpg.connect(postgres_dsn())
        try:
            since = await conn.fetchval("SELECT clock_timestamp()")
            if creation_stream:
                path = "/api/v1/agents/sessions"
                method = "POST"
                kwargs = {"json": {**body, "stream": True}}
                headers = {**e2e_headers, "Idempotency-Key": key}
            else:
                path = f"/api/v1/agents/sessions/{thread_id}/events"
                method = "GET"
                kwargs = {}
                headers = e2e_headers
            async with e2e_client.stream(method, path, headers=headers, **kwargs) as stream:
                assert stream.status_code == (201 if creation_stream else 200)
                assert stream.headers["content-type"].startswith("text/event-stream")
                cutoff = await conn.fetchval("SELECT clock_timestamp()")
                await asyncio.sleep(0.5)
                idle = await conn.fetch(
                    "SELECT pid FROM pg_stat_activity WHERE datname = current_database() "
                    "AND xact_start >= $1 AND xact_start <= $2 AND state = 'idle in transaction' "
                    "AND query ~ '(agent_runs|agent_inputs|sessions)'",
                    since,
                    cutoff,
                )
                assert not idle, f"SSE 持有入口事务: {idle}"
                active = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/turns/{turn_id}", headers=e2e_headers)
                assert active.status_code == 200 and active.json()["status"] == "in_progress"
                assert active.json()["status"] == "in_progress"
        finally:
            await conn.close()
        async with httpx.AsyncClient(base_url=os.environ["OPENAI_REPLAY_URL"].removesuffix("/v1"), timeout=5) as replay:
            assert (await replay.get("/release-blocking", params={"token": token})).status_code == 200
        completed = await _turn(e2e_client, e2e_headers, thread_id, turn_id)
        assert completed["status"] == "completed", completed
    finally:
        async with httpx.AsyncClient(base_url=os.environ["OPENAI_REPLAY_URL"].removesuffix("/v1"), timeout=5) as replay:
            await replay.get("/release-blocking", params={"token": token})
        if thread_id and turn_id:
            current = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/turns/{turn_id}", headers=e2e_headers)
            if current.status_code == 200 and current.json()["status"] in {"running", "waiting", "cancelling"}:
                await e2e_client.post(
                    f"/api/v1/agents/sessions/{thread_id}/events",
                    headers={**e2e_headers, "Idempotency-Key": f"sse-cleanup-{uuid.uuid4().hex}"},
                    json={"events": [{"type": "agent.session.input.cancel", "yuxi": {"turn_id": turn_id}}]},
                )
        await delete_agent(e2e_client, e2e_headers, slug)
        deleted = await e2e_client.delete("/api/system/model-providers/ci-replay", headers=e2e_headers)
        assert deleted.status_code in {200, 404}, deleted.text
