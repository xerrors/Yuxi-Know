"""知识原件暂存的命名、顺序和失败边界。"""

from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.api.responses.knowledge import serialize_staged_file
from yuxi.infrastructure.minio.client import StorageError, UploadResult
from yuxi.modules.knowledge.services import uploads

pytestmark = pytest.mark.asyncio


@pytest.fixture
def storage(monkeypatch):
    """用可回读对象集合表达存储副作用，PG 语义由集成测试独立证明。"""
    objects, names = {}, []

    async def upload(*, bucket_name, object_name, data, content_type):
        """保存字节和 MIME，返回真实上传结果形状。"""
        objects[object_name] = (data, content_type)
        return UploadResult(f"http://minio/{bucket_name}/{object_name}", bucket_name, object_name)

    async def same_name(kb_id, filename):
        """保存当前投影名，表达同名查询发生在上传之后。"""
        assert objects
        names.append((kb_id, filename))
        return [{"file_id": "same-name", "filename": filename}]

    client = SimpleNamespace(aupload_file=upload)
    monkeypatch.setattr(uploads, "get_minio_client", lambda: client)
    monkeypatch.setattr(uploads.time, "time", lambda: 1700000000.123)
    monkeypatch.setattr(uploads.knowledge_base, "file_exists_in_knowledge_base", AsyncMock(return_value=False))
    monkeypatch.setattr(uploads.knowledge_base, "get_same_name_files", same_name)
    return objects, names, client


@pytest.mark.parametrize(
    ("kb_id", "filename", "source", "object_name", "lookup_name", "mime"),
    [
        ("kb", "Report.TXT", "file", "kb/upload/Report_1700000000123.TXT", "report.txt", None),
        (None, "Note.MD", "file", "unknown/upload/Note_1700000000123.MD", "note.md", None),
        ("kb", "Dir/Note.TXT", "file", "kb/upload/Dir/Note_1700000000123.TXT", "dir/note.txt", None),
        ("kb", "https://example.org/Article", "url", None, "https://example.org/Article", "text/html"),
    ],
)
async def test_staging_keeps_source_names_and_stored_bytes(storage, kb_id, filename, source, object_name, lookup_name, mime):
    """普通文件保持原对象名，URL 使用内容哈希，展示名规则各自保留。"""
    objects, names, _client = storage
    content = b"original source bytes\n"
    digest = sha256(content).hexdigest()
    object_name = object_name or f"kb/upload/{digest}.html"
    result = await uploads.stage_document(kb_id=kb_id, filename=filename, content=content, source=source)
    assert result.content_hash == digest
    assert result.upload.object_name == object_name
    assert objects == {object_name: (content, mime)}
    assert names == [(kb_id, lookup_name)]
    assert result.same_name_files == [{"file_id": "same-name", "filename": lookup_name}]
    if source == "file":
        projection = serialize_staged_file(result, kb_id=kb_id, filename=filename, size=len(content))
        assert projection == {
            "file_path": f"http://minio/knowledgebases/{object_name}",
            "minio_path": f"http://minio/knowledgebases/{object_name}",
            "kb_id": kb_id,
            "content_hash": digest,
            "filename": lookup_name,
            "original_filename": filename.rsplit(".", 1)[0],
            "size": len(content),
            "minio_filename": object_name.split("/upload/", 1)[1],
            "object_name": object_name,
            "bucket_name": "knowledgebases",
            "same_name_files": result.same_name_files,
            "has_same_name": True,
        }


async def test_existing_content_is_rejected_before_any_object_write(storage, monkeypatch):
    """PG 已有相同内容时不产生新对象，也不进入同名投影。"""
    objects, names, _client = storage
    monkeypatch.setattr(uploads.knowledge_base, "file_exists_in_knowledge_base", AsyncMock(return_value=True))
    with pytest.raises(uploads.DuplicateDocumentContentError, match="相同内容文件"):
        await uploads.stage_document(kb_id="kb", filename="Report.txt", content=b"duplicate")
    assert objects == {} and names == []


async def test_object_storage_failure_propagates_without_same_name_query(storage, monkeypatch):
    """对象失败不能被同名查询或成功预处理结果掩盖。"""
    objects, names, client = storage
    monkeypatch.setattr(client, "aupload_file", AsyncMock(side_effect=StorageError("upload unavailable")))
    with pytest.raises(StorageError, match="upload unavailable"):
        await uploads.stage_document(kb_id="kb", filename="Report.txt", content=b"source")
    assert objects == {} and names == []


async def test_same_name_failure_preserves_already_staged_object(storage, monkeypatch):
    """查询失败保留已写对象，不能新加补偿误删共享的 URL hash 原件。"""
    objects, _names, _client = storage
    monkeypatch.setattr(uploads.knowledge_base, "get_same_name_files", AsyncMock(side_effect=RuntimeError("query failed")))
    content = b"shared html"
    with pytest.raises(RuntimeError, match="query failed"):
        await uploads.stage_document(kb_id="kb", filename="https://example.org/page", content=content, source="url")
    assert objects == {f"kb/upload/{sha256(content).hexdigest()}.html": (content, "text/html")}


async def test_url_without_knowledge_base_uses_unknown_without_postgres(monkeypatch):
    """无知识库时真实 Manager 两个查询早返，URL 原件仍使用 unknown/hash 键。"""
    from yuxi.infrastructure.postgres.manager import pg_manager

    content = b"<html>unknown source</html>"
    objects = {}

    def reject_database():
        """任何数据库访问都会使无知识库路径失败。"""
        raise AssertionError("无 kb_id 不应查询 PostgreSQL")

    async def upload(**kwargs):
        """保存唯一对象以验证 URL MIME 和完整字节。"""
        objects[kwargs["object_name"]] = (kwargs["data"], kwargs["content_type"])
        return UploadResult("http://minio/object", kwargs["bucket_name"], kwargs["object_name"])

    monkeypatch.setattr(pg_manager, "get_async_session_context", reject_database)
    monkeypatch.setattr(uploads, "get_minio_client", lambda: SimpleNamespace(aupload_file=upload))
    result = await uploads.stage_document(kb_id=None, filename="https://example.org/Unknown", content=content, source="url")
    assert objects == {f"unknown/upload/{sha256(content).hexdigest()}.html": (content, "text/html")}
    assert result.same_name_files == []
