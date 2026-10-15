"""真实供应商经过 shipping API、worker 与 SSE 的手工探针。"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from test.e2e.e2e_helpers import (
    RUN_TIMEOUT_SECONDS,
    archive_public_thread,
    create_public_agent,
    delete_agent,
    output_text,
    public_message,
    skip_if_external_quota,
    wait_for_consumed_input,
)
from test.live_api_cleanup import make_test_session_title
from test.support.public_events import read_events

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e, pytest.mark.slow, pytest.mark.timeout(300)]


async def test_real_provider_streams_persisted_session_result(e2e_client, e2e_headers, e2e_agent_context):
    """真实模型输出经 SSE 到达客户端，并与同一 Run 的持久结果一致。"""
    expected = "REAL_PROVIDER_E2E_OK"
    slug = await create_public_agent(
        e2e_client, e2e_headers, e2e_agent_context["uid"],
        slug_prefix="e2e-provider-", expected_output=expected,
        name_prefix="E2E Provider", description="真实模型协议探针",
    )
    session_id = turn_id = None
    try:
        async with e2e_client.stream(
            "POST", "/api/v1/agents/sessions", headers={**e2e_headers, "Idempotency-Key": str(uuid.uuid4())},
            json={"agent_id": slug, "title": make_test_session_title("provider"),
                  "input": [public_message(f"只回复 {expected}")], "stream": True},
        ) as response:
            assert response.status_code == 201, await response.aread()
            events = read_events(response)
            _, created = await anext(events)
            assert created["type"] == "agent.session.created"
            session = created["session"]
            session_id = session["id"]
            accepted = await wait_for_consumed_input(e2e_client, e2e_headers, session["yuxi"]["receipt"])
            turn_id = accepted["turn_id"]
            chunks = []
            async with asyncio.timeout(RUN_TIMEOUT_SECONDS):
                async for _, event in events:
                    if event["type"] == "agent.session.turn.output_text.delta":
                        chunks.append(event["delta"])
                    if event["type"] in {"agent.session.turn.completed", "agent.session.turn.failed", "agent.session.turn.cancelled"}:
                        assert event["turn_id"] == turn_id
                        if event["type"] == "agent.session.turn.failed":
                            skip_if_external_quota(event["turn"].get("error"))
                        assert event["type"] == "agent.session.turn.completed", event
                        break
                else:
                    pytest.fail("真实供应商流没有终态")
        turn = await e2e_client.get(f"/api/v1/agents/sessions/{session_id}/turns/{turn_id}", headers=e2e_headers)
        assert turn.status_code == 200, turn.text
        result = turn.json()
        assert result["status"] == "completed"
        assert expected in "".join(chunks) and expected in output_text(result["yuxi"]["output"])
        assert result["yuxi"]["result_run_id"] == accepted["run_id"]
        assert all(item["yuxi"]["run_id"] == accepted["run_id"] and item["turn_id"] == turn_id for item in result["yuxi"]["output"])
    finally:
        try:
            if session_id:
                if turn_id is None:
                    input_id = session["yuxi"]["receipt"]["input_id"]
                    cancelled = await e2e_client.post(
                        f"/api/v1/agents/sessions/{session_id}/events",
                        headers={**e2e_headers, "Idempotency-Key": str(uuid.uuid4())},
                        json={"events": [{"type": "yuxi.session.input.cancel_input", "input_id": input_id}]},
                    )
                    assert cancelled.status_code in {202, 409}, cancelled.text
                    snapshot = await e2e_client.get(f"/api/v1/agents/sessions/{session_id}/inputs/{input_id}", headers=e2e_headers)
                    assert snapshot.status_code == 200, snapshot.text
                    turn_id = snapshot.json()["turn_id"]
                await archive_public_thread(e2e_client, e2e_headers, session_id, turn_id=turn_id)
        finally:
            await delete_agent(e2e_client, e2e_headers, slug)
