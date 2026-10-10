from __future__ import annotations

from types import SimpleNamespace

import pytest

from yuxi.knowledge import preview
from yuxi.knowledge.base import KnowledgeBase
from yuxi.utils.filepreview import MAX_BINARY_PREVIEW_SIZE_BYTES


class FakeKnowledgeBase(KnowledgeBase):
    @property
    def kb_type(self) -> str:
        return "fake"

    async def _create_kb_instance(self, kb_id: str, embedding_model_spec: str | None):
        return None

    async def _initialize_kb_instance(self, instance) -> None:
        pass

    async def index_file(self, kb_id: str, file_id: str, operator_id: str | None = None) -> dict:
        return {}

    async def aquery(self, query_text: str, kb_id: str, **kwargs) -> list[dict]:
        return []

    def get_query_params_config(self, kb_id: str, **kwargs) -> dict:
        return {"options": []}

    async def delete_file(self, kb_id: str, file_id: str) -> None:
        pass

    async def get_file_basic_info(self, kb_id: str, file_id: str) -> dict:
        return {}

    async def get_file_content(self, kb_id: str, file_id: str) -> dict:
        return {}

    async def get_file_info(self, kb_id: str, file_id: str) -> dict:
        return {}


class FakeMinioClient:
    KB_BUCKETS = {"parsed": "knowledgebases"}

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    async def astat_file(self, bucket_name: str, object_name: str) -> int | None:
        content = self.objects.get((bucket_name, object_name))
        return len(content) if content is not None else None

    async def adownload_file(self, bucket_name: str, object_name: str) -> bytes:
        return self.objects[(bucket_name, object_name)]

    async def aupload_file(
        self,
        bucket_name: str,
        object_name: str,
        data: bytes,
        content_type: str | None = None,
    ) -> SimpleNamespace:
        assert content_type == "application/pdf"
        self.objects[(bucket_name, object_name)] = data
        return SimpleNamespace(url=f"http://localhost:9000/{bucket_name}/{object_name}")


def make_file_record(**overrides) -> SimpleNamespace:
    values = {
        "file_id": "file1",
        "kb_id": "db1",
        "filename": "demo.docx",
        "original_filename": None,
        "path": "minio://knowledgebases/db1/upload/demo.docx",
        "minio_url": None,
        "file_size": None,
        "is_folder": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def stub_file_record(monkeypatch: pytest.MonkeyPatch, record: SimpleNamespace) -> None:
    async def get_by_file_id(file_id: str):
        assert file_id == record.file_id
        return record

    monkeypatch.setattr(
        preview,
        "KnowledgeFileRepository",
        lambda: SimpleNamespace(get_by_file_id=get_by_file_id),
    )


def test_office_file_entry_exposes_logical_file_availability(tmp_path) -> None:
    kb = FakeKnowledgeBase(str(tmp_path))
    file_meta = {
        "file_id": "file1",
        "kb_id": "db1",
        "filename": "demo.docx",
        "path": "minio://knowledgebases/db1/upload/demo.docx",
        "status": "parsed",
    }

    entry = kb._knowledge_file_entry("db1", "file1", file_meta)

    assert "preview_modes" not in entry
    assert "default_preview_mode" not in entry


@pytest.mark.parametrize("filename", ["demo.docx", "demo.pptx", "表格.xlsx", "表格.xls"])
@pytest.mark.asyncio
async def test_read_office_pdf_preview_converts_and_caches_pdf(monkeypatch: pytest.MonkeyPatch, filename: str) -> None:
    """各类 Office 文件复用 PDF 缓存并保留原件。"""
    stub_file_record(monkeypatch, make_file_record(filename=filename))
    minio_client = FakeMinioClient()
    minio_client.objects[("knowledgebases", "db1/upload/demo.docx")] = b"office"
    convert_calls = 0

    async def fake_convert(filename: str, content: bytes) -> bytes:
        nonlocal convert_calls
        convert_calls += 1
        assert filename.endswith((".docx", ".pptx", ".xlsx", ".xls"))
        assert content == b"office"
        return b"%PDF-1.4\nconverted"

    monkeypatch.setattr(preview, "get_minio_client", lambda: minio_client)
    monkeypatch.setattr(preview, "convert_office_to_pdf", fake_convert)

    response = await preview.read_knowledge_file_preview("db1", "file1")
    cached_response = await preview.read_knowledge_file_preview("db1", "file1")

    assert response["preview_type"] == "pdf"
    assert response["supported"] is True
    assert response["binary"] is True
    assert response["content"] == b"%PDF-1.4\nconverted"
    assert response["media_type"] == "application/pdf"
    assert cached_response["content"] == b"%PDF-1.4\nconverted"
    assert minio_client.objects[("knowledgebases", "db1/preview/file1.pdf")] == b"%PDF-1.4\nconverted"
    assert convert_calls == 1
    assert minio_client.objects[("knowledgebases", "db1/upload/demo.docx")] == b"office"


@pytest.mark.asyncio
async def test_macro_enabled_spreadsheet_does_not_get_pdf_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_file_record(monkeypatch, make_file_record(filename="demo.xlsm"))
    minio_client = FakeMinioClient()
    minio_client.objects[("knowledgebases", "db1/upload/demo.docx")] = b"PK\x03\x04excel"
    monkeypatch.setattr(preview, "get_minio_client", lambda: minio_client)

    response = await preview.read_knowledge_file_preview("db1", "file1")

    assert response["preview_type"] == "unsupported"
    assert response["supported"] is False


@pytest.mark.asyncio
async def test_read_binary_preview_uses_complete_renderer_result(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_file_record(monkeypatch, make_file_record(filename="report.bin", file_size=16))
    minio_client = FakeMinioClient()
    content = b"%PDF-1.4\nreport"
    minio_client.objects[("knowledgebases", "db1/upload/demo.docx")] = content
    monkeypatch.setattr(preview, "get_minio_client", lambda: minio_client)

    response = await preview.read_knowledge_file_preview("db1", "file1")

    assert response["content"] == content
    assert response["preview_type"] == "pdf"
    assert response["supported"] is True
    assert response["media_type"] == "application/pdf"
    assert response["binary"] is True
    assert response["filename"] == "report.bin"


@pytest.mark.asyncio
async def test_read_file_preview_rejects_large_original_before_download(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_file_record(
        monkeypatch,
        make_file_record(filename="large.pdf", file_size=MAX_BINARY_PREVIEW_SIZE_BYTES + 1),
    )

    def fail_minio_access():
        raise AssertionError("large preview should not access MinIO")

    monkeypatch.setattr(preview, "get_minio_client", fail_minio_access)

    response = await preview.read_knowledge_file_preview("db1", "file1")

    assert response["preview_type"] == "unsupported"
    assert response["supported"] is False
    assert response["limit"] == MAX_BINARY_PREVIEW_SIZE_BYTES


@pytest.mark.asyncio
async def test_read_file_preview_rejects_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_file_record(monkeypatch, make_file_record(is_folder=True))

    with pytest.raises(ValueError, match="folder"):
        await preview.read_knowledge_file_preview("db1", "file1")
