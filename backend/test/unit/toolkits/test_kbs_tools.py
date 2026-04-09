from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from yuxi.agents.toolkits.kbs import tools


def _query_kb_callable():
    callback = getattr(tools.query_kb, "coroutine", None)
    if callback is not None:
        return callback

    callback = getattr(tools.query_kb, "func", None)
    if callback is not None:
        return callback

    raise AssertionError("query_kb tool has no callable entry")


async def _run_query_kb(**kwargs):
    callback = _query_kb_callable()
    result = callback(**kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


@pytest.mark.asyncio
async def test_query_kb_injects_filepath_into_chunk_metadata(monkeypatch) -> None:
    async def _fake_retriever(query_text: str, **kwargs):
        assert query_text == "auth"
        return [
            {
                "content": "auth guide",
                "metadata": {
                    "file_id": "file-1",
                    "source": "auth-guide.pdf",
                },
            }
        ]

    monkeypatch.setattr(
        tools.knowledge_base,
        "get_retrievers",
        lambda: {
            "db-1": {
                "name": "FAQ",
                "retriever": _fake_retriever,
                "metadata": {"kb_type": "milvus"},
            }
        },
    )

    async def _fake_visible_kbs(runtime):
        return [{"db_id": "db-1", "name": "FAQ"}]

    monkeypatch.setattr(tools, "_resolve_visible_knowledge_bases_for_query", _fake_visible_kbs)

    async def _fake_inject(*, retrieval_chunks, visible_kbs, target_db_id, target_kb_name=None):
        assert visible_kbs == [{"db_id": "db-1", "name": "FAQ"}]
        assert target_db_id == "db-1"
        retrieval_chunks[0]["metadata"]["filepath"] = "/home/gem/kbs/FAQ/API/auth-guide.pdf"
        retrieval_chunks[0]["metadata"]["parsed_path"] = "/home/gem/kbs/FAQ/parsed/API/auth-guide.pdf.md"
        return retrieval_chunks

    monkeypatch.setattr(
        "yuxi.agents.backends.knowledge_base_backend.inject_filepaths_into_retrieval_result",
        _fake_inject,
    )

    runtime = SimpleNamespace(context=SimpleNamespace())
    result = await _run_query_kb(kb_name="FAQ", query_text="auth", runtime=runtime)

    assert result[0]["metadata"]["filepath"] == "/home/gem/kbs/FAQ/API/auth-guide.pdf"
    assert result[0]["metadata"]["parsed_path"] == "/home/gem/kbs/FAQ/parsed/API/auth-guide.pdf.md"


@pytest.mark.asyncio
async def test_query_kb_allows_dify_knowledge_base(monkeypatch) -> None:
    async def _fake_retriever(query_text: str, **kwargs):
        assert query_text == "auth"
        return [
            {
                "content": "auth guide",
                "score": 0.98,
                "metadata": {
                    "file_id": "dify-doc-1",
                    "source": "Dify Doc",
                },
            }
        ]

    monkeypatch.setattr(
        tools.knowledge_base,
        "get_retrievers",
        lambda: {
            "db-1": {
                "name": "FAQ",
                "retriever": _fake_retriever,
                "metadata": {"kb_type": "dify"},
            }
        },
    )

    async def _fake_visible_kbs(runtime):
        return [{"db_id": "db-1", "name": "FAQ"}]

    monkeypatch.setattr(tools, "_resolve_visible_knowledge_bases_for_query", _fake_visible_kbs)
    monkeypatch.setattr(
        "yuxi.agents.backends.knowledge_base_backend.inject_filepaths_into_retrieval_result",
        pytest.fail,
    )

    runtime = SimpleNamespace(context=SimpleNamespace())
    result = await _run_query_kb(kb_name="FAQ", query_text="auth", runtime=runtime)

    assert result == [
        {
            "content": "auth guide",
            "score": 0.98,
            "metadata": {
                "file_id": "dify-doc-1",
                "source": "Dify Doc",
            },
        }
    ]


@pytest.mark.asyncio
async def test_query_kb_returns_lightrag_result_without_filepath_injection(monkeypatch) -> None:
    async def _fake_retriever(query_text: str, **kwargs):
        assert query_text == "auth"
        return "LightRAG context"

    monkeypatch.setattr(
        tools.knowledge_base,
        "get_retrievers",
        lambda: {
            "db-1": {
                "name": "FAQ",
                "retriever": _fake_retriever,
                "metadata": {"kb_type": "lightrag"},
            }
        },
    )

    async def _fake_visible_kbs(runtime):
        return [{"db_id": "db-1", "name": "FAQ"}]

    monkeypatch.setattr(tools, "_resolve_visible_knowledge_bases_for_query", _fake_visible_kbs)
    monkeypatch.setattr(
        "yuxi.agents.backends.knowledge_base_backend.inject_filepaths_into_retrieval_result",
        pytest.fail,
    )

    runtime = SimpleNamespace(context=SimpleNamespace())
    result = await _run_query_kb(kb_name="FAQ", query_text="auth", runtime=runtime)

    assert result == "LightRAG context"


@pytest.mark.asyncio
async def test_query_kb_uses_backend_filepath_injector(monkeypatch) -> None:
    async def _fake_retriever(query_text: str, **kwargs):
        assert query_text == "auth"
        return [
            {
                "content": "auth guide",
                "metadata": {
                    "file_id": "file-1",
                    "source": "auth-guide.pdf",
                },
            }
        ]

    monkeypatch.setattr(
        tools.knowledge_base,
        "get_retrievers",
        lambda: {
            "db-1": {
                "name": "FAQ",
                "retriever": _fake_retriever,
                "metadata": {"kb_type": "milvus"},
            }
        },
    )

    async def _fake_visible_kbs(runtime):
        return [{"db_id": "db-1", "name": "FAQ"}]

    async def _fake_inject(*, retrieval_chunks, visible_kbs, target_db_id, target_kb_name=None):
        assert visible_kbs == [{"db_id": "db-1", "name": "FAQ"}]
        assert target_db_id == "db-1"
        retrieval_chunks[0]["metadata"]["filepath"] = "/home/gem/kbs/FAQ/auth-guide.pdf"
        retrieval_chunks[0]["metadata"]["parsed_path"] = "/home/gem/kbs/FAQ/parsed/auth-guide.pdf.md"
        return retrieval_chunks

    monkeypatch.setattr(tools, "_resolve_visible_knowledge_bases_for_query", _fake_visible_kbs)
    monkeypatch.setattr(
        "yuxi.agents.backends.knowledge_base_backend.inject_filepaths_into_retrieval_result",
        _fake_inject,
    )

    runtime = SimpleNamespace(context=SimpleNamespace())
    result = await _run_query_kb(kb_name="FAQ", query_text="auth", runtime=runtime)

    assert result[0]["metadata"]["filepath"] == "/home/gem/kbs/FAQ/auth-guide.pdf"
    assert result[0]["metadata"]["parsed_path"] == "/home/gem/kbs/FAQ/parsed/auth-guide.pdf.md"
