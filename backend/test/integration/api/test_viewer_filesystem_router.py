"""Realtime Project Workdir HTTP integration tests."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from yuxi.modules.workspace.paths import user_workdir_host_dir

from test.integration.api.helpers import create_default_agent_thread, get_thread_workdir_path

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_viewer_tree_requires_authentication(test_client):
    response = await test_client.get("/api/viewer/filesystem/tree", params={"thread_id": "x", "path": "/"})
    assert response.status_code == 401


async def test_created_file_is_immediately_visible_to_tree_preview_and_artifact(
    test_client,
    standard_user,
    admin_headers,
):
    headers = standard_user["headers"]
    thread_id = await create_default_agent_thread(test_client, headers, title_prefix="viewer-filesystem")

    upload = await test_client.post(
        "/api/viewer/filesystem/upload",
        data={"thread_id": thread_id, "parent_path": "/"},
        files={"files": ("live.txt", b"live bytes\n", "text/plain")},
        headers=headers,
    )
    assert upload.status_code == 200, upload.text
    [entry] = upload.json()["entries"]
    file_path = entry["path"]
    assert file_path == "/live.txt"

    collision = await test_client.post(
        "/api/viewer/filesystem/upload",
        data={"thread_id": thread_id, "parent_path": "/"},
        files={"files": ("live.txt", b"replacement", "text/plain")},
        headers=headers,
    )
    assert collision.status_code == 409, collision.text

    tree = await test_client.get(
        "/api/viewer/filesystem/tree",
        params={"thread_id": thread_id, "path": "/"},
        headers=headers,
    )
    assert tree.status_code == 200, tree.text
    assert "live.txt" in {item["name"] for item in tree.json()["entries"]}

    preview = await test_client.get(
        "/api/viewer/filesystem/file",
        params={"thread_id": thread_id, "path": file_path},
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["content"] == "live bytes\n"

    artifact = await test_client.get(entry["artifact_url"], headers=headers)
    assert artifact.status_code == 200, artifact.text
    assert artifact.content == b"live bytes\n"

    cross_user = await test_client.get(entry["artifact_url"], headers=admin_headers)
    assert cross_user.status_code == 404

    deleted = await test_client.delete(
        "/api/viewer/filesystem/file",
        params={"thread_id": thread_id, "path": file_path},
        headers=headers,
    )
    assert deleted.status_code == 200, deleted.text
    missing = await test_client.get(
        "/api/viewer/filesystem/download",
        params={"thread_id": thread_id, "path": file_path},
        headers=headers,
    )
    assert missing.status_code == 404


async def test_viewer_rejects_paths_outside_current_workdir(test_client, standard_user):
    headers = standard_user["headers"]
    thread_id = await create_default_agent_thread(test_client, headers, title_prefix="viewer-filesystem")
    for path in (
        "/home/user/workspace/agents/skills/private.txt",
        "/home/user/workspace/projects/other/file.txt",
    ):
        response = await test_client.get(
            "/api/viewer/filesystem/file",
            params={"thread_id": thread_id, "path": path},
            headers=headers,
        )
        assert response.status_code == 403


async def test_mention_search_observes_live_viewer_files_without_cache(test_client, standard_user):
    headers = standard_user["headers"]
    thread_id = await create_default_agent_thread(test_client, headers, title_prefix="viewer-filesystem")
    filename = "mention-live-file.txt"
    upload = await test_client.post(
        "/api/viewer/filesystem/upload",
        data={"thread_id": thread_id, "parent_path": "/"},
        files={"files": (filename, b"live", "text/plain")},
        headers=headers,
    )
    assert upload.status_code == 200, upload.text
    artifact_path = upload.json()["entries"][0]["artifact_url"].split("/artifacts/", 1)[1]

    found = await test_client.get(
        "/api/mention/search",
        params={"thread_id": thread_id, "query": "mention-live", "sources": "thread"},
        headers=headers,
    )
    assert found.status_code == 200, found.text
    assert found.json() == [
        {
            "name": filename,
            "path": f"/{artifact_path}",
            "is_dir": False,
            "source": "thread",
        }
    ]

    deleted = await test_client.delete(
        "/api/viewer/filesystem/file",
        params={"thread_id": thread_id, "path": f"/{filename}"},
        headers=headers,
    )
    assert deleted.status_code == 200, deleted.text
    missing = await test_client.get(
        "/api/mention/search",
        params={"thread_id": thread_id, "query": "mention-live", "sources": "thread"},
        headers=headers,
    )
    assert missing.status_code == 200, missing.text
    assert missing.json() == []


async def test_viewer_download_blocks_project_symlink_escape(test_client, standard_user):
    headers = standard_user["headers"]
    uid = str(standard_user["user"]["uid"])
    thread_id = await create_default_agent_thread(test_client, headers, title_prefix="viewer-filesystem-security")
    workdir_path = await get_thread_workdir_path(thread_id)

    project_root = f"/home/user/workspace/{workdir_path}"
    file_path = f"{project_root}/escape.txt"
    (user_workdir_host_dir(uid, workdir_path) / "escape.txt").symlink_to("/etc/hosts")

    response = await test_client.get(
        "/api/viewer/filesystem/download",
        params={"thread_id": thread_id, "path": file_path},
        headers=headers,
    )

    assert response.status_code == 403, response.text


async def test_viewer_upload_blocks_project_symlink_escape(test_client, standard_user, tmp_path: Path):
    headers = standard_user["headers"]
    uid = str(standard_user["user"]["uid"])
    thread_id = await create_default_agent_thread(test_client, headers, title_prefix="viewer-filesystem-security")
    workdir_path = await get_thread_workdir_path(thread_id)

    project_root = f"/home/user/workspace/{workdir_path}"
    outside_dir = tmp_path / f"yuxi-viewer-{uuid.uuid4().hex}"
    outside_dir.mkdir()
    parent_path = f"{project_root}/escape-dir"
    (user_workdir_host_dir(uid, workdir_path) / "escape-dir").symlink_to(outside_dir)

    response = await test_client.post(
        "/api/viewer/filesystem/upload",
        data={"thread_id": thread_id, "parent_path": parent_path},
        files={"files": ("escape.txt", b"outside", "text/plain")},
        headers=headers,
    )

    assert response.status_code == 403, response.text
    assert not (outside_dir / "escape.txt").exists()


async def test_viewer_upload_preserves_non_directory_parent_error(test_client, standard_user):
    headers = standard_user["headers"]
    uid = str(standard_user["user"]["uid"])
    thread_id = await create_default_agent_thread(test_client, headers, title_prefix="viewer-filesystem-security")
    workdir_path = await get_thread_workdir_path(thread_id)

    (user_workdir_host_dir(uid, workdir_path) / "occupied").write_text("file", encoding="utf-8")

    response = await test_client.post(
        "/api/viewer/filesystem/upload",
        data={"thread_id": thread_id, "parent_path": "/occupied"},
        files={"files": ("child.txt", b"content", "text/plain")},
        headers=headers,
    )

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "目录不存在"


async def test_viewer_upload_does_not_replace_hidden_target_symlink(test_client, standard_user, tmp_path: Path):
    headers = standard_user["headers"]
    uid = str(standard_user["user"]["uid"])
    thread_id = await create_default_agent_thread(test_client, headers, title_prefix="viewer-filesystem-security")
    workdir_path = await get_thread_workdir_path(thread_id)

    outside = tmp_path / f"yuxi-viewer-target-{uuid.uuid4().hex}.txt"
    outside.write_text("outside", encoding="utf-8")
    target = user_workdir_host_dir(uid, workdir_path) / "hidden.txt"
    target.symlink_to(outside)

    response = await test_client.post(
        "/api/viewer/filesystem/upload",
        data={"thread_id": thread_id, "parent_path": "/"},
        files={"files": ("hidden.txt", b"replacement", "text/plain")},
        headers=headers,
    )

    assert response.status_code == 409, response.text
    assert target.is_symlink()
    assert outside.read_text(encoding="utf-8") == "outside"
