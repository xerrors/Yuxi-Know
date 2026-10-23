"""MCP 与 Public HTTP 共用知识用例的检索、窗口和分页回归。"""

from __future__ import annotations

from types import MethodType, SimpleNamespace

import pytest

from yuxi.modules.knowledge.base import KnowledgeExecutor
from yuxi.modules.knowledge.manager import KnowledgeBaseManager
from yuxi.modules.knowledge.read_models import KnowledgeBaseDetail
from yuxi.modules.knowledge.services import tools


async def _call_tool(tool, *, visible_kbs=None, **kwargs):
    """在知识用例 Owner 验证结果与拒绝原因，不再依赖 Agent 本地调用。"""
    visible = visible_kbs if visible_kbs is not None else [{"kb_id": "db-1", "name": "FAQ", "kb_type": "milvus"}]
    try:
        return await tool(visible_kbs=visible, **kwargs)
    except ValueError as exc:
        return str(exc)


def _build_test_window(content: str, offset: int = 0, limit: int = 1800) -> dict:
    lines = content.splitlines()
    start = min(max(offset, 0), len(lines))
    selected = lines[start : start + limit]
    end = start + len(selected)
    return {
        "start_line": start + 1 if selected else 0,
        "end_line": end,
        "total_lines": len(lines),
        "offset": start,
        "window_size": limit,
        "has_more_before": start > 0,
        "has_more_after": end < len(lines),
        "next_offset": end if end < len(lines) else None,
        "content": "\n".join(f"{start + idx + 1:6d}\t{line}" for idx, line in enumerate(selected)),
    }


def _patch_retrievers(monkeypatch, *, kb_type: str = "milvus", retriever=None):
    async def _not_configured(*args, **kwargs):
        del args, kwargs
        raise AssertionError("knowledge base method is not configured for this test")

    async def _fake_get_database_document_support(kb_id: str):
        return (
            KnowledgeBaseDetail(
                kb_id=kb_id,
                name="FAQ",
                description=None,
                kb_type=kb_type,
                embedding_model_spec=None,
                llm_model_spec=None,
                query_params={},
                additional_params={},
                share_config={"version": 2, "read_scope": None, "manage_scope": None},
                created_by=None,
                created_at=None,
                files=None,
            ),
            kb_type != "dify",
        )

    manager = SimpleNamespace(
        find_file_content=_not_configured,
        open_file_content=_not_configured,
        get_knowledge_base_document_support=_fake_get_database_document_support,
    )

    async def _retrieve(kb_id: str, query: str, **options):
        if kb_id != "db-1":
            raise ValueError(f"知识库资源 '{kb_id}' 不存在")
        return await (retriever or object())(query, **options)

    async def _get_config(kb_id):
        """提供工具用例的类型配置。"""
        return SimpleNamespace(kb_type=kb_type)

    async def _get_executor(_kb_type):
        """让真实 Manager 的阅读入口调用受控文档源。"""

        async def _open(kb_id, file_id, *, config, offset, limit):
            """复用当前测试装配的窗口读取。"""
            return await manager.open_file_content(kb_id, file_id, offset=offset, limit=limit)

        return SimpleNamespace(supports_document_read=kb_type != "dify", open_document=_open)

    manager.get_kb_config = _get_config
    manager._get_or_create_kb_instance = _get_executor
    manager.retrieve = _retrieve
    # 复用真实 manager 的文档操作方法，使其内部走上面的 mock。
    for name in (
        "open_document",
        "find_in_document",
        "_require_kb_supports_documents",
        "knowledge_base_type_supports_documents",
    ):
        setattr(manager, name, MethodType(getattr(KnowledgeBaseManager, name), manager))
    monkeypatch.setattr(tools, "knowledge_base", manager)
    return manager


@pytest.mark.asyncio
async def test_query_kb_returns_search_schema_without_sandbox_paths(monkeypatch) -> None:
    async def _fake_retriever(query_text: str, **kwargs):
        assert query_text == "auth"
        assert kwargs == {}
        return KnowledgeExecutor.build_search_output(
            "db-1",
            [
                {
                    "content": "auth guide",
                    "metadata": {
                        "file_id": "file-1",
                        "source": "auth-guide.pdf",
                        "filepath": "/tmp/sandbox/auth-guide.pdf",
                    },
                }
            ],
        )

    _patch_retrievers(monkeypatch, retriever=_fake_retriever)
    result = await _call_tool(tools.query_kb, kb_id="db-1", query_text="auth")

    assert result["kb_id"] == "db-1"
    assert result["results"][0]["id"] == "file-1:1"
    assert result["results"][0]["kb_id"] == "db-1"
    assert result["results"][0]["file_id"] == "file-1"
    assert result["results"][0]["content"] == "auth guide"
    assert result["results"][0]["metadata"]["source"] == "auth-guide.pdf"
    assert "filepath" not in result["results"][0]["metadata"]
    assert "parsed_path" not in result["results"][0]["metadata"]


