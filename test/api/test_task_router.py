"""
Integration tests for the task management router.
"""

from __future__ import annotations

import asyncio

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_task_routes_require_admin(test_client, standard_user):
    """Non-admin users should be blocked from accessing task APIs."""
    headers = standard_user["headers"]

    list_response = await test_client.get("/api/tasks", headers=headers)
    assert list_response.status_code == 403

    detail_response = await test_client.get("/api/tasks/some-task", headers=headers)
    assert detail_response.status_code == 403

    cancel_response = await test_client.post("/api/tasks/some-task/cancel", headers=headers)
    assert cancel_response.status_code == 403


async def test_admin_can_list_tasks(test_client, admin_headers):
    """Admin should receive a well-formed task list payload."""
    response = await test_client.get("/api/tasks", headers=admin_headers)
    assert response.status_code == 200, response.text

    payload = response.json()
    assert "tasks" in payload
    assert isinstance(payload["tasks"], list)
    assert "summary" in payload
    assert isinstance(payload["summary"], dict)


async def test_cancel_unknown_task_returns_client_error(test_client, admin_headers):
    """Cancelling a non-existent task should surface a 400 response."""
    response = await test_client.post("/api/tasks/not-real/cancel", headers=admin_headers)
    assert response.status_code == 400, response.text


async def test_enqueue_document_creates_task(
    test_client,
    admin_headers,
    knowledge_database,
):
    """Trigger knowledge ingestion to ensure a task record is materialised."""
    db_id = knowledge_database["db_id"]

    enqueue_response = await test_client.post(
        f"/api/knowledge/databases/{db_id}/documents",
        json={
            "items": [],
            "params": {"content_type": "file"},
        },
        headers=admin_headers,
    )
    assert enqueue_response.status_code == 200, enqueue_response.text

    enqueue_payload = enqueue_response.json()
    assert enqueue_payload.get("status") == "queued"
    task_id = enqueue_payload.get("task_id")
    assert task_id, "Knowledge ingestion did not return a task_id"

    # The task should be queryable immediately after enqueueing.
    detail_response = await test_client.get(f"/api/tasks/{task_id}", headers=admin_headers)
    assert detail_response.status_code == 200, detail_response.text
    detail_payload = detail_response.json().get("task", {})
    assert detail_payload.get("id") == task_id
    assert detail_payload.get("status") in {"queued", "pending", "running", "failed", "success", "cancelled"}

    # Ensure the task surfaces in the list endpoint within a short window.
    for _ in range(10):
        list_response = await test_client.get("/api/tasks", headers=admin_headers)
        assert list_response.status_code == 200, list_response.text
        all_tasks = list_response.json().get("tasks", [])
        if any(entry.get("id") == task_id for entry in all_tasks):
            break
        await asyncio.sleep(0.2)
    else:
        pytest.fail("Task did not appear in list endpoint within timeout window")

    # Poll for terminal state to validate worker bookkeeping.
    for _ in range(20):
        detail_response = await test_client.get(f"/api/tasks/{task_id}", headers=admin_headers)
        task_status = detail_response.json().get("task", {}).get("status")
        if task_status in {"success", "failed", "cancelled"}:
            break
        await asyncio.sleep(0.5)
    else:
        pytest.fail("Task did not reach a terminal status within timeout window")
