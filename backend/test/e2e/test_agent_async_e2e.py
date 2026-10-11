"""真实 Public Thread 流、Turn 结果与持久归属端到端验证。"""

from __future__ import annotations

import asyncio
import os
import uuid

import asyncpg
import httpx
import pytest

from test.e2e.e2e_helpers import output_text
from test.e2e.e2e_helpers import (
    create_public_agent,
    create_public_thread,
    delete_agent,
    postgres_dsn,
    skip_if_external_quota,
    wait_for_consumed_input,
)
from test.support.public_events import read_events

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e, pytest.mark.slow]

EXPECTED_OUTPUT = "ASYNC_AGENT_E2E_OK"
RUN_TIMEOUT_SECONDS = int(os.getenv("E2E_RUN_TIMEOUT_SECONDS", "240"))


async def _submit_input(client: httpx.AsyncClient, headers: dict[str, str], thread_id: str) -> dict:
    """提交一条 follow_up，保留 Input、Turn 和 Run 回执。"""
    response = await client.post(
        f"/api/v1/agents/sessions/{thread_id}/events",
        json={
            "events": [
                {
                    "type": "agent.session.input.message",
                    "input": [
                        {
                            "role": "user",
                            "content": [{"type": "input_text", "text": f"请只回复 {EXPECTED_OUTPUT}，不要添加任何解释。"}],
                        }
                    ],
                    "yuxi": {"mode": "follow_up"},
                }
            ]
        },
        headers={**headers, "Idempotency-Key": f"async-input-{uuid.uuid4().hex}"},
    )
    assert response.status_code == 202, response.text
    accepted = await wait_for_consumed_input(client, headers, response.json())
    assert accepted["session_id"] == thread_id
    assert accepted["input_id"] and accepted["turn_id"] and accepted["run_id"], accepted
    return accepted


async def _stream_until_terminal(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    thread_id: str,
    turn_id: str,
    *,
    after_cursor: str | None = None,
) -> list[dict]:
    """读取目标 Turn 的结构化 SSE，终态后立即关闭无限流。"""
    stream_headers = {**headers, **({"Last-Event-ID": after_cursor} if after_cursor else {})}
    events: list[dict] = []

    async def consume() -> None:
        async with client.stream("GET", f"/api/v1/agents/sessions/{thread_id}/events", headers=stream_headers) as response:
            assert response.status_code == 200, await response.aread()
            async for cursor, event in read_events(response):
                if event.get("turn_id") != turn_id:
                    continue
                assert event["session_id"] == thread_id
                assert cursor
                event["cursor"] = cursor  # 仅测试附加 SSE envelope，公开 JSON 不含 cursor。
                events.append(event)
                if event["type"] == "agent.session.turn.failed":
                    skip_if_external_quota((event.get("turn", {}).get("error") or {}).get("message"))
                if event["type"] in {
                    "agent.session.turn.completed",
                    "agent.session.turn.failed",
                    "agent.session.turn.cancelled",
                }:
                    return

    await asyncio.wait_for(consume(), timeout=RUN_TIMEOUT_SECONDS)
    assert events and events[-1]["type"].startswith("agent.session.turn."), events
    return events


async def _assert_run_persisted(*, run_id: str, input_id: str, turn_id: str, thread_id: str, agent_slug: str, uid: str) -> None:
    """独立查询 PostgreSQL，核实同一 Input/Turn/Run 的消息归属。"""
    conn = await asyncpg.connect(postgres_dsn())
    try:
        row = await conn.fetchrow(
            """
            SELECT ar.id, ar.status, ar.error_message, ar.run_type, ar.agent_slug, ar.uid,
                   ar.thread_id, ar.turn_id, ar.input_id, ar.session_record_id,
                   ar.input_message_id, ar.output_message_id, ar.created_at, ar.started_at,
                   ar.finished_at, ai.status AS input_status, ai.turn_id AS input_turn_id,
                   ai.consumed_run_id, at.status AS turn_status, at.result_run_id,
                   input_msg.role AS input_role, input_msg.extra_metadata->>'input_id' AS message_input_id,
                   output_msg.role AS output_role, output_msg.run_id AS output_run_id,
                   output_msg.turn_id AS output_turn_id, output_msg.content AS output_content,
                   conv.thread_id AS persisted_thread_id
            FROM agent_runs ar
            JOIN agent_inputs ai ON ai.id = ar.input_id
            JOIN agent_turns at ON at.id = ar.turn_id
            JOIN sessions conv ON conv.id = ar.session_record_id
            LEFT JOIN messages input_msg ON input_msg.id = ar.input_message_id
            LEFT JOIN messages output_msg ON output_msg.id = ar.output_message_id
            WHERE ar.id = $1
            """,
            run_id,
        )
        assert row, f"agent_runs row missing for {run_id}"
        if row["status"] != "completed":
            skip_if_external_quota(row["error_message"])
        assert row["status"] == row["turn_status"] == "completed"
        assert row["run_type"] == "chat"
        assert (row["agent_slug"], row["uid"]) == (agent_slug, uid)
        assert row["thread_id"] == row["persisted_thread_id"] == thread_id
        assert row["turn_id"] == row["input_turn_id"] == turn_id
        assert row["input_id"] == input_id
        assert row["input_status"] == "consumed" and row["consumed_run_id"] == run_id
        assert row["result_run_id"] == run_id
        assert row["input_message_id"] and row["output_message_id"]
        assert row["input_role"] == "user" and row["message_input_id"] == input_id
        assert row["output_role"] == "assistant"
        assert row["output_run_id"] == run_id and row["output_turn_id"] == turn_id
        assert EXPECTED_OUTPUT in row["output_content"]
        assert row["created_at"] <= row["started_at"] <= row["finished_at"]
    finally:
        await conn.close()


