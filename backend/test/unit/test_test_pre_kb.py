from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("SAVE_DIR", "/tmp/yuxi-test-saves")

from yuxi.knowledge.base import FileStatus
from yuxi.knowledge.implementations.test_pre import TestPreKB


@pytest.mark.asyncio
async def test_test_pre_parse_index_and_query_flow(monkeypatch, tmp_path: Path) -> None:
    text_path = tmp_path / "notes.txt"
    text_path.write_text(
        "Yuxi supports test_pre knowledge bases.\nKeyword retrieval is lightweight.\n",
        encoding="utf-8",
    )

    kb = TestPreKB(str(tmp_path / "workdir"))
    db_id = "kb_test_pre_1"
    kb.databases_meta[db_id] = {
        "name": "TestPre",
        "description": "test",
        "kb_type": "test_pre",
        "embed_info": {"name": "mock-embed"},
        "llm_info": None,
        "query_params": None,
        "metadata": {},
        "created_at": "2026-04-04T00:00:00Z",
    }

    async def _noop_persist_file(file_id: str) -> None:
        del file_id

    async def _fake_save_markdown_to_minio(saved_db_id: str, file_id: str, content: str) -> str:
        assert saved_db_id == db_id
        saved_markdown[file_id] = content
        return f"http://minio/kb-parsed/{saved_db_id}/parsed/{file_id}.md"

    saved_markdown: dict[str, str] = {}
    monkeypatch.setattr(kb, "_persist_file", _noop_persist_file)
    monkeypatch.setattr(kb, "_save_markdown_to_minio", _fake_save_markdown_to_minio)

    async def _fake_parser(source: str, params: dict | None = None) -> str:
        del params
        return Path(source).read_text(encoding="utf-8")

    monkeypatch.setattr("yuxi.plugins.parser.unified.Parser.aparse", _fake_parser)

    file_meta = await kb.add_file_record(db_id, str(text_path), params={"content_type": "file"})
    assert file_meta["status"] == FileStatus.UPLOADED
    assert file_meta["file_type"] == "txt"

    parsed = await kb.parse_file(db_id, file_meta["file_id"])
    assert parsed["status"] == FileStatus.PARSED
    assert parsed["markdown_file"].startswith("http://minio/kb-parsed/")
    assert "test_pre knowledge bases" in saved_markdown[file_meta["file_id"]]

    indexed = await kb.index_file(db_id, file_meta["file_id"])
    assert indexed["status"] == FileStatus.INDEXED

    async def _fake_read_markdown_from_minio(file_path: str) -> str:
        file_id = Path(file_path).stem
        return saved_markdown[file_id]

    async def _fake_generate_keywords(query_text: str, keyword_count: int) -> list[str]:
        assert "Yuxi" in query_text
        assert keyword_count == 5
        return ["Yuxi", "lightweight"]

    monkeypatch.setattr(kb, "_read_markdown_from_minio", _fake_read_markdown_from_minio)
    monkeypatch.setattr(kb, "_generate_keywords", _fake_generate_keywords)

    results = await kb.aquery("How does Yuxi do lightweight retrieval?", db_id)
    assert len(results) == 1
    assert "Yuxi supports test_pre knowledge bases." in results[0]["content"]
    assert results[0]["metadata"]["file_id"] == file_meta["file_id"]
    assert results[0]["metadata"]["match_keywords"] == ["Yuxi", "lightweight"]

    content_info = await kb.get_file_content(db_id, file_meta["file_id"])
    assert "Keyword retrieval is lightweight." in content_info["content"]
    assert content_info["lines"] == []
