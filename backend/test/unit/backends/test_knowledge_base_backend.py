from __future__ import annotations

from types import SimpleNamespace

import pytest
from yuxi.agents.backends.knowledge_base_backend import (
    KBS_PATH,
    KnowledgeBaseReadonlyBackend,
    build_knowledge_base_filepath_map,
    inject_filepaths_into_retrieval_result,
    resolve_file_relative_virtual_path,
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
    assert "/FAQ/parsed/API/auth-guide.pdf.md" in parsed_entries

    responses = backend.download_files(["/FAQ/API/auth-guide.pdf", "/FAQ/parsed/API/auth-guide.pdf.md"])
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


def test_build_knowledge_base_filepath_map_matches_virtual_tree(monkeypatch, tmp_path) -> None:
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

    filepath_map = build_knowledge_base_filepath_map(visible_kbs=visible_kbs, files_meta=files_meta)
    backend = KnowledgeBaseReadonlyBackend(visible_kbs=visible_kbs, cache_root=tmp_path)

    assert filepath_map["file-pdf"] == f"{KBS_PATH}/FAQ/API/auth-guide.pdf"
    assert filepath_map["file-db2"] == f"{KBS_PATH}/FAQ__db-2/overview.txt"
    assert filepath_map["file-pdf-2"].startswith(f"{KBS_PATH}/FAQ/API/auth-guide.pdf__")

    mapped_virtual_paths = {path[len(KBS_PATH) :] for path in filepath_map.values()}
    for virtual_path in mapped_virtual_paths:
        assert virtual_path in backend._files


def test_resolve_file_relative_virtual_path_by_file_id(monkeypatch) -> None:
    visible_kbs = [{"db_id": "db-1", "name": "食品 相关文献"}]
    files_meta = {
        "folder-1": {
            "file_id": "folder-1",
            "database_id": "db-1",
            "parent_id": None,
            "filename": "课程",
            "is_folder": True,
            "created_at": "2026-03-26T00:00:00Z",
        },
        "file_79c496": {
            "file_id": "file_79c496",
            "database_id": "db-1",
            "parent_id": "folder-1",
            "filename": "营养与食品课程中的思政建设研究.pdf",
            "path": "http://minio/knowledgebases/db-1/uploads/file_79c496.pdf",
            "is_folder": False,
            "size": 100,
            "created_at": "2026-03-26T00:00:00Z",
        },
    }
    monkeypatch.setattr("yuxi.agents.backends.knowledge_base_backend._all_files_meta", lambda: files_meta)

    relative_path = resolve_file_relative_virtual_path(file_id="file_79c496", visible_kbs=visible_kbs)
    absolute_map = build_knowledge_base_filepath_map(visible_kbs=visible_kbs, files_meta=files_meta)

    assert relative_path == "/食品 相关文献/课程/营养与食品课程中的思政建设研究.pdf"
    assert absolute_map["file_79c496"] == f"{KBS_PATH}{relative_path}"


@pytest.mark.asyncio
async def test_inject_filepaths_into_retrieval_result_injects_by_file_id(monkeypatch) -> None:
    retrieval_chunks = [
        {
            "content": "auth guide",
            "metadata": {
                "file_id": "file-1",
                "source": "auth-guide.pdf",
            },
        }
    ]

    monkeypatch.setattr(
        "yuxi.agents.backends.knowledge_base_backend._resolve_virtual_layout",
        lambda **kwargs: SimpleNamespace(
            source_filepaths={"file-1": f"{KBS_PATH}/FAQ/auth-guide.pdf"},
            parsed_filepaths={"file-1": f"{KBS_PATH}/FAQ/parsed/auth-guide.pdf.md"},
        ),
    )

    result = await inject_filepaths_into_retrieval_result(
        retrieval_chunks=retrieval_chunks,
        visible_kbs=[{"db_id": "db-1", "name": "FAQ"}],
        target_db_id="db-1",
    )

    assert result[0]["metadata"]["filepath"] == f"{KBS_PATH}/FAQ/auth-guide.pdf"
    assert result[0]["metadata"]["parsed_path"] == f"{KBS_PATH}/FAQ/parsed/auth-guide.pdf.md"


@pytest.mark.asyncio
async def test_inject_filepaths_into_retrieval_result_injects_parsed_path_when_markdown_exists(monkeypatch) -> None:
    files_meta = {
        "file-1": {
            "file_id": "file-1",
            "database_id": "db-1",
            "parent_id": None,
            "filename": "auth-guide.pdf",
            "path": "http://minio/kb-source/db-1/upload/auth-guide.pdf",
            "markdown_file": "http://minio/kb-parsed/db-1/parsed/file-1.md",
            "is_folder": False,
            "created_at": "2026-03-26T00:00:00Z",
        }
    }
    monkeypatch.setattr("yuxi.agents.backends.knowledge_base_backend._all_files_meta", lambda: files_meta)

    retrieval_chunks = [{"content": "auth guide", "metadata": {"file_id": "file-1"}}]
    result = await inject_filepaths_into_retrieval_result(
        retrieval_chunks=retrieval_chunks,
        visible_kbs=[{"db_id": "db-1", "name": "FAQ"}],
        target_db_id="db-1",
    )

    assert result[0]["metadata"]["filepath"] == f"{KBS_PATH}/FAQ/auth-guide.pdf"
    assert result[0]["metadata"]["parsed_path"] == f"{KBS_PATH}/FAQ/parsed/auth-guide.pdf.md"


@pytest.mark.asyncio
async def test_inject_filepaths_into_retrieval_result_does_not_use_filename_fallback(monkeypatch) -> None:
    retrieval_chunks = [
        {
            "id": "chunk-1",
            "metadata": {
                "source": "auth-guide.pdf",
            },
        }
    ]

    monkeypatch.setattr(
        "yuxi.agents.backends.knowledge_base_backend._resolve_virtual_layout",
        lambda **kwargs: SimpleNamespace(
            source_filepaths={
                "file-1": f"{KBS_PATH}/FAQ/API/auth-guide.pdf",
                "file-2": f"{KBS_PATH}/FAQ/API/another.pdf",
            },
            parsed_filepaths={
                "file-1": f"{KBS_PATH}/FAQ/parsed/API/auth-guide.pdf.md",
                "file-2": f"{KBS_PATH}/FAQ/parsed/API/another.pdf.md",
            },
        ),
    )

    result = await inject_filepaths_into_retrieval_result(
        retrieval_chunks=retrieval_chunks,
        visible_kbs=[{"db_id": "db-1", "name": "FAQ"}],
        target_db_id="db-1",
    )

    assert "filepath" not in result[0]["metadata"]
    assert "parsed_path" not in result[0]["metadata"]


@pytest.mark.asyncio
async def test_inject_filepaths_into_retrieval_result_requires_explicit_file_id(monkeypatch) -> None:
    retrieval_chunks = [
        {
            "content": "chunk",
            "metadata": {
                "source": "http://172.19.13.5:9000/knowledgebases/kb-1/parsed/file_79c496.md",
            },
        }
    ]

    monkeypatch.setattr(
        "yuxi.agents.backends.knowledge_base_backend._resolve_virtual_layout",
        lambda **kwargs: SimpleNamespace(
            source_filepaths={
                "file_79c496": f"{KBS_PATH}/食品 相关文献/课程/营养与食品课程中的思政建设研究.pdf",
            },
            parsed_filepaths={
                "file_79c496": f"{KBS_PATH}/食品 相关文献/parsed/课程/营养与食品课程中的思政建设研究.pdf.md",
            },
        ),
    )

    result = await inject_filepaths_into_retrieval_result(
        retrieval_chunks=retrieval_chunks,
        visible_kbs=[{"db_id": "db-1", "name": "食品 相关文献"}],
        target_db_id="db-1",
    )

    assert "filepath" not in result[0]["metadata"]
    assert "parsed_path" not in result[0]["metadata"]
