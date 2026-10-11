"""真实 HTTP 上传后回读工作区文件与 MinIO 对象。"""

import asyncio
from hashlib import sha256
from io import BytesIO
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import pytest
from PIL import Image

from yuxi.infrastructure.minio import get_minio_client

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_concurrent_knowledge_uploads_preserve_both_files(test_client, admin_headers, knowledge_base_resource):
    """知识库并发上传两个文件，回读真实对象核对内容与哈希。"""
    storage = get_minio_client()
    contents = {f"pytest-upload-{uuid4().hex}.txt": content for content in (b"first knowledge file", b"second knowledge file")}
    uploaded = []

    async def upload(name, content):
        """保存成功上传的对象位置，供核对与清理。"""
        response = await test_client.post(
            "/api/knowledge/files/upload",
            params={"kb_id": knowledge_base_resource["kb_id"]},
            files={"file": (name, content, "text/plain")},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        uploaded.append(payload)
        assert payload["filename"] == name
        assert payload["size"] == len(content)
        assert payload["content_hash"] == sha256(content).hexdigest()
        assert await storage.adownload_file(payload["bucket_name"], payload["object_name"]) == content

    try:
        results = await asyncio.gather(*(upload(name, content) for name, content in contents.items()), return_exceptions=True)
        assert results == [None, None], results
        assert len(uploaded) == 2
    finally:
        for payload in uploaded:
            await storage.adelete_file(payload["bucket_name"], payload["object_name"])


async def test_workspace_upload_preserves_bytes_and_existing_file(test_client, standard_user):
    """超过 spool 阈值的文件按流落盘，同名重传不得覆盖。"""
    headers = standard_user["headers"]
    filename = f"pytest-upload-{uuid4().hex}.bin"
    path = f"/{filename}"
    content = b"\x00\xff\x01\x02" * (1024 * 1024)
    try:
        uploaded = await test_client.post(
            "/api/workspace/upload",
            data={"parent_path": "/"},
            files={"files": (filename, content, "application/octet-stream")},
            headers=headers,
        )
        assert uploaded.status_code == 200, uploaded.text
        assert uploaded.json()["entries"][0]["size"] == len(content)
        collision = await test_client.post(
            "/api/workspace/upload",
            data={"parent_path": "/"},
            files={"files": (filename, b"replacement", "application/octet-stream")},
            headers=headers,
        )
        assert collision.status_code == 400, collision.text
        downloaded = await test_client.get("/api/workspace/download", params={"path": path}, headers=headers)
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content == content
    finally:
        removed = await test_client.delete("/api/workspace/file", params={"path": path}, headers=headers)
        assert removed.status_code in {200, 404}, removed.text


@pytest.mark.parametrize("endpoint,url_key", [("/api/user/upload-image", "image_url"), ("/api/auth/upload-avatar", "avatar_url")])
async def test_image_upload_preserves_minio_bytes_and_rejects_invalid_content(test_client, standard_user, endpoint, url_key):
    """图片与头像端点消费实际图片字节，并返回可定位的存储结果。"""
    source = BytesIO()
    Image.new("RGB", (2, 2), "red").save(source, format="PNG")
    content = source.getvalue()
    storage = get_minio_client()
    object_name = None
    try:
        response = await test_client.post(
            endpoint,
            headers=standard_user["headers"],
            files={"file": ("not-an-extension.txt", content, "text/plain")},
        )
        assert response.status_code == 200, response.text
        url = response.json()[url_key]
        object_name = unquote(urlsplit(url).path.split("/public/", 1)[1])
        assert object_name.endswith(".png")
        assert await storage.adownload_file("public", object_name) == content
        if url_key == "avatar_url":
            me = await test_client.get("/api/auth/me", headers=standard_user["headers"])
            assert me.status_code == 200, me.text
            assert me.json()["avatar"] == url
        invalid = await test_client.post(
            endpoint,
            headers=standard_user["headers"],
            files={"file": ("fake.png", b"not an image", "image/png")},
        )
        assert invalid.status_code == 400, invalid.text
    finally:
        if object_name:
            await storage.adelete_file("public", object_name)
