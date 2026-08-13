from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import yuxi.knowledge.cache as cache_module

pytestmark = pytest.mark.unit


class _FakeRedis:
    def __init__(self):
        self.data = {}
        self.locks = []

    async def get(self, key: str):
        return self.data.get(key)

    async def set(self, key: str, value: str, *, ex: int):
        self.data[key] = value
        self.expires = (key, ex)

    async def delete(self, key: str):
        self.data.pop(key, None)

    def lock(self, key: str, *, timeout: int, blocking_timeout: int):
        self.locks.append((key, timeout, blocking_timeout))
        return _FakeLock()


class _FakeLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def _row():
    return SimpleNamespace(
        kb_id="kb_1",
        name="Knowledge",
        description="Description",
        kb_type="milvus",
        embedding_model_spec="provider:embedding",
        llm_model_spec=None,
        query_params={"options": {"top_k": 5}},
        additional_params={
            "chunking": {"preset_id": "general"},
            "stats": {"file_count": 3},
        },
        created_at=None,
    )


@pytest.mark.asyncio
async def test_cache_round_trip(monkeypatch):
    redis = _FakeRedis()
    monkeypatch.setattr(cache_module, "get_async_redis_client", lambda: _async_value(redis))

    await cache_module.cache_kb_config(_row())
    snapshot = await cache_module.get_cached_kb_config("kb_1")

    assert set(snapshot) == {
        "kb_id",
        "kb_type",
        "embedding_model_spec",
        "query_params",
        "additional_params",
    }
    assert snapshot["query_params"] == {"options": {"top_k": 5}}
    assert "stats" not in snapshot["additional_params"]
    key = f"{cache_module.KNOWLEDGE_BASE_CACHE_KEY_PREFIX}kb_1"
    assert json.loads(redis.data[key])["kb_type"] == "milvus"
    assert redis.expires == (key, cache_module.KNOWLEDGE_BASE_CACHE_TTL_SECONDS)


@pytest.mark.asyncio
async def test_cache_read_failure_returns_miss(monkeypatch):
    async def fail_client():
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(cache_module, "get_async_redis_client", fail_client)

    assert await cache_module.get_cached_kb_config("kb_1") is None


@pytest.mark.asyncio
async def test_cache_lock_uses_kb_scoped_key(monkeypatch):
    redis = _FakeRedis()
    monkeypatch.setattr(cache_module, "get_async_redis_client", lambda: _async_value(redis))

    async with cache_module.kb_config_cache_lock("kb_1"):
        pass

    assert redis.locks == [
        (
            f"{cache_module.KNOWLEDGE_BASE_CACHE_KEY_PREFIX}kb_1:lock",
            cache_module.KNOWLEDGE_BASE_CACHE_LOCK_TIMEOUT_SECONDS,
            cache_module.KNOWLEDGE_BASE_CACHE_LOCK_WAIT_SECONDS,
        )
    ]


@pytest.mark.asyncio
async def test_cache_delete_failure_is_visible(monkeypatch):
    async def fail_client():
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(cache_module, "get_async_redis_client", fail_client)

    with pytest.raises(ConnectionError, match="redis unavailable"):
        await cache_module.delete_cached_kb_config("kb_1")


async def _async_value(value):
    return value
