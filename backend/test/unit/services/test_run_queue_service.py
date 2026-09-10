from __future__ import annotations

import asyncio

import pytest
import yuxi.services.run_queue_service as run_queue_service


class _FakeStreamRedis:
    def __init__(self):
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self.expire_calls: list[tuple[str, int]] = []
        self.pipeline_executions = 0

    def pipeline(self, *, transaction):
        """模拟单次发出的有序 Redis 命令批次。"""
        assert transaction is False
        owner = self

        class Pipeline:
            """只执行队列事件需要的两条命令。"""

            def __init__(self):
                self.commands = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                pass

            def xadd(self, *args, **kwargs):
                self.commands.append((owner.xadd, args, kwargs))

            def expire(self, *args, **kwargs):
                self.commands.append((owner.expire, args, kwargs))

            async def execute(self):
                """顺序应用命令并返回实际事件标识。"""
                owner.pipeline_executions += 1
                return [await func(*args, **kwargs) for func, args, kwargs in self.commands]

        return Pipeline()

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

    async def xread(self, streams: dict, block: int, count: int):
        del block
        result = []
        for key, start in streams.items():
            rows = list(self.streams.get(key, []))
            if start not in ("0-0", ""):
                rows = [(event_id, fields) for event_id, fields in rows if event_id > start]
            rows = rows[:count]
            if rows:
                result.append([key, rows])
        return result


@pytest.mark.asyncio
async def test_run_stream_event_roundtrip(monkeypatch: pytest.MonkeyPatch):
    fake_redis = _FakeStreamRedis()

    async def fake_get_async_redis_client():
        return fake_redis

    monkeypatch.setattr(run_queue_service, "get_async_redis_client", fake_get_async_redis_client)

    run_id = "run-1"
    seq1 = await run_queue_service.append_run_stream_event(run_id, "loading", {"items": [1]})
    seq2 = await run_queue_service.append_run_stream_event(
        run_id,
        "finished",
        {"chunk": {"status": "finished", "thread_id": "child-thread"}},
    )

    assert seq1 < seq2
    assert fake_redis.pipeline_executions == 2
    assert fake_redis.expire_calls == [("run:events:run-1", run_queue_service.RUN_EVENTS_STREAM_TTL_SECONDS)] * 2

    events = await run_queue_service.list_run_stream_events(run_id, after_seq="0-0", limit=100)
    assert [item["event_type"] for item in events] == ["loading", "finished"]
    assert events[0]["payload"]["schema_version"] == 1
    assert events[0]["payload"]["run_id"] == run_id
    assert events[0]["payload"]["payload"] == {"items": [1]}
    assert events[1]["payload"]["thread_id"] == "child-thread"

    next_events = await run_queue_service.list_run_stream_events(run_id, after_seq=seq1, limit=100)
    assert len(next_events) == 1
    assert next_events[0]["seq"] == seq2

    last_seq = await run_queue_service.get_last_run_stream_seq(run_id)
    assert last_seq == seq2

    recent_events = await run_queue_service.list_recent_run_stream_events(run_id, limit=2)
    assert [item["seq"] for item in recent_events] == [seq2, seq1]
    assert [item["event_type"] for item in recent_events] == ["finished", "loading"]


@pytest.mark.asyncio
async def test_run_stream_event_decoder_keeps_legacy_payload_shape(monkeypatch: pytest.MonkeyPatch):
    fake_redis = _FakeStreamRedis()
    key = run_queue_service._event_stream_key("run-legacy")
    fake_redis.streams[key] = [
        ("1700000000000-0", {"event_type": "custom", "payload": "not-json", "ts": "1700000000000"}),
    ]

    async def fake_get_async_redis_client():
        return fake_redis

    monkeypatch.setattr(run_queue_service, "get_async_redis_client", fake_get_async_redis_client)

    forward = await run_queue_service.list_run_stream_events("run-legacy")
    reverse = await run_queue_service.list_recent_run_stream_events("run-legacy")

    assert forward == reverse
    assert forward == [
        {
            "seq": "1700000000000-0",
            "event_type": "custom",
            "payload": {
                "schema_version": 1,
                "run_id": "run-legacy",
                "thread_id": None,
                "event": "custom",
                "payload": {},
                "created_at": None,
            },
            "ts": 1700000000000,
        }
    ]


@pytest.mark.asyncio
async def test_blocking_read_run_stream_events_reads_after_cursor(monkeypatch: pytest.MonkeyPatch):
    fake_redis = _FakeStreamRedis()

    async def fake_get_async_redis_client():
        return fake_redis

    monkeypatch.setattr(run_queue_service, "get_async_redis_client", fake_get_async_redis_client)

    run_id = "run-1"
    seq1 = await run_queue_service.append_run_stream_event(run_id, "loading", {"items": [1]})
    seq2 = await run_queue_service.append_run_stream_event(run_id, "finished", {"chunk": {}})

    events = await run_queue_service.blocking_read_run_stream_events(run_id, after_seq="0-0", block_ms=100)
    assert [item["event_type"] for item in events] == ["loading", "finished"]

    tail = await run_queue_service.blocking_read_run_stream_events(run_id, after_seq=seq1, block_ms=100)
    assert [item["seq"] for item in tail] == [seq2]


