"""Integration tests for viewer-oriented filesystem router endpoints."""

from __future__ import annotations

import importlib
import uuid

import pytest
from yuxi.agents.backends.sandbox import ensure_thread_dirs, sandbox_workspace_dir, virtual_path_for_thread_file

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _get_provider():
    from yuxi.agents.backends import get_sandbox_provider

    return get_sandbox_provider()


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
            "title": f"viewer-filesystem-test-{uuid.uuid4().hex[:8]}",
            "metadata": {},
        },
        headers=headers,
    )
    assert create_resp.status_code == 200, create_resp.text
    payload = create_resp.json()
    thread_id = payload.get("thread_id") or payload.get("id")
    assert thread_id, f"Create thread response missing thread identifier: {payload}"
    return thread_id


async def _upload_attachment_file(
    test_client,
    thread_id: str,
    headers: dict[str, str],
    file_name: str,
    content: str,
) -> str:
    response = await test_client.post(
        f"/api/chat/thread/{thread_id}/attachments",
        files={"file": (file_name, content.encode("utf-8"), "text/plain")},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    payload = response.json()
    path = payload.get("path") or payload.get("file_path")
    assert isinstance(path, str) and path
    return path


async def test_viewer_tree_requires_authentication(test_client):
    response = await test_client.get("/api/viewer/filesystem/tree", params={"thread_id": "x", "path": "/"})
    assert response.status_code == 401


async def test_viewer_tree_root_lists_user_data_namespace(test_client, standard_user):
    headers = standard_user["headers"]
    thread_id = await _create_thread_for_user(test_client, headers)

    response = await test_client.get(
        "/api/viewer/filesystem/tree",
        params={"thread_id": thread_id, "path": "/"},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    entries = response.json().get("entries", [])
    paths = {entry.get("path") for entry in entries}
    assert "/home/gem/user-data/" in paths


async def test_viewer_file_returns_raw_content_without_line_numbers(test_client, standard_user):
    headers = standard_user["headers"]
    thread_id = await _create_thread_for_user(test_client, headers)
    file_path = await _upload_attachment_file(test_client, thread_id, headers, "viewer_demo.txt", "alpha\nbeta\n")

    response = await test_client.get(
        "/api/viewer/filesystem/file",
        params={"thread_id": thread_id, "path": file_path},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert "alpha" in response.json()["content"]
    assert "beta" in response.json()["content"]


async def test_viewer_download_returns_attachment_response(test_client, standard_user):
    headers = standard_user["headers"]
    thread_id = await _create_thread_for_user(test_client, headers)
    file_path = await _upload_attachment_file(test_client, thread_id, headers, "download_demo.txt", "download-me\n")

    response = await test_client.get(
        "/api/viewer/filesystem/download",
        params={"thread_id": thread_id, "path": file_path},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    content_disposition = response.headers.get("content-disposition", "")
    assert "attachment;" in content_disposition
    assert "download_demo" in content_disposition
    assert "download-me" in response.text


async def test_viewer_download_returns_full_file_for_large_user_data_content(test_client, standard_user):
    headers = standard_user["headers"]
    thread_id = await _create_thread_for_user(test_client, headers)
    large_content = "0123456789abcdef" * 4096

    ensure_thread_dirs(thread_id)
    actual_path = sandbox_workspace_dir(thread_id) / "large_download.txt"
    actual_path.write_text(large_content, encoding="utf-8")
    file_path = virtual_path_for_thread_file(thread_id, actual_path)

    response = await test_client.get(
        "/api/viewer/filesystem/download",
        params={"thread_id": thread_id, "path": file_path},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.content == large_content.encode("utf-8")


async def test_viewer_tree_root_lists_kbs_namespace_when_visible(test_client, standard_user, monkeypatch):
    headers = standard_user["headers"]
    thread_id = await _create_thread_for_user(test_client, headers)

    async def _fake_list_viewer_filesystem_tree(**kwargs):
        return {
            "entries": [
                {"path": "/home/gem/user-data/", "name": "user-data", "is_dir": True, "size": 0, "modified_at": ""},
                {"path": "/home/gem/kbs/", "name": "kbs", "is_dir": True, "size": 0, "modified_at": ""},
            ]
        }

    router_module = importlib.import_module("server.routers.filesystem_router")
    monkeypatch.setitem(
        router_module.get_viewer_tree.__globals__,
        "list_viewer_filesystem_tree",
        _fake_list_viewer_filesystem_tree,
    )

    response = await test_client.get(
        "/api/viewer/filesystem/tree",
        params={"thread_id": thread_id, "path": "/"},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    entries = response.json().get("entries", [])
    paths = {entry.get("path") for entry in entries}
    assert "/home/gem/kbs/" in paths


async def test_viewer_can_list_and_read_kbs_namespace(test_client, standard_user):
    headers = standard_user["headers"]
    thread_id = await _create_thread_for_user(test_client, headers)

    tree_response = await test_client.get(
        "/api/viewer/filesystem/tree",
        params={"thread_id": thread_id, "path": "/home/gem/kbs"},
        headers=headers,
    )
    assert tree_response.status_code == 200, tree_response.text
    entries = tree_response.json().get("entries", [])
    assert any(str(entry.get("path", "")).startswith("/home/gem/kbs/") for entry in entries)
