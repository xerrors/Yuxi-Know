from __future__ import annotations

import uuid

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_channel_state_command_reads_thread_without_creating_run(test_client, admin_headers):
    agents_response = await test_client.get("/api/agent", headers=admin_headers)
    assert agents_response.status_code == 200, agents_response.text
    agent_slug = agents_response.json()["agents"][0].get("slug") or agents_response.json()["agents"][0].get("agent_id")

    thread_response = await test_client.post(
        "/api/chat/thread",
        json={"agent_id": agent_slug, "title": f"pytest-channel-{uuid.uuid4().hex[:8]}", "metadata": {}},
        headers=admin_headers,
    )
    assert thread_response.status_code == 200, thread_response.text
    thread_id = thread_response.json().get("thread_id") or thread_response.json().get("id")

    response = await test_client.post(
        "/api/agent-invocation/channel/messages",
        json={
            "channel": "cli",
            "account_id": "integration",
            "chat_id": "state-check",
            "thread_id": thread_id,
            "message_id": f"state-{uuid.uuid4().hex}",
            "agent_slug": agent_slug,
            "message": {"type": "text", "text": "/state"},
        },
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["kind"] == "command"
    assert response.json()["command"] == "state"
    assert "agent_state" in response.json()["state"]