@pytest.mark.asyncio
async def test_query_kb_allows_dify_knowledge_base(monkeypatch) -> None:
    async def _fake_retriever(query_text: str, **kwargs):
        assert query_text == "auth"
        return KnowledgeExecutor.build_search_output(
            "db-1",
            [
                {
                    "content": "auth guide",
                    "score": 0.98,
                    "metadata": {
                        "file_id": "dify-doc-1",
                        "chunk_id": "dify-segment-1",
                        "source": "Dify Doc",
                    },
                }
            ],
        )

    _patch_retrievers(monkeypatch, kb_type="dify", retriever=_fake_retriever)
    result = await _call_tool(tools.query_kb, kb_id="db-1", query_text="auth")

    assert result == {
        "kb_id": "db-1",
        "results": [
            {
                "id": "dify-segment-1",
                "kb_id": "db-1",
                "file_id": "dify-doc-1",
                "content": "auth guide",
                "metadata": {
                    "file_id": "dify-doc-1",
                    "chunk_id": "dify-segment-1",
                    "source": "Dify Doc",
                    "score": 0.98,
                },
            }
        ],
    }


@pytest.mark.asyncio
async def test_query_kb_returns_plain_result_without_path_injection(monkeypatch) -> None:
    async def _fake_retriever(query_text: str, **kwargs):
        assert query_text == "auth"
        return "Milvus context"

    _patch_retrievers(monkeypatch, retriever=_fake_retriever)
    result = await _call_tool(tools.query_kb, kb_id="db-1", query_text="auth")

    assert result == "Milvus context"


@pytest.mark.asyncio
async def test_query_kb_maps_full_doc_id_and_chunk_metadata(monkeypatch) -> None:
    async def _fake_retriever(query_text: str, **kwargs):
        assert query_text == "auth"
        return KnowledgeExecutor.build_search_output(
            "db-1",
            [
                {
                    "content": "auth guide",
                    "full_doc_id": "file-1",
                    "chunk_id": "chunk-1",
                    "chunk_index": 3,
                }
            ],
        )

    _patch_retrievers(monkeypatch, retriever=_fake_retriever)
    result = await _call_tool(tools.query_kb, kb_id="db-1", query_text="auth")

    assert result["results"][0] == {
        "id": "chunk-1",
        "kb_id": "db-1",
        "file_id": "file-1",
        "content": "auth guide",
        "metadata": {"chunk_index": 3},
    }


@pytest.mark.asyncio
async def test_find_kb_document_returns_context_windows(monkeypatch) -> None:
    _patch_retrievers(monkeypatch)

    async def _fake_find_file_content(
        kb_id: str,
        file_id: str,
        patterns: list[str],
        *,
        use_regex: bool = False,
        case_sensitive: bool = False,
        max_windows: int = 5,
        window_size: int = 80,
    ):
        assert kb_id == "db-1"
        assert file_id == "file-1"
        assert patterns == ["token"]
        assert use_regex is False
        assert case_sensitive is False
        assert max_windows == 5
        assert window_size == 80
        return {
            "semantic": False,
            "match_mode": "keyword",
            "total_matches": 2,
            "windows": [
                {
                    "start_line": 1,
                    "end_line": 3,
                    "matched_lines": [2],
                    "content": "     1\tintro\n     2\ttoken value\n     3\toutro",
                }
            ],
        }

    monkeypatch.setattr(tools.knowledge_base, "find_file_content", _fake_find_file_content)

    result = await _call_tool(
        tools.find_kb_document,
        kb_id="db-1",
        file_id="file-1",
        patterns=["token"],
    )

    assert result == {
        "kb_id": "db-1",
        "file_id": "file-1",
        "semantic": False,
        "match_mode": "keyword",
        "total_matches": 2,
        "windows": [
            {
                "start_line": 1,
                "end_line": 3,
                "matched_lines": [2],
                "content": "     1\tintro\n     2\ttoken value\n     3\toutro",
            }
        ],
    }


@pytest.mark.asyncio
async def test_find_kb_document_rejects_dify(monkeypatch) -> None:
    _patch_retrievers(monkeypatch, kb_type="dify")
    result = await _call_tool(
        tools.find_kb_document,
        kb_id="db-1",
        file_id="file-1",
        patterns=["token"],
    )

    assert "只支持检索" in result


