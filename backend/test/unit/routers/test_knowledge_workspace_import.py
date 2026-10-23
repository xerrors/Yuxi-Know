from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import yuxi.api.routers.knowledge.management as knowledge_router
from yuxi.infrastructure.minio.client import UploadResult
from yuxi.modules.knowledge.services import uploads

pytestmark = pytest.mark.asyncio


async def test_import_workspace_files_uploads_workspace_file_to_minio(monkeypatch):
    async def fake_ensure_knowledge_base_supports_documents(slug: str, operation: str) -> None:
        assert slug == "db_1"
        assert "文档添加" in operation

    async def fake_upload(*, bucket_name: str, object_name: str, data: bytes, content_type, metadata=None) -> UploadResult:
        file_name = object_name
        assert bucket_name == uploads.MinIOClient.KB_BUCKETS["documents"]
        assert file_name.startswith("db_1/upload/") and file_name.endswith("/source.md")
        assert data == b"# workspace note\n"
        return UploadResult(f"http://minio/{bucket_name}/{file_name}", bucket_name, file_name)

    monkeypatch.setattr(
        knowledge_router,
        "_ensure_knowledge_base_supports_documents",
        fake_ensure_knowledge_base_supports_documents,
    )

    user = SimpleNamespace(id="user_1")

    async def fake_read_workspace_file_bytes(*, path, current_user):
        assert path == "/note.md"
        assert current_user is user
        return "note.md", b"# workspace note\n"

    monkeypatch.setattr(knowledge_router, "read_workspace_file_bytes", fake_read_workspace_file_bytes)
    monkeypatch.setattr(uploads, "get_minio_client", lambda: SimpleNamespace(aupload_file=fake_upload))

    result = await knowledge_router.import_workspace_files(
        knowledge_router.WorkspaceImportRequest(kb_id="db_1", paths=["/note.md"]),
        current_user=user,
    )

    assert result["status"] == "success"
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["file_path"].startswith(f"http://minio/{uploads.MinIOClient.KB_BUCKETS['documents']}/db_1/upload/")
    assert item["content_hash"]
    assert item["filename"] == "note.md"
    assert item["size"] == len(b"# workspace note\n")
    assert item["workspace_path"] == "/note.md"


async def test_import_workspace_files_rejects_directory(monkeypatch):
    async def fake_ensure_knowledge_base_supports_documents(slug: str, operation: str) -> None:
        return None

    async def fake_read_workspace_file_bytes(**_kwargs):
        raise HTTPException(status_code=400, detail="当前路径不是文件: /folder")

    monkeypatch.setattr(
        knowledge_router,
        "_ensure_knowledge_base_supports_documents",
        fake_ensure_knowledge_base_supports_documents,
    )
    monkeypatch.setattr(knowledge_router, "read_workspace_file_bytes", fake_read_workspace_file_bytes)

    with pytest.raises(HTTPException) as exc_info:
        await knowledge_router.import_workspace_files(
            knowledge_router.WorkspaceImportRequest(kb_id="db_1", paths=["/folder"]),
            current_user=SimpleNamespace(id="user_1"),
        )

    assert exc_info.value.status_code == 400
    assert "不是文件" in exc_info.value.detail
