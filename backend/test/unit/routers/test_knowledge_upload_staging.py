"""三个原件入口保留各自 HTTP 包装与来源获取。"""

from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.api.routers.knowledge import management as router
from yuxi.infrastructure.minio.client import UploadResult
from yuxi.modules.knowledge.services import uploads

pytestmark = pytest.mark.asyncio


async def test_url_response_preserves_original_and_redirected_names(monkeypatch):
    """来源适配器保持原始 URL、重定向结果和独立 URL 响应字段。"""
    original, final = "https://example.org/Original", "https://example.org/Redirected"
    content = b"<html>source</html>"
    digest = sha256(content).hexdigest()
    stored = {}

    async def upload(**kwargs):
        """保存内容，独立核对路由没有把 URL 当作普通文件名。"""
        stored.update(kwargs)
        return UploadResult("http://minio/html", kwargs["bucket_name"], kwargs["object_name"])

    monkeypatch.setattr(router, "fetch_url_content", AsyncMock(return_value=(content, final)))
    monkeypatch.setattr(uploads, "get_minio_client", lambda: SimpleNamespace(aupload_file=upload))
    result = await router.fetch_url(original, kb_id=None, current_user=SimpleNamespace(uid="user"))
    assert result == {
        "status": "success",
        "file_path": "http://minio/html",
        "minio_url": "http://minio/html",
        "content_hash": digest,
        "filename": original,
        "final_url": final,
        "size": len(content),
    }
    assert stored["object_name"].startswith("unknown/upload/")
    assert stored["object_name"].endswith("/source.html")
    assert {key: value for key, value in stored.items() if key != "object_name"} == {
        "bucket_name": "knowledgebases",
        "data": content,
        "content_type": "text/html",
        "metadata": {"Content-Disposition": "attachment; filename*=UTF-8''page.html"},
    }