async def test_async_agent_run_stream_result_and_persistence(
    e2e_client: httpx.AsyncClient,
    e2e_headers: dict[str, str],
    e2e_agent_context: dict[str, str],
):
    """Public 流、游标重连和 Turn 结果指向同一持久 Run。"""
    uid = e2e_agent_context["uid"]
    agent_slug = await create_public_agent(
        e2e_client,
        e2e_headers,
        uid,
        slug_prefix="e2e-async-agent-",
        expected_output=EXPECTED_OUTPUT,
        name_prefix="E2E 异步 Agent",
        description="真实异步 Agent E2E 临时智能体",
    )
    thread_id: str | None = None
    accepted: dict | None = None
    completed = False
    try:
        thread_id = await create_public_thread(e2e_client, e2e_headers, agent_slug, tag="agent-async-e2e")
        accepted = await _submit_input(e2e_client, e2e_headers, thread_id)
        run_id, turn_id, input_id = accepted["run_id"], accepted["turn_id"], accepted["input_id"]

        streamed = await _stream_until_terminal(e2e_client, e2e_headers, thread_id, turn_id)
        assert any(
            event["type"] == "agent.session.turn.output_text.delta" and event.get("yuxi", {}).get("run_id") == run_id for event in streamed
        )
        assert streamed[-1]["type"] == "agent.session.turn.completed", streamed[-1]
        assert streamed[-1]["yuxi"]["run_id"] == run_id and streamed[-1]["yuxi"]["input_id"] == input_id

        turn_response = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/turns/{turn_id}", headers=e2e_headers)
        assert turn_response.status_code == 200, turn_response.text
        turn = turn_response.json()
        if turn["status"] != "completed":
            skip_if_external_quota(turn.get("error"))
        assert turn["status"] == "completed", turn
        assert turn["yuxi"]["result_run_id"] == run_id
        assert EXPECTED_OUTPUT in output_text(turn["yuxi"]["output"])

        run_response = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/runs/{run_id}", headers=e2e_headers)
        assert run_response.status_code == 200, run_response.text
        run = run_response.json()
        assert run["status"] == "completed" and run["turn_id"] == turn_id
        assert run["input_id"] == input_id and all(item["yuxi"]["run_id"] == run_id for item in run["output"])

        history_response = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/items?order=asc&limit=100", headers=e2e_headers)
        assert history_response.status_code == 200, history_response.text
        history = history_response.json()
        assert any(item["yuxi"].get("input_id") == input_id and item["turn_id"] == turn_id for item in history["data"])
        assert any(
            item["yuxi"]["run_id"] == run_id and item["turn_id"] == turn_id and EXPECTED_OUTPUT in output_text([item])
            for item in history["data"]
            if item["type"] == "message" and item["role"] == "assistant"
        )
        assert any(item["id"] == run_id and item["turn_id"] == turn_id for item in history["yuxi"]["runs"])

        await _assert_run_persisted(
            run_id=run_id,
            input_id=input_id,
            turn_id=turn_id,
            thread_id=thread_id,
            agent_slug=agent_slug,
            uid=uid,
        )

        first_cursor = next(event["cursor"] for event in streamed if event["type"] == "agent.session.turn.output_text.delta")
        replayed = await _stream_until_terminal(e2e_client, e2e_headers, thread_id, turn_id, after_cursor=first_cursor)
        assert replayed[-1]["type"] == "agent.session.turn.completed"
        assert replayed[-1]["yuxi"]["run_id"] == run_id and replayed[-1]["yuxi"]["input_id"] == input_id
        completed = True
    finally:
        if accepted and thread_id and not completed:
            await e2e_client.post(
                f"/api/v1/agents/sessions/{thread_id}/events",
                json={
                    "events": [
                        {
                            "type": "agent.session.input.cancel",
                            "yuxi": {"turn_id": accepted["turn_id"], "expected_run_id": accepted["run_id"]},
                        }
                    ]
                },
                headers={**e2e_headers, "Idempotency-Key": f"async-cancel-{uuid.uuid4().hex}"},
            )
        await delete_agent(e2e_client, e2e_headers, agent_slug)
