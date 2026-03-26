"""
Integration tests for batch question resume payload validation.
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _get_agent_id(test_client, headers):
    """Get an agent ID for testing."""
    agents_response = await test_client.get("/api/chat/agent", headers=headers)
    if agents_response.status_code != 200:
        pytest.skip(f"Failed to get agents: {agents_response.text}")
    agents = agents_response.json().get("agents", [])
    if not agents:
        pytest.skip("No agents are registered in the system.")

    agent_id = agents[0].get("id")
    if not agent_id:
        pytest.skip("Agent payload missing id field.")

    return agent_id


async def _create_test_thread(test_client, admin_headers) -> str:
    """Helper to create a thread for resume testing using /thread endpoint."""
    agent_id = await _get_agent_id(test_client, admin_headers)
    thread_id = f"test-thread-{uuid.uuid4().hex[:8]}"

    # Create thread via /thread endpoint
    response = await test_client.post(
        "/api/chat/thread",
        json={"agent_id": agent_id, "title": "Test thread for resume"},
        headers=admin_headers,
    )
    if response.status_code != 200:
        pytest.skip(f"Failed to create thread: {response.text}")

    thread_data = response.json()
    return thread_data.get("id") or thread_id


async def test_resume_rejects_non_dict_answer(test_client, admin_headers):
    """Test that non-dict answer is rejected at the API level."""
    response = await test_client.post(
        "/api/chat/thread/fake-thread-id/resume",
        json={"thread_id": "fake-thread-id", "answer": "approve"},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert "Input should be a valid dictionary" in response.text


async def test_resume_rejects_empty_answer_map(test_client, admin_headers):
    """Test that empty answer map is rejected."""
    thread_id = await _create_test_thread(test_client, admin_headers)
    response = await test_client.post(
        f"/api/chat/thread/{thread_id}/resume",
        json={"thread_id": thread_id, "answer": {}},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert "answer 不能为空" in response.text


async def test_resume_rejects_empty_question_id(test_client, admin_headers):
    """Test that empty question_id is rejected."""
    thread_id = await _create_test_thread(test_client, admin_headers)
    response = await test_client.post(
        f"/api/chat/thread/{thread_id}/resume",
        json={"thread_id": thread_id, "answer": {"": "选项A"}},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert "question_id 不能为空" in response.text


async def test_resume_rejects_empty_answer_text(test_client, admin_headers):
    """Test that empty answer text is rejected."""
    thread_id = await _create_test_thread(test_client, admin_headers)
    response = await test_client.post(
        f"/api/chat/thread/{thread_id}/resume",
        json={"thread_id": thread_id, "answer": {"q1": "  "}},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert "answer 不能为空" in response.text


async def test_resume_accepts_batch_answer_map(test_client, admin_headers):
    """Test that valid batch answer map is accepted."""
    thread_id = await _create_test_thread(test_client, admin_headers)
    response = await test_client.post(
        f"/api/chat/thread/{thread_id}/resume",
        json={"thread_id": thread_id, "answer": {"q1": "选项A", "q2": ["选项B", "选项C"]}},
        headers=admin_headers,
    )

    # Will return 200 if conversation exists and is in interrupt state,
    # or 404 if conversation not found
    assert response.status_code in (200, 404)
