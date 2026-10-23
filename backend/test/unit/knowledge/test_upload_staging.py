"""原件暂存具有独立对象身份，内容重复不代表逻辑文件重复。"""

from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.infrastructure.minio.client import StorageError, UploadResult
from yuxi.modules.knowledge.services import uploads
from yuxi.shared.errors import InvalidInputError

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    ("kb_id", "filename", "source", "leaf", "mime"),
    [
        ("kb", "Report.TXT", "file", "source.TXT", None),
        (None, "Note.MD", "file", "source.MD", None),
        ("kb", "https://example.org/Article", "url", "source.html", "text/html"),
    ],
)
async def test_staging_independent_objects_and_exact_bytes(monkeypatch, kb_id, filename, source, leaf, mime):
    """同名同内容两次暂存不会覆盖对象，不依赖 PostgreSQL 内容查询。"""
    objects = {}

    async def upload(**kwargs):
        objects[kwargs["object_name"]] = (kwargs["data"], kwargs["content_type"])
        return UploadResult("http://minio/" + kwargs["object_name"], kwargs["bucket_name"], kwargs["object_name"])

    monkeypatch.setattr(uploads, "get_minio_client", lambda: SimpleNamespace(aupload_file=upload))
    first = await uploads.stage_document(kb_id=kb_id, filename=filename, content=b"bytes", source=source)
    second = await uploads.stage_document(kb_id=kb_id, filename=filename, content=b"bytes", source=source)
    assert first.content_hash == second.content_hash == sha256(b"bytes").hexdigest()
    assert first.upload.object_name != second.upload.object_name
    assert len(objects) == 2
    assert all(key.startswith(f"{kb_id or 'unknown'}/upload/") and key.endswith("/" + leaf) for key in objects)
    assert list(objects.values()) == [(b"bytes", mime)] * 2


async def test_invalid_leaf_rejected_before_object_write(monkeypatch):
    upload = AsyncMock()
    monkeypatch.setattr(uploads, "get_minio_client", lambda: SimpleNamespace(aupload_file=upload))
    with pytest.raises(InvalidInputError):
        await uploads.stage_document(kb_id="kb", filename="a/b.txt", content=b"bytes")
    upload.assert_not_awaited()


async def test_object_failure_is_observable(monkeypatch):
    upload = AsyncMock(side_effect=StorageError("unavailable"))
    monkeypatch.setattr(uploads, "get_minio_client", lambda: SimpleNamespace(aupload_file=upload))
    with pytest.raises(StorageError):
        await uploads.stage_document(kb_id="kb", filename="a.txt", content=b"bytes")
