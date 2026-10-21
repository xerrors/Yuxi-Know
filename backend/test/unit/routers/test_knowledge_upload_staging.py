"""三个原件入口保留各自 HTTP 包装与来源获取。"""

from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, UploadFile

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
        "has_same_name": False,
        "same_name_files": [],
    }
    assert stored == {
        "bucket_name": "knowledgebases",
        "object_name": f"unknown/upload/{digest}.html",
        "data": content,
        "content_type": "text/html",
    }


@pytest.mark.parametrize(
    ("source", "detail"),
    [
        ("upload", "知识库中已经存在了相同内容文件，File with the same content already exists in this knowledge_base"),
        ("workspace", "知识库中已经存在了相同内容文件: Note.TXT"),
        ("url", "知识库中已经存在了相同内容文件"),
    ],
)
async def test_content_conflict_retains_each_entrypoint_message(monkeypatch, source, detail):
    """共同领域冲突由各 HTTP 入口转换，保留原有 409 文案。"""
    monkeypatch.setattr(uploads.knowledge_base, "file_exists_in_knowledge_base", AsyncMock(return_value=True))
    monkeypatch.setattr(router, "_ensure_knowledge_base_supports_documents", AsyncMock())
    monkeypatch.setattr(router, "read_workspace_file_bytes", AsyncMock(return_value=("Note.TXT", b"same")))
    monkeypatch.setattr(router, "fetch_url_content", AsyncMock(return_value=(b"same", "https://example.org/final")))
    user = SimpleNamespace(uid="user")
    with pytest.raises(HTTPException) as rejected:
        if source == "upload":
            await router.upload_file(UploadFile(filename="Note.TXT", file=BytesIO(b"same")), kb_id="kb", current_user=user)
        elif source == "workspace":
            await router.import_workspace_files(router.WorkspaceImportRequest(kb_id="kb", paths=["/Note.TXT"]), current_user=user)
        else:
            await router.fetch_url("https://example.org/original", kb_id="kb", current_user=user)
    assert (rejected.value.status_code, rejected.value.detail) == (409, detail)