@pytest.mark.asyncio
async def test_open_kb_document_reads_markdown_content_by_default_window(monkeypatch) -> None:
    lines = [f"line {index}" for index in range(1, 2001)]

    _patch_retrievers(monkeypatch)

    async def _fake_open_file_content(kb_id: str, file_id: str, offset: int = 0, limit: int = 1800):
        assert kb_id == "db-1"
        assert file_id == "file-1"
        return _build_test_window("\n".join(lines), offset=offset, limit=limit)

    monkeypatch.setattr(tools.knowledge_base, "open_file_content", _fake_open_file_content)

    result = await _call_tool(tools.open_kb_document, kb_id="db-1", file_id="file-1")

    assert result["kb_id"] == "db-1"
    assert result["file_id"] == "file-1"
    assert result["start_line"] == 1
    assert result["end_line"] == 1800
    assert result["total_lines"] == 2000
    assert result["window_size"] == 1800
    assert result["has_more_before"] is False
    assert result["has_more_after"] is True
    assert result["next_offset"] == 1800
    assert "     1\tline 1" in result["content"]
    assert "  1800\tline 1800" in result["content"]


@pytest.mark.asyncio
async def test_open_kb_document_prefers_line_over_offset(monkeypatch) -> None:
    lines = [f"line {index}" for index in range(1, 1001)]

    _patch_retrievers(monkeypatch)

    async def _fake_open_file_content(kb_id: str, file_id: str, offset: int = 0, limit: int = 1800):
        assert kb_id == "db-1"
        assert file_id == "file-1"
        return _build_test_window("\n".join(lines), offset=offset, limit=limit)

    monkeypatch.setattr(tools.knowledge_base, "open_file_content", _fake_open_file_content)

    result = await _call_tool(
        tools.open_kb_document,
        kb_id="db-1",
        file_id="file-1",
        line=801,
        offset=0,
        window_size=10,
    )

    assert result["offset"] == 800
    assert result["start_line"] == 801
    assert result["end_line"] == 810
    assert result["has_more_before"] is True
    assert result["has_more_after"] is True
    assert result["next_offset"] == 810
    assert "   801\tline 801" in result["content"]


@pytest.mark.asyncio
async def test_open_kb_document_rejects_invisible_resource(monkeypatch) -> None:

    visible_kbs = [{"kb_id": "db-2", "name": "FAQ"}]
    result = await _call_tool(tools.open_kb_document, kb_id="db-1", file_id="file-1", visible_kbs=visible_kbs)

    assert "不存在或当前会话未启用" in result


@pytest.mark.asyncio
async def test_open_kb_document_requires_markdown_content(monkeypatch) -> None:
    _patch_retrievers(monkeypatch)

    async def _fake_open_file_content(kb_id: str, file_id: str, offset: int = 0, limit: int = 1800):
        del kb_id, file_id, offset, limit
        raise Exception("文件 file-1 没有解析后的 Markdown 内容")

    monkeypatch.setattr(tools.knowledge_base, "open_file_content", _fake_open_file_content)

    with pytest.raises(Exception, match="没有解析后的 Markdown 内容"):
        await _call_tool(tools.open_kb_document, kb_id="db-1", file_id="file-1")


@pytest.mark.asyncio
async def test_search_file_requires_kb_name_or_query(monkeypatch) -> None:
    result = await _call_tool(tools.search_file)

    assert "不能同时为空" in result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "fake_files", "expected_filenames"),
    [
        (
            {"query": "test"},
            [
                SimpleNamespace(
                    file_id="file-1",
                    filename="test.pdf",
                    file_type="file",
                    status="indexed",
                    created_at=None,
                    updated_at=None,
                    file_size=1024,
                ),
                SimpleNamespace(
                    file_id="file-2",
                    filename="test2.pdf",
                    file_type="file",
                    status="indexed",
                    created_at=None,
                    updated_at=None,
                    file_size=2048,
                ),
                SimpleNamespace(
                    file_id="file-3",
                    filename="other.pdf",
                    file_type="file",
                    status="indexed",
                    created_at=None,
                    updated_at=None,
                    file_size=512,
                ),
            ],
            ["test.pdf", "test2.pdf"],
        ),
        (
            {"kb_name": "FAQ"},
            [
                SimpleNamespace(
                    file_id="file-1",
                    filename="test.pdf",
                    file_type="file",
                    status="indexed",
                    created_at=None,
                    updated_at=None,
                    file_size=1024,
                ),
                SimpleNamespace(
                    file_id="file-2",
                    filename="other.pdf",
                    file_type="file",
                    status="indexed",
                    created_at=None,
                    updated_at=None,
                    file_size=2048,
                ),
            ],
            ["test.pdf", "other.pdf"],
        ),
    ],
)
async def test_search_file_returns_files(monkeypatch, kwargs: dict, fake_files, expected_filenames: list[str]) -> None:
    from yuxi.modules.knowledge.repositories.files import KnowledgeFileRepository

    async def _fake_search_files(
        self,
        *,
        kb_id,
        filename_query=None,
        statuses=None,
        offset=0,
        limit=100,
        files_only=True,
    ):
        del self, kb_id, statuses, files_only
        matches = [file for file in fake_files if (filename_query or "") in file.filename.lower()]
        return matches[offset : offset + limit], len(matches)

    monkeypatch.setattr(KnowledgeFileRepository, "search_files", _fake_search_files)

    result = await _call_tool(tools.search_file, **kwargs)

    assert result["total"] == len(expected_filenames)
    assert [file["filename"] for file in result["files"]] == expected_filenames


