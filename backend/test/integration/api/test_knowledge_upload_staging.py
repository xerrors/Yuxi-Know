"""现有 API 拓扑的原件暂存契约；URL 内容源单独替代，PG/MinIO 保持真实。"""

import asyncio
import re
from hashlib import sha256
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select

from yuxi.api.routers.knowledge import management as router
from yuxi.infrastructure.minio.client import get_minio_client
from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.modules.background_jobs.models import BackgroundJobRecord
from yuxi.modules.identity.models import User
from yuxi.modules.knowledge.models import KnowledgeFile

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

FILE_FIELDS = {
    "message",
    "file_path",
    "minio_path",
    "kb_id",
    "content_hash",
    "filename",
    "original_filename",
    "size",
    "minio_filename",
    "object_name",
    "bucket_name",
}


@pytest_asyncio.fixture
async def staged_objects():
    """仅清理测试明确取得的原件，不扫描或删除其他知识库资源。"""
    objects = set()
    yield objects
    storage = get_minio_client()
    for bucket, name in objects:
        await storage.adelete_file(bucket, name)


async def _assert_file(payload, *, kb_id, filename, content, staged_objects, workspace_path=None):
    """回读原件完整字节，并用固定契约核对路径、大小写和公开字段。"""
    staged_objects.add((payload["bucket_name"], payload["object_name"]))
    expected_fields = FILE_FIELDS | ({"workspace_path"} if workspace_path else set())
    assert set(payload) == expected_fields
    assert re.fullmatch(r"[a-f0-9]{32}/source" + re.escape("." + filename.rsplit(".", 1)[-1]), payload["minio_filename"])
    assert payload["object_name"] == f"{kb_id or 'unknown'}/upload/{payload['minio_filename']}"
    assert payload["file_path"] == payload["minio_path"]
    assert payload["filename"] == filename and payload["original_filename"] == filename
    assert payload["kb_id"] == kb_id and payload["bucket_name"] == "knowledgebases"
    assert payload["content_hash"] == sha256(content).hexdigest() and payload["size"] == len(content)
    assert payload["message"] == ("Workspace file successfully imported" if workspace_path else "File successfully uploaded")
    if workspace_path:
        assert payload["workspace_path"] == workspace_path
    assert await get_minio_client().adownload_file(payload["bucket_name"], payload["object_name"]) == content


async def _assert_no_registration(sessions, kb_id):
    """从独立连接确认暂存没有创建正式文件或知识摄取作业。"""
    async with sessions() as observer:
        assert await observer.scalar(select(func.count()).select_from(KnowledgeFile).where(KnowledgeFile.kb_id == kb_id)) == 0
        assert (
            await observer.scalar(
                select(func.count()).select_from(BackgroundJobRecord).where(BackgroundJobRecord.payload["kb_id"].as_string() == kb_id)
            )
            == 0
        )


async def test_file_and_workspace_staging_preserve_bytes_without_registering(
    test_client, admin_headers, knowledge_base_resource, postgres_sessions, staged_objects
):
    """实际 HTTP 上传和工作区批量导入保留对象契约，批内相同原件不被额外去重。"""
    kb_id = knowledge_base_resource["kb_id"]
    filename, content = f"MiXeD-{uuid4().hex}.TXT", b"first source\n"
    response = await test_client.post(
        "/api/knowledge/files/upload", params={"kb_id": kb_id}, files={"file": (filename, content)}, headers=admin_headers
    )
    assert response.status_code == 200, response.text
    await _assert_file(response.json(), kb_id=kb_id, filename=filename, content=content, staged_objects=staged_objects)
    await _assert_no_registration(postgres_sessions, kb_id)

    workspace_name, workspace_content = f"Workspace-{uuid4().hex}.MD", b"# workspace source\n"
    path = f"/{workspace_name}"
    try:
        uploaded = await test_client.post(
            "/api/workspace/upload", data={"parent_path": "/"}, files={"files": (workspace_name, workspace_content)}, headers=admin_headers
        )
        assert uploaded.status_code == 200, uploaded.text
        imported = await test_client.post(
            "/api/knowledge/files/import-workspace", json={"kb_id": kb_id, "paths": [path, path]}, headers=admin_headers
        )
        assert imported.status_code == 200, imported.text
        assert set(imported.json()) == {"status", "items"} and imported.json()["status"] == "success"
        assert len(imported.json()["items"]) == 2
        for item in imported.json()["items"]:
            await _assert_file(
                item, kb_id=kb_id, filename=workspace_name, content=workspace_content, staged_objects=staged_objects, workspace_path=path
            )
        await _assert_no_registration(postgres_sessions, kb_id)
    finally:
        removed = await test_client.delete("/api/workspace/file", params={"path": path}, headers=admin_headers)
        assert removed.status_code in {200, 404}, removed.text


