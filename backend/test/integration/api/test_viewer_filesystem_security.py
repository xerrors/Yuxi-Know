from __future__ import annotations

import uuid

import pytest
from yuxi.agents.backends.sandbox import ensure_thread_dirs, sandbox_workspace_dir, virtual_path_for_thread_file

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _create_thread_for_user(test_client, headers: dict[str, str]) -> str:
    agents_resp = await test_client.get("/api/chat/agent", headers=headers)
    assert agents_resp.status_code == 200, agents_resp.text
    agents = agents_resp.json().get("agents", [])
    if not agents:
        pytest.skip("No agents available for viewer filesystem integration tests.")

    agent_id = agents[0].get("id")
    if not agent_id:
        pytest.skip("Agent payload missing id field.")

    create_resp = await test_client.post(
        "/api/chat/thread",
        json={
            "agent_id": agent_id,
            "title": f"viewer-security-test-{uuid.uuid4().hex[:8]}",
            "metadata": {},
        },
        headers=headers,
    )
    assert create_resp.status_code == 200, create_resp.text
    payload = create_resp.json()
    thread_id = payload.get("thread_id") or payload.get("id")
    assert thread_id
    return thread_id


async def test_viewer_download_blocks_workspace_symlink_escape(test_client, standard_user, tmp_path):
    headers = standard_user["headers"]
    user_id = str(standard_user["user"]["id"])
    thread_id = await _create_thread_for_user(test_client, headers)

    ensure_thread_dirs(thread_id, user_id)
    workspace_dir = sandbox_workspace_dir(thread_id, user_id)
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("outside", encoding="utf-8")
    symlink_path = workspace_dir / "escape.txt"
    symlink_path.symlink_to(outside_file)
    file_path = virtual_path_for_thread_file(thread_id, symlink_path, user_id=user_id)

    response = await test_client.get(
        "/api/viewer/filesystem/download",
        params={"thread_id": thread_id, "path": file_path},
        headers=headers,
    )

    assert response.status_code == 403, response.text
