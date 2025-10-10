"""
Integration tests for chat router endpoints.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_chat_endpoints_require_authentication(test_client):
    assert (await test_client.get("/api/chat/default_agent")).status_code == 401
    assert (await test_client.get("/api/chat/agent")).status_code == 401


async def test_admin_can_list_agents(test_client, admin_headers):
    response = await test_client.get("/api/chat/agent", headers=admin_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert isinstance(payload["agents"], list)
    assert "metadata" in payload


async def test_admin_can_read_default_agent(test_client, admin_headers):
    response = await test_client.get("/api/chat/default_agent", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert "default_agent_id" in response.json()


async def test_setting_default_agent_requires_admin(test_client, admin_headers, standard_user):
    # Attempt as admin first to obtain a candidate agent id.
    agents_response = await test_client.get("/api/chat/agent", headers=admin_headers)
    assert agents_response.status_code == 200, agents_response.text
    agents = agents_response.json().get("agents", [])

    if not agents:
        pytest.skip("No agents are registered in the system.")

    candidate_agent_id = agents[0].get("id")
    if not candidate_agent_id:
        pytest.skip("Agent payload missing id field.")

    # Normal user should not be able to update the default agent.
    forbidden_response = await test_client.post(
        "/api/chat/set_default_agent",
        json={"agent_id": candidate_agent_id},
        headers=standard_user["headers"],
    )
    assert forbidden_response.status_code == 403

    # Admin should succeed.
    update_response = await test_client.post(
        "/api/chat/set_default_agent",
        json={"agent_id": candidate_agent_id},
        headers=admin_headers,
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["default_agent_id"] == candidate_agent_id