@pytest.mark.asyncio
async def test_blocking_read_run_stream_events_empty_when_no_new_events(monkeypatch: pytest.MonkeyPatch):
    fake_redis = _FakeStreamRedis()

    async def fake_get_async_redis_client():
        return fake_redis

    monkeypatch.setattr(run_queue_service, "get_async_redis_client", fake_get_async_redis_client)

    run_id = "run-1"
    seq = await run_queue_service.append_run_stream_event(run_id, "loading", {"items": [1]})

    events = await run_queue_service.blocking_read_run_stream_events(run_id, after_seq=seq, block_ms=100)
    assert events == []


def test_normalize_after_seq_stream_id_only():
    assert run_queue_service.normalize_after_seq(None) == "0-0"
    assert run_queue_service.normalize_after_seq("1700000000000-3") == "1700000000000-3"
    assert run_queue_service.normalize_after_seq("12") == "0-0"
    assert run_queue_service.normalize_after_seq("bad-value") == "0-0"


@pytest.mark.asyncio
async def test_cancel_signal_only_writes_expiring_key(monkeypatch: pytest.MonkeyPatch):
    """快速取消提示不要求 Redis 客户端支持 Pub/Sub。"""
    writes: list[tuple[str, str, int]] = []

    class KeyOnlyRedis:
        async def set(self, key: str, value: str, *, ex: int):
            writes.append((key, value, ex))

    async def key_only_client():
        return KeyOnlyRedis()

    monkeypatch.setattr(run_queue_service, "get_redis_client", key_only_client)

    await run_queue_service.publish_cancel_signal("run-1")

    assert writes == [
        (
            "run:cancel:run-1",
            "1",
            run_queue_service.RUN_CANCEL_KEY_TTL_SECONDS,
        )
    ]


@pytest.mark.asyncio
async def test_cancel_live_signal_client_failure_is_best_effort(monkeypatch: pytest.MonkeyPatch):
    """Redis 客户端获取失败不能改变 PostgreSQL 取消与终态事实。"""

    async def unavailable_client():
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(run_queue_service, "get_redis_client", unavailable_client)

    await run_queue_service.publish_cancel_signals(["run-1", "run-2"])
    await run_queue_service.clear_cancel_signal("run-1")


@pytest.mark.asyncio
async def test_cancel_signal_batch_propagates_caller_cancellation(monkeypatch: pytest.MonkeyPatch):
    """调用方取消必须终止批量发布，不能被 best-effort 策略吞掉。"""

    async def cancelled_publish(_run_id: str):
        raise asyncio.CancelledError

    monkeypatch.setattr(run_queue_service, "publish_cancel_signal", cancelled_publish)

    with pytest.raises(asyncio.CancelledError):
        await run_queue_service.publish_cancel_signals(["run-1"])


@pytest.mark.asyncio
async def test_cancel_wait_connection_failure_respects_poll_interval(monkeypatch: pytest.MonkeyPatch):
    """Redis 持续连接失败时按间隔重试且只记录一次每类故障。"""
    sleep_delays: list[float] = []
    warnings: list[str] = []

    async def unavailable_client():
        raise ConnectionError("redis unavailable")

    async def record_sleep(delay: float):
        sleep_delays.append(delay)
        if len(sleep_delays) == 5:
            raise asyncio.CancelledError

    monkeypatch.setattr(run_queue_service, "get_redis_client", unavailable_client)
    monkeypatch.setattr(run_queue_service.asyncio, "sleep", record_sleep)
    monkeypatch.setattr(run_queue_service.logger, "warning", warnings.append)

    with pytest.raises(asyncio.CancelledError):
        await run_queue_service.wait_for_cancel_signal("run-1", poll_interval_seconds=1.0)

    assert len(sleep_delays) == 5
    assert all(delay > 0.9 for delay in sleep_delays)
    assert len(warnings) == 1


@pytest.mark.asyncio
async def test_cancel_wait_polls_key_at_configured_interval(monkeypatch: pytest.MonkeyPatch):
    """取消 watcher 在两次 Redis key 读取之间等待完整轮询间隔。"""
    sleep_delays: list[float] = []
    reads = 0

    async def read_signal(_run_id: str):
        nonlocal reads
        reads += 1
        return reads == 2

    async def record_sleep(delay: float):
        sleep_delays.append(delay)

    monkeypatch.setattr(run_queue_service, "_read_cancel_signal", read_signal)
    monkeypatch.setattr(run_queue_service.asyncio, "sleep", record_sleep)

    assert await run_queue_service.wait_for_cancel_signal("run-1", poll_interval_seconds=0.2)

    assert reads == 2
    assert sleep_delays == pytest.approx([0.2], abs=0.001)


@pytest.mark.asyncio
async def test_cancel_wait_propagates_task_cancellation(monkeypatch: pytest.MonkeyPatch):
    """停止 RunContext 时，Redis key watcher 立即传播任务取消。"""
    started = asyncio.Event()
    blocked = asyncio.Event()

    async def blocked_read(_run_id: str):
        started.set()
        await blocked.wait()
        return False

    monkeypatch.setattr(run_queue_service, "_read_cancel_signal", blocked_read)
    task = asyncio.create_task(run_queue_service.wait_for_cancel_signal("run-1", poll_interval_seconds=0.01))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(asyncio.shield(task), timeout=0.2)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
