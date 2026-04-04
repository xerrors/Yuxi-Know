from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

import yuxi.services.run_worker as run_worker


class _RaisingAsyncIter:
    def __init__(self, exc: Exception):
        self._exc = exc

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise self._exc


class _BytesAsyncIter:
    def __init__(self, values: list[bytes]):
        self._values = list(values)
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._values):
            raise StopAsyncIteration
        value = self._values[self._idx]
        self._idx += 1
        return value


def _build_run() -> SimpleNamespace:
    return SimpleNamespace(
        status="pending",
        request_id="req-1",
        input_payload={
            "query": "hello",
            "config": {"thread_id": "thread-1"},
            "agent_id": "ChatbotAgent",
            "image_content": None,
            "user_id": "1",
            "request_id": "req-1",
        },
    )


def _patch_common(monkeypatch: pytest.MonkeyPatch, run_obj: SimpleNamespace):
    @asynccontextmanager
    async def fake_session_ctx():
        yield object()

    async def fake_noop(*args, **kwargs):
        del args, kwargs
        return None

    async def fake_get_run(run_id: str):
        del run_id
        return run_obj

    async def fake_load_user(user_id: str):
        del user_id
        return SimpleNamespace(id=1)

    async def fake_not_cancelled(self):
        del self
        return False

    monkeypatch.setattr(run_worker.pg_manager, "get_async_session_context", fake_session_ctx)
    monkeypatch.setattr(run_worker, "_get_run", fake_get_run)
    monkeypatch.setattr(run_worker, "_load_user", fake_load_user)
    monkeypatch.setattr(run_worker, "mark_run_running", fake_noop)
    monkeypatch.setattr(run_worker, "clear_cancel_signal", fake_noop)
    monkeypatch.setattr(run_worker, "stream_agent_chat", lambda **kwargs: object())
    monkeypatch.setattr(run_worker.RunContext, "start", fake_noop)
    monkeypatch.setattr(run_worker.RunContext, "close", fake_noop)
    monkeypatch.setattr(run_worker.RunContext, "is_cancelled", fake_not_cancelled)


@pytest.mark.asyncio
async def test_process_agent_run_non_retryable_error_marks_failed(monkeypatch: pytest.MonkeyPatch):
    run_obj = _build_run()
    _patch_common(monkeypatch, run_obj)

    terminal_statuses: list[str] = []
    events: list[str] = []

    async def fake_append_event(run_id: str, event_type: str, payload: dict):
        del run_id, payload
        events.append(event_type)

    async def fake_mark_terminal(run_id: str, status: str, error_type=None, error_message=None):
        del run_id, error_type, error_message
        terminal_statuses.append(status)

    monkeypatch.setattr(run_worker, "append_run_event", fake_append_event)
    monkeypatch.setattr(run_worker, "mark_run_terminal", fake_mark_terminal)
    monkeypatch.setattr(
        run_worker,
        "_consume_stream_with_cancel",
        lambda stream, run_ctx: _RaisingAsyncIter(RuntimeError("boom")),
    )

    await run_worker.process_agent_run({"job_try": 1}, "run-1")

    assert "error" in events
    assert terminal_statuses == ["failed"]


@pytest.mark.asyncio
async def test_process_agent_run_retryable_error_retries_then_completes(monkeypatch: pytest.MonkeyPatch):
    run_obj = _build_run()
    _patch_common(monkeypatch, run_obj)

    terminal_statuses: list[str] = []
    events: list[dict] = []
    attempts = {"count": 0}

    async def fake_append_event(run_id: str, event_type: str, payload: dict):
        del run_id
        events.append({"event_type": event_type, "payload": payload})

    async def fake_mark_terminal(run_id: str, status: str, error_type=None, error_message=None):
        del run_id, error_type, error_message
        terminal_statuses.append(status)

    def fake_consume(stream, run_ctx):
        del stream, run_ctx
        attempts["count"] += 1
        if attempts["count"] == 1:
            return _RaisingAsyncIter(run_worker.RetryableRunError("temporary failure"))
        return _BytesAsyncIter([b'{"status":"finished","request_id":"req-1"}\n'])

    monkeypatch.setattr(run_worker, "append_run_event", fake_append_event)
    monkeypatch.setattr(run_worker, "mark_run_terminal", fake_mark_terminal)
    monkeypatch.setattr(run_worker, "_consume_stream_with_cancel", fake_consume)

    with pytest.raises(run_worker.RetryableRunError):
        await run_worker.process_agent_run({"job_try": 1}, "run-1")

    assert terminal_statuses == []
    assert any(
        item["event_type"] == "error" and item["payload"]["chunk"].get("error_type") == "retryable_worker_error"
        for item in events
    )

    await run_worker.process_agent_run({"job_try": 2}, "run-1")
    assert terminal_statuses == ["completed"]


@pytest.mark.asyncio
async def test_worker_startup_ensures_builtin_mcp_servers(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    def fake_initialize():
        calls.append("initialize")

    async def fake_create_business_tables():
        calls.append("create_business_tables")

    async def fake_ensure_business_schema():
        calls.append("ensure_business_schema")

    async def fake_ensure_builtin_mcp_servers_in_db():
        calls.append("ensure_builtin_mcp_servers_in_db")

    monkeypatch.setattr(run_worker.pg_manager, "initialize", fake_initialize)
    monkeypatch.setattr(run_worker.pg_manager, "create_business_tables", fake_create_business_tables)
    monkeypatch.setattr(run_worker.pg_manager, "ensure_business_schema", fake_ensure_business_schema)
    monkeypatch.setattr(run_worker, "ensure_builtin_mcp_servers_in_db", fake_ensure_builtin_mcp_servers_in_db)

    await run_worker._worker_startup({})

    assert calls == [
        "initialize",
        "create_business_tables",
        "ensure_business_schema",
        "ensure_builtin_mcp_servers_in_db",
    ]
