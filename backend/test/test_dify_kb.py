from __future__ import annotations

import pytest

from yuxi.knowledge.implementations.dify import DifyKB


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, response_payload: dict | None = None, raises: Exception | None = None, **kwargs):
        del kwargs
        self._response_payload = response_payload or {}
        self._raises = raises

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def post(self, url: str, json: dict, headers: dict):
        assert "/datasets/" in url
        assert headers.get("Authorization", "").startswith("Bearer ")
        if self._raises:
            raise self._raises
        assert json["retrieval_model"]["search_method"] == "semantic_search"
        assert json["retrieval_model"]["top_k"] == 5
        assert json["retrieval_model"]["reranking_enable"] is False
        assert json["retrieval_model"]["score_threshold_enabled"] is True
        assert json["retrieval_model"]["score_threshold"] == 0.3
        return _FakeResponse(self._response_payload)


@pytest.mark.asyncio
async def test_dify_kb_aquery_maps_records(monkeypatch, tmp_path):
    kb = DifyKB(str(tmp_path))
    db_id = "kb_test_dify"
    kb.databases_meta[db_id] = {
        "name": "dify-kb",
        "description": "test",
        "kb_type": "dify",
        "query_params": {
            "options": {
                "search_mode": "vector",
                "final_top_k": 5,
                "score_threshold_enabled": True,
                "similarity_threshold": 0.3,
            }
        },
        "metadata": {
            "dify_api_url": "https://api.dify.ai/v1",
            "dify_token": "token",
            "dify_dataset_id": "dataset-123",
        },
    }

    payload = {
        "records": [
            {
                "score": 0.98,
                "segment": {
                    "id": "seg-1",
                    "position": 2,
                    "content": "hello world",
                    "document": {"id": "doc-1", "name": "Doc One"},
                },
            }
        ]
    }

    monkeypatch.setattr(
        "yuxi.knowledge.implementations.dify.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(response_payload=payload, **kwargs),
    )

    result = await kb.aquery("hello", db_id)
    assert len(result) == 1
    assert result[0]["content"] == "hello world"
    assert result[0]["score"] == 0.98
    assert result[0]["metadata"]["source"] == "Doc One"
    assert result[0]["metadata"]["file_id"] == "doc-1"
    assert result[0]["metadata"]["chunk_id"] == "seg-1"
    assert result[0]["metadata"]["chunk_index"] == 2


@pytest.mark.asyncio
async def test_dify_kb_aquery_error_returns_empty(monkeypatch, tmp_path):
    kb = DifyKB(str(tmp_path))
    db_id = "kb_test_dify_error"
    kb.databases_meta[db_id] = {
        "name": "dify-kb",
        "description": "test",
        "kb_type": "dify",
        "query_params": {"options": {}},
        "metadata": {
            "dify_api_url": "https://api.dify.ai/v1",
            "dify_token": "token",
            "dify_dataset_id": "dataset-123",
        },
    }

    monkeypatch.setattr(
        "yuxi.knowledge.implementations.dify.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(raises=RuntimeError("boom"), **kwargs),
    )

    result = await kb.aquery("hello", db_id)
    assert result == []
