"""评估调用样例经 Public Thread 进入统一生命周期的端到端验证。"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import asyncpg
import httpx
import pytest

from test.e2e.e2e_helpers import create_public_agent, delete_agent, postgres_dsn, skip_if_external_quota, wait_for_consumed_input
from test.e2e.e2e_helpers import output_text
from test.live_api_cleanup import make_test_session_title

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e, pytest.mark.slow]

POLL_INTERVAL_SECONDS = float(os.getenv("E2E_RUN_POLL_INTERVAL_SECONDS", "2"))
RUN_TIMEOUT_SECONDS = int(os.getenv("E2E_RUN_TIMEOUT_SECONDS", "240"))
EVAL_EXPECTED_OUTPUT = "AGENT_EVAL_E2E_OK"


async def _wait_turn(client: httpx.AsyncClient, headers: dict[str, str], thread_id: str, turn_id: str) -> dict[str, Any]:
    """等待持久 Turn 结果，不依赖旧 Invocation 的同步包装。"""
    deadline = asyncio.get_running_loop().time() + RUN_TIMEOUT_SECONDS
    while asyncio.get_running_loop().time() < deadline:
        response = await client.get(f"/api/v1/agents/sessions/{thread_id}/turns/{turn_id}", headers=headers)
        assert response.status_code == 200, response.text
        turn = response.json()
        if turn["status"] in {"completed", "failed", "cancelled"}:
            return turn
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    pytest.fail(f"Public Turn {turn_id} timed out")


async def _assert_public_origin(*, thread_id: str, turn_id: str, input_id: str, run_id: str, agent_slug: str) -> None:
    """从 PostgreSQL 证明样例由 Public Input 产生且没有旧 Invocation 元数据。"""
    conn = await asyncpg.connect(postgres_dsn())
    try:
        row = await conn.fetchrow(
            """
            SELECT ar.status, ar.run_type, ar.agent_slug, ar.turn_id, ar.input_id,
                   ar.source AS run_source, ar.channel AS run_channel,
                   ai.status AS input_status, ai.consumed_run_id,
                   ai.source AS input_source, ai.channel AS input_channel,
                   at.result_run_id, conv.extra_metadata->>'source' AS thread_source,
                   input_msg.extra_metadata->>'input_id' AS message_input_id,
                   input_msg.extra_metadata->'agent_invocation_meta' IS NOT NULL AS legacy_invocation_meta
            FROM agent_runs ar
            JOIN agent_inputs ai ON ai.id = ar.input_id
            JOIN agent_turns at ON at.id = ar.turn_id
            JOIN sessions conv ON conv.id = ar.session_record_id
            JOIN messages input_msg ON input_msg.id = ar.input_message_id
            WHERE ar.id = $1 AND conv.thread_id = $2
            """,
            run_id,
            thread_id,
        )
        assert row, f"Public Run {run_id} missing"
        assert row["status"] == "completed" and row["run_type"] == "chat"
        assert row["agent_slug"] == agent_slug
        assert row["turn_id"] == turn_id and row["input_id"] == input_id
        assert row["input_status"] == "consumed" and row["consumed_run_id"] == run_id
        assert row["result_run_id"] == run_id
        assert row["run_source"] == row["input_source"] == row["thread_source"] == "public_api"
        assert row["run_channel"] == row["input_channel"] == "web"
        assert row["message_input_id"] == input_id
        assert row["legacy_invocation_meta"] is False
    finally:
        await conn.close()


async def test_public_thread_evaluation_sample_uses_one_input_turn_run_flow(
    e2e_client: httpx.AsyncClient,
    e2e_headers: dict[str, str],
    e2e_agent_context: dict[str, str],
):
    """评估样例仅用 Public 输入、Turn 结果与 Run 快照执行。"""
    agent_slug = await create_public_agent(
        e2e_client,
        e2e_headers,
        e2e_agent_context["uid"],
        slug_prefix="e2e-agent-eval-",
        expected_output=EVAL_EXPECTED_OUTPUT,
        name_prefix="E2E Agent Eval",
        description="真实 Public 评估样例 E2E 临时智能体",
    )
    thread_id: str | None = None
    accepted: dict | None = None
    completed = False
    try:
        create_response = await e2e_client.post(
            "/api/v1/agents/sessions",
            json={
                "agent_id": agent_slug,
                "title": make_test_session_title("agent-eval-e2e"),
                "input": [
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": f"请只输出 {EVAL_EXPECTED_OUTPUT}，不要添加任何解释。"}],
                    }
                ],
            },
            headers={**e2e_headers, "Idempotency-Key": f"eval-{uuid.uuid4().hex}"},
        )
        assert create_response.status_code == 201, create_response.text
        accepted = await wait_for_consumed_input(e2e_client, e2e_headers, create_response.json()["yuxi"]["receipt"])
        thread_id = accepted["session_id"]
        assert accepted["input_id"] and accepted["turn_id"] and accepted["run_id"], accepted

        turn = await _wait_turn(e2e_client, e2e_headers, thread_id, accepted["turn_id"])
        if turn["status"] != "completed":
            skip_if_external_quota(turn.get("error"))
        assert turn["status"] == "completed", turn
        assert turn["yuxi"]["result_run_id"] == accepted["run_id"]
        assert EVAL_EXPECTED_OUTPUT in output_text(turn["yuxi"]["output"])
        assert all(item["yuxi"]["run_id"] == accepted["run_id"] for item in turn["yuxi"]["output"])
        assert all(item["turn_id"] == accepted["turn_id"] for item in turn["yuxi"]["output"])
        completed = True

        run_response = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/runs/{accepted['run_id']}", headers=e2e_headers)
        assert run_response.status_code == 200, run_response.text
        run = run_response.json()
        assert run["status"] == "completed" and run["turn_id"] == accepted["turn_id"]
        assert run["input_id"] == accepted["input_id"]
        assert EVAL_EXPECTED_OUTPUT in output_text(run["output"])

        await _assert_public_origin(
            thread_id=thread_id,
            turn_id=accepted["turn_id"],
            input_id=accepted["input_id"],
            run_id=accepted["run_id"],
            agent_slug=agent_slug,
        )

        invalid = await e2e_client.post(
            f"/api/v1/agents/sessions/{thread_id}/events",
            json={
                "events": [
                    {
                        "type": "agent.session.input.message",
                        "input": [{"role": "user", "content": [{"type": "input_text", "text": "test"}]}],
                        "evaluation": {"dataset_name": "legacy"},
                        "yuxi": {"mode": "follow_up"},
                    }
                ]
            },
            headers={**e2e_headers, "Idempotency-Key": f"invalid-eval-{uuid.uuid4().hex}"},
        )
        assert invalid.status_code == 422, invalid.text
        conn = await asyncpg.connect(postgres_dsn())
        try:
            assert await conn.fetchval("SELECT count(*) FROM agent_inputs WHERE thread_id = $1", thread_id) == 1
        finally:
            await conn.close()
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
                headers={**e2e_headers, "Idempotency-Key": f"eval-cancel-{uuid.uuid4().hex}"},
            )
        await delete_agent(e2e_client, e2e_headers, agent_slug)
