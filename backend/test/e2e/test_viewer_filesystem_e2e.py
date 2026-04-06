from __future__ import annotations

import uuid

import httpx
import pytest

from yuxi.agents.backends.sandbox import (
    ensure_thread_dirs,
    sandbox_outputs_dir,
    sandbox_uploads_dir,
    sandbox_user_data_dir,
    sandbox_workspace_dir,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e, pytest.mark.slow]


async def _create_thread(client: httpx.AsyncClient, headers: dict[str, str], agent_id: str) -> str:
    response = await client.post(
        "/api/chat/thread",
        json={"agent_id": agent_id, "title": f"viewer-fs-e2e-{uuid.uuid4().hex[:8]}", "metadata": {}},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    thread_id = payload.get("thread_id") or payload.get("id")
    assert thread_id, payload
    return str(thread_id)


async def _tree(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    agent_id: str,
    thread_id: str,
    path: str,
) -> list[dict]:
    response = await client.get(
        "/api/viewer/filesystem/tree",
        params={"thread_id": thread_id, "path": path, "agent_id": agent_id},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return list(response.json().get("entries") or [])


async def _file(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    agent_id: str,
    thread_id: str,
    path: str,
) -> dict:
    response = await client.get(
        "/api/viewer/filesystem/file",
        params={"thread_id": thread_id, "path": path, "agent_id": agent_id},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


async def _download(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    agent_id: str,
    thread_id: str,
    path: str,
) -> tuple[str, bytes]:
    response = await client.get(
        "/api/viewer/filesystem/download",
        params={"thread_id": thread_id, "path": path, "agent_id": agent_id},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.headers.get("content-disposition", ""), response.content


async def _delete(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    agent_id: str,
    thread_id: str,
    path: str,
) -> dict:
    response = await client.delete(
        "/api/viewer/filesystem/file",
        params={"thread_id": thread_id, "path": path, "agent_id": agent_id},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


async def _create_directory(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    agent_id: str,
    thread_id: str,
    parent_path: str,
    name: str,
) -> dict:
    response = await client.post(
        "/api/viewer/filesystem/directory",
        json={"thread_id": thread_id, "parent_path": parent_path, "name": name, "agent_id": agent_id},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


async def _upload(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    agent_id: str,
    thread_id: str,
    parent_path: str,
    file_name: str,
    content: bytes,
) -> dict:
    response = await client.post(
        "/api/viewer/filesystem/upload",
        data={"thread_id": thread_id, "parent_path": parent_path, "agent_id": agent_id},
        files={"file": (file_name, content, "text/plain")},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


async def test_viewer_filesystem_e2e_respects_workspace_sharing_and_thread_local_uploads(
    e2e_client: httpx.AsyncClient,
    e2e_headers: dict[str, str],
    e2e_agent_context: dict[str, str | int],
):
    agent_id = str(e2e_agent_context["agent_id"])
    user_id = str(e2e_agent_context["user_id"])
    thread_id = await _create_thread(e2e_client, e2e_headers, agent_id)
    other_thread_id = await _create_thread(e2e_client, e2e_headers, agent_id)

    ensure_thread_dirs(thread_id, user_id)
    ensure_thread_dirs(other_thread_id, user_id)

    (sandbox_user_data_dir(thread_id) / "root-note.txt").write_text("root-visible\n", encoding="utf-8")
    (sandbox_workspace_dir(thread_id, user_id) / "demo.py").write_text("print(42)\n", encoding="utf-8")

    uploads_dir = sandbox_uploads_dir(thread_id) / "attachments"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    (uploads_dir / "thread1.txt").write_text("thread-one-upload\n", encoding="utf-8")
    (sandbox_outputs_dir(thread_id) / "result.txt").write_text("viewer-output\n", encoding="utf-8")

    root_entries = await _tree(
        e2e_client,
        e2e_headers,
        agent_id=agent_id,
        thread_id=thread_id,
        path="/",
    )
    root_paths = {str(entry.get("path", "")) for entry in root_entries}
    assert "/home/gem/user-data/" in root_paths, sorted(root_paths)

    user_data_paths = {
        str(entry.get("path", ""))
        for entry in await _tree(
            e2e_client,
            e2e_headers,
            agent_id=agent_id,
            thread_id=thread_id,
            path="/home/gem/user-data",
        )
    }
    expected_root_paths = {
        "/home/gem/user-data/workspace/",
        "/home/gem/user-data/uploads/",
        "/home/gem/user-data/outputs/",
        "/home/gem/user-data/root-note.txt",
    }
    assert expected_root_paths.issubset(user_data_paths), sorted(user_data_paths)

    workspace_paths = {
        str(entry.get("path", ""))
        for entry in await _tree(
            e2e_client,
            e2e_headers,
            agent_id=agent_id,
            thread_id=thread_id,
            path="/home/gem/user-data/workspace",
        )
    }
    assert "/home/gem/user-data/workspace/demo.py" in workspace_paths, sorted(workspace_paths)

    other_workspace_paths = {
        str(entry.get("path", ""))
        for entry in await _tree(
            e2e_client,
            e2e_headers,
            agent_id=agent_id,
            thread_id=other_thread_id,
            path="/home/gem/user-data/workspace",
        )
    }
    assert "/home/gem/user-data/workspace/demo.py" in other_workspace_paths, sorted(other_workspace_paths)

    other_upload_paths = {
        str(entry.get("path", ""))
        for entry in await _tree(
            e2e_client,
            e2e_headers,
            agent_id=agent_id,
            thread_id=other_thread_id,
            path="/home/gem/user-data/uploads",
        )
    }
    assert "/home/gem/user-data/uploads/attachments/" not in other_upload_paths, sorted(other_upload_paths)

    file_payload = await _file(
        e2e_client,
        e2e_headers,
        agent_id=agent_id,
        thread_id=thread_id,
        path="/home/gem/user-data/workspace/demo.py",
    )
    assert file_payload.get("content") == "print(42)\n", file_payload
    assert file_payload.get("preview_type") == "text", file_payload
    assert file_payload.get("supported") is True, file_payload

    other_file_payload = await _file(
        e2e_client,
        e2e_headers,
        agent_id=agent_id,
        thread_id=other_thread_id,
        path="/home/gem/user-data/workspace/demo.py",
    )
    assert other_file_payload.get("content") == "print(42)\n", other_file_payload

    content_disposition, payload = await _download(
        e2e_client,
        e2e_headers,
        agent_id=agent_id,
        thread_id=thread_id,
        path="/home/gem/user-data/outputs/result.txt",
    )
    assert "result.txt" in content_disposition, content_disposition
    assert payload == b"viewer-output\n", payload


async def test_viewer_filesystem_e2e_deletes_workspace_directory_recursively(
    e2e_client: httpx.AsyncClient,
    e2e_headers: dict[str, str],
    e2e_agent_context: dict[str, str | int],
):
    agent_id = str(e2e_agent_context["agent_id"])
    user_id = str(e2e_agent_context["user_id"])
    thread_id = await _create_thread(e2e_client, e2e_headers, agent_id)

    ensure_thread_dirs(thread_id, user_id)
    target_dir = sandbox_workspace_dir(thread_id, user_id) / "delete-dir"
    nested_dir = target_dir / "deep"
    nested_dir.mkdir(parents=True)
    (nested_dir / "artifact.txt").write_text("delete me\n", encoding="utf-8")

    delete_payload = await _delete(
        e2e_client,
        e2e_headers,
        agent_id=agent_id,
        thread_id=thread_id,
        path="/home/gem/user-data/workspace/delete-dir",
    )
    assert delete_payload.get("success") is True, delete_payload
    assert not target_dir.exists()

    workspace_paths = {
        str(entry.get("path", ""))
        for entry in await _tree(
            e2e_client,
            e2e_headers,
            agent_id=agent_id,
            thread_id=thread_id,
            path="/home/gem/user-data/workspace",
        )
    }
    assert "/home/gem/user-data/workspace/delete-dir/" not in workspace_paths, sorted(workspace_paths)


async def test_viewer_filesystem_e2e_creates_directory_and_uploads_file(
    e2e_client: httpx.AsyncClient,
    e2e_headers: dict[str, str],
    e2e_agent_context: dict[str, str | int],
):
    agent_id = str(e2e_agent_context["agent_id"])
    user_id = str(e2e_agent_context["user_id"])
    thread_id = await _create_thread(e2e_client, e2e_headers, agent_id)
    directory_name = f"viewer-created-{uuid.uuid4().hex[:8]}"

    ensure_thread_dirs(thread_id, user_id)

    directory_payload = await _create_directory(
        e2e_client,
        e2e_headers,
        agent_id=agent_id,
        thread_id=thread_id,
        parent_path="/home/gem/user-data/workspace",
        name=directory_name,
    )
    assert directory_payload.get("success") is True, directory_payload
    assert (sandbox_workspace_dir(thread_id, user_id) / directory_name).is_dir()

    upload_payload = await _upload(
        e2e_client,
        e2e_headers,
        agent_id=agent_id,
        thread_id=thread_id,
        parent_path=f"/home/gem/user-data/workspace/{directory_name}",
        file_name="note.txt",
        content=b"created by viewer\n",
    )
    assert upload_payload.get("success") is True, upload_payload

    created_paths = {
        str(entry.get("path", ""))
        for entry in await _tree(
            e2e_client,
            e2e_headers,
            agent_id=agent_id,
            thread_id=thread_id,
            path=f"/home/gem/user-data/workspace/{directory_name}",
        )
    }
    assert f"/home/gem/user-data/workspace/{directory_name}/note.txt" in created_paths, sorted(created_paths)

    file_payload = await _file(
        e2e_client,
        e2e_headers,
        agent_id=agent_id,
        thread_id=thread_id,
        path=f"/home/gem/user-data/workspace/{directory_name}/note.txt",
    )
    assert file_payload.get("content") == "created by viewer\n", file_payload
