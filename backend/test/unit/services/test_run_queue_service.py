from __future__ import annotations

import pytest

import yuxi.services.run_queue_service as run_queue_service


class _FakeRedisClient:
    def __init__(self, *, ping_error: Exception | None = None):
        self.ping_error = ping_error
        self.ping_calls = 0
        self.closed = False

    async def ping(self):
        self.ping_calls += 1
        if self.ping_error is not None:
            raise self.ping_error

    async def aclose(self):
        self.closed = True


class _FakeStreamRedis:
    def __init__(self):
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self.expire_calls: list[tuple[str, int]] = []

    async def xadd(self, key: str, fields: dict[str, str], **kwargs):
        del kwargs
        stream = self.streams.setdefault(key, [])
        event_id = f"{1700000000000 + len(stream)}-0"
        stream.append((event_id, dict(fields)))
        return event_id

    async def expire(self, key: str, ttl: int):
        self.expire_calls.append((key, ttl))

    async def xrange(self, key: str, min: str, max: str, count: int):
        del max
        rows = list(self.streams.get(key, []))
        if min.startswith("("):
            cursor = min[1:]
            rows = [(event_id, fields) for event_id, fields in rows if event_id > cursor]
        elif min == "-":
            rows = list(rows)
        return rows[:count]

    async def xrevrange(self, key: str, max: str, min: str, count: int):
        del max, min
        rows = list(reversed(self.streams.get(key, [])))
        return rows[:count]


@pytest.mark.asyncio
async def test_get_redis_client_ping_once_and_cache(monkeypatch: pytest.MonkeyPatch):
    redis_asyncio = pytest.importorskip("redis.asyncio")

    fake_client = _FakeRedisClient()
    monkeypatch.setattr(run_queue_service, "_redis_client", None)
    monkeypatch.setattr(
        redis_asyncio.Redis,
        "from_url",
        staticmethod(lambda *args, **kwargs: fake_client),
    )

    client_1 = await run_queue_service.get_redis_client()
    client_2 = await run_queue_service.get_redis_client()

    assert client_1 is fake_client
    assert client_2 is fake_client
    assert fake_client.ping_calls == 1


@pytest.mark.asyncio
async def test_get_redis_client_ping_fail_fast(monkeypatch: pytest.MonkeyPatch):
    redis_asyncio = pytest.importorskip("redis.asyncio")

    fake_client = _FakeRedisClient(ping_error=RuntimeError("redis unavailable"))
    monkeypatch.setattr(run_queue_service, "_redis_client", None)
    monkeypatch.setattr(
        redis_asyncio.Redis,
        "from_url",
        staticmethod(lambda *args, **kwargs: fake_client),
    )

    with pytest.raises(RuntimeError, match="Redis connection failed"):
        await run_queue_service.get_redis_client()

    assert run_queue_service._redis_client is None
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_run_stream_event_roundtrip(monkeypatch: pytest.MonkeyPatch):
    fake_redis = _FakeStreamRedis()
    monkeypatch.setattr(run_queue_service, "_redis_client", fake_redis)

    run_id = "run-1"
    seq1 = await run_queue_service.append_run_stream_event(run_id, "loading", {"items": [1]})
    seq2 = await run_queue_service.append_run_stream_event(run_id, "finished", {"chunk": {"status": "finished"}})

    assert seq1 < seq2

    events = await run_queue_service.list_run_stream_events(run_id, after_seq="0-0", limit=100)
    assert [item["event_type"] for item in events] == ["loading", "finished"]
    assert events[0]["payload"] == {"items": [1]}

    next_events = await run_queue_service.list_run_stream_events(run_id, after_seq=seq1, limit=100)
    assert len(next_events) == 1
    assert next_events[0]["seq"] == seq2

    last_seq = await run_queue_service.get_last_run_stream_seq(run_id)
    assert last_seq == seq2


def test_normalize_after_seq_stream_id_only():
    assert run_queue_service.normalize_after_seq(None) == "0-0"
    assert run_queue_service.normalize_after_seq(0) == "0-0"
    assert run_queue_service.normalize_after_seq(5) == "0-0"
    assert run_queue_service.normalize_after_seq("1700000000000-3") == "1700000000000-3"
    assert run_queue_service.normalize_after_seq("12") == "0-0"
    assert run_queue_service.normalize_after_seq("bad-value") == "0-0"