@pytest.mark.asyncio
async def test_search_file_pagination(monkeypatch) -> None:

    from types import SimpleNamespace as SN

    fake_files = [
        SN(
            file_id=f"file-{i}",
            filename=f"file{i}.pdf",
            file_type="file",
            status="indexed",
            created_at=None,
            updated_at=None,
            file_size=1024 * i,
        )
        for i in range(10)
    ]

    async def _fake_search_files(
        self,
        *,
        kb_id,
        filename_query=None,
        statuses=None,
        offset=0,
        limit=100,
        files_only=True,
    ):
        del self, kb_id, filename_query, statuses, files_only
        return fake_files[offset : offset + limit], len(fake_files)

    from yuxi.modules.knowledge.repositories.files import KnowledgeFileRepository

    monkeypatch.setattr(KnowledgeFileRepository, "search_files", _fake_search_files)

    result = await _call_tool(tools.search_file, kb_name="FAQ", offset=2, limit=3)

    assert result["total"] == 10
    assert len(result["files"]) == 3
    assert result["offset"] == 2
    assert result["limit"] == 3
    assert result["has_more"] is True


@pytest.mark.asyncio
async def test_search_file_rejects_invisible_kb(monkeypatch) -> None:

    visible_kbs = [{"kb_id": "db-2", "name": "Other"}]
    result = await _call_tool(tools.search_file, kb_name="FAQ", query="test", visible_kbs=visible_kbs)

    assert "不存在或当前会话未启用" in result


@pytest.mark.asyncio
async def test_search_file_skips_read_only_kbs(monkeypatch) -> None:

    visible_kbs = [{"kb_id": "dify-1", "name": "Dify", "kb_type": "dify"}]
    result = await _call_tool(tools.search_file, query="report", visible_kbs=visible_kbs)

    assert "只支持检索，不支持文件搜索" in result


@pytest.mark.asyncio
async def test_search_file_total_reflects_full_set_not_page(monkeypatch) -> None:
    """total/has_more 必须基于全量文件，而非按 limit/offset 截断的窗口。"""

    from types import SimpleNamespace as SN

    fake_files = [
        SN(
            file_id=f"file-{i:02d}",
            filename=f"file{i}.pdf",
            file_type="file",
            status="indexed",
            created_at=None,
            updated_at=None,
            file_size=1024,
        )
        for i in range(50)
    ]

    async def _fake_search_files(
        self,
        *,
        kb_id,
        filename_query=None,
        statuses=None,
        offset=0,
        limit=100,
        files_only=True,
    ):
        del self, kb_id, filename_query, statuses, files_only
        return fake_files[offset : offset + limit], len(fake_files)

    from yuxi.modules.knowledge.repositories.files import KnowledgeFileRepository

    monkeypatch.setattr(KnowledgeFileRepository, "search_files", _fake_search_files)

    result = await _call_tool(tools.search_file, kb_name="FAQ", offset=0, limit=10)

    assert result["total"] == 50
    assert len(result["files"]) == 10
    assert result["has_more"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [{"kb_id": "db-2"}, {"kb_id": "db-1", "kb_name": "Other"}])
async def test_search_file_id_cannot_bypass_visible_scope_or_name(monkeypatch, kwargs):
    """ID 与名称必须落在同一可见知识库内。"""
    result = await _call_tool(tools.search_file, **kwargs)
    assert "不存在或当前会话未启用" in result