async def test_registered_content_can_be_staged_again(
    test_client, admin_headers, knowledge_base_resource, postgres_sessions, staged_objects
):
    """登记后的相同内容仍允许独立暂存，不在未知父目录时决定最终名称。"""
    kb_id = knowledge_base_resource["kb_id"]
    filename, content = f"repeat-{uuid4().hex}.txt", b"repeat source"
    first = await test_client.post(
        "/api/knowledge/files/upload", params={"kb_id": kb_id}, files={"file": (filename, content)}, headers=admin_headers
    )
    assert first.status_code == 200
    payload = first.json()
    staged_objects.add((payload["bucket_name"], payload["object_name"]))
    registered = await test_client.post(
        f"/api/knowledge/knowledge-bases/{kb_id}/documents/add",
        json={"items": [payload["file_path"]], "params": {"content_hashes": {payload["file_path"]: payload["content_hash"]}}},
        headers=admin_headers,
    )
    assert registered.status_code == 200 and registered.json()["added"] == 1, registered.text
    second = await test_client.post(
        "/api/knowledge/files/upload", params={"kb_id": kb_id}, files={"file": (filename, content)}, headers=admin_headers
    )
    assert second.status_code == 200, second.text
    await _assert_file(second.json(), kb_id=kb_id, filename=filename, content=content, staged_objects=staged_objects)
    assert second.json()["object_name"] != payload["object_name"]


async def test_upload_without_kb_uses_unknown_and_rejects_unauthenticated(test_client, admin_headers, staged_objects):
    """真实 API 的无知识库前缀保持 unknown，未认证请求不能暂存原件。"""
    filename, content = f"unknown-{uuid4().hex}.TXT", b"unknown kb source"
    rejected = await test_client.post("/api/knowledge/files/upload", files={"file": (filename, content)})
    assert rejected.status_code in {401, 403}, rejected.text
    response = await test_client.post("/api/knowledge/files/upload", files={"file": (filename, content)}, headers=admin_headers)
    assert response.status_code == 200, response.text
    await _assert_file(response.json(), kb_id=None, filename=filename, content=content, staged_objects=staged_objects)


async def test_url_asgi_projection_uses_real_pg_and_minio(
    test_client, admin_headers, knowledge_base_resource, postgres_sessions, staged_objects, monkeypatch
):
    """仅替代抓取内容源和认证适配，ASGI HTTP 路由、权限查询、PG 与 MinIO 保持真实。"""
    kb_id = knowledge_base_resource["kb_id"]
    original, final = f"https://example.org/Article-{uuid4().hex}", "https://example.org/final"
    content = b"<html><body>deterministic source</body></html>"
    digest = sha256(content).hexdigest()
    me = await test_client.get("/api/auth/me", headers=admin_headers)
    assert me.status_code == 200, me.text
    async with postgres_sessions() as observer:
        user = await observer.scalar(select(User).where(User.uid == me.json()["uid"]))
    app = FastAPI()
    app.include_router(router.knowledge, prefix="/api")
    app.dependency_overrides[router.get_admin_user] = lambda: user
    monkeypatch.setattr(router, "fetch_url_content", AsyncMock(return_value=(content, final)))
    pg_manager.initialize()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/knowledge/files/fetch-url", json={"url": original, "kb_id": kb_id})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert set(payload) == {
            "status",
            "file_path",
            "minio_url",
            "content_hash",
            "filename",
            "final_url",
            "size",
        }
        assert payload["status"] == "success" and payload["filename"] == original and payload["final_url"] == final
        assert payload["content_hash"] == digest and payload["size"] == len(content)
        assert payload["file_path"] == payload["minio_url"]
        from yuxi.infrastructure.minio.object_urls import parse_minio_url

        _, key = parse_minio_url(payload["file_path"])
        assert key.startswith(f"{kb_id}/upload/") and key.endswith("/source.html")
        staged_objects.add(("knowledgebases", key))
        storage = get_minio_client()
        assert await storage.adownload_file("knowledgebases", key) == content
        stat = await asyncio.to_thread(storage.client.stat_object, "knowledgebases", key)
        assert stat.content_type == "text/html"
    finally:
        await pg_manager.close()
