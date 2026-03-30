from __future__ import annotations

from types import SimpleNamespace

import pytest
from yuxi.agents.backends.knowledge_base_backend import (
    KnowledgeBaseReadonlyBackend,
    resolve_visible_knowledge_bases_for_context,
)


def test_knowledge_base_backend_builds_virtual_tree_and_materializes_files(monkeypatch, tmp_path) -> None:
    visible_kbs = [
        {"db_id": "db-1", "name": "FAQ"},
        {"db_id": "db-2", "name": "FAQ"},
    ]
    files_meta = {
        "folder-api": {
            "file_id": "folder-api",
            "database_id": "db-1",
            "parent_id": None,
            "filename": "API",
            "is_folder": True,
            "created_at": "2026-03-26T00:00:00Z",
        },
        "file-pdf": {
            "file_id": "file-pdf",
            "database_id": "db-1",
            "parent_id": "folder-api",
            "filename": "auth-guide.pdf",
            "path": "http://minio/kb-source/db-1/upload/auth-guide.pdf",
            "markdown_file": "http://minio/kb-parsed/db-1/parsed/file-pdf.md",
            "size": 12,
            "is_folder": False,
            "created_at": "2026-03-26T00:00:00Z",
        },
        "file-pdf-2": {
            "file_id": "file-pdf-2",
            "database_id": "db-1",
            "parent_id": "folder-api",
            "filename": "auth-guide.pdf",
            "path": "http://minio/kb-source/db-1/upload/auth-guide-2.pdf",
            "size": 7,
            "is_folder": False,
            "created_at": "2026-03-26T00:00:00Z",
        },
        "file-db2": {
            "file_id": "file-db2",
            "database_id": "db-2",
            "parent_id": None,
            "filename": "overview.txt",
            "path": "http://minio/kb-source/db-2/upload/overview.txt",
            "size": 5,
            "is_folder": False,
            "created_at": "2026-03-26T00:00:00Z",
        },
    }
    monkeypatch.setattr("yuxi.agents.backends.knowledge_base_backend._all_files_meta", lambda: files_meta)

    class _FakeMinio:
        def download_file(self, bucket_name: str, object_name: str) -> bytes:
            return f"{bucket_name}:{object_name}".encode()

    monkeypatch.setattr("yuxi.agents.backends.knowledge_base_backend.get_minio_client", lambda: _FakeMinio())

    backend = KnowledgeBaseReadonlyBackend(visible_kbs=visible_kbs, cache_root=tmp_path)

    root_entries = {entry["path"] for entry in backend.ls_info("/")}
    assert "/FAQ/" in root_entries
    assert "/FAQ__db-2/" in root_entries

    faq_entries = {entry["path"] for entry in backend.ls_info("/FAQ")}
    assert "/FAQ/API/" in faq_entries
    assert "/FAQ/parsed/" in faq_entries

    api_entries = {entry["path"] for entry in backend.ls_info("/FAQ/API")}
    assert "/FAQ/API/auth-guide.pdf" in api_entries
    assert any(path.startswith("/FAQ/API/auth-guide.pdf__file-pdf") for path in api_entries)

    parsed_entries = {entry["path"] for entry in backend.ls_info("/FAQ/parsed/API")}
    assert "/FAQ/parsed/API/auth-guide.md" in parsed_entries

    responses = backend.download_files(["/FAQ/API/auth-guide.pdf", "/FAQ/parsed/API/auth-guide.md"])
    assert responses[0].content == b"kb-source:db-1/upload/auth-guide.pdf"
    assert responses[1].content == b"kb-parsed:db-1/parsed/file-pdf.md"

    assert "kb-source" in backend.read("/FAQ/API/auth-guide.pdf")
    assert backend.write("/FAQ/API/new.txt", "x").error == "Knowledge base path is read-only."


@pytest.mark.asyncio
async def test_resolve_visible_knowledge_bases_for_context_filters_by_enabled_names(monkeypatch) -> None:
    async def _fake_get_databases_by_raw_id(user_id: int) -> dict:
        assert user_id == 7
        return {"databases": [{"db_id": "db-1", "name": "Alpha"}, {"db_id": "db-2", "name": "Beta"}]}

    monkeypatch.setattr(
        "yuxi.agents.backends.knowledge_base_backend.knowledge_base.get_databases_by_raw_id",
        _fake_get_databases_by_raw_id,
    )

    context = SimpleNamespace(user_id="7", knowledges=["Beta"])
    visible = await resolve_visible_knowledge_bases_for_context(context)

    assert visible == [{"db_id": "db-2", "name": "Beta"}]
    assert getattr(context, "_visible_knowledge_bases") == visible
