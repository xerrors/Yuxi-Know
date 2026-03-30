from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

import yuxi.services.agent_run_service as agent_run_service


class FakeConfigRepo:
    def __init__(self, db_session):
        self.db = db_session

    async def get_by_id(self, config_id: int):
        return SimpleNamespace(id=config_id, agent_id="ChatbotAgent", department_id=1)


@pytest.mark.asyncio
async def test_stream_agent_run_events_emits_error_and_close_on_db_error(monkeypatch: pytest.MonkeyPatch):
    @asynccontextmanager
    async def fake_session_ctx():
        yield object()

    class BrokenRepo:
        def __init__(self, db):
            self.db = db

        async def get_run_for_user(self, run_id: str, user_id: str):
            del run_id, user_id
            raise RuntimeError("db down")

    monkeypatch.setattr(agent_run_service.pg_manager, "get_async_session_context", fake_session_ctx)
    monkeypatch.setattr(agent_run_service, "AgentRunRepository", BrokenRepo)

    chunks = []
    async for chunk in agent_run_service.stream_agent_run_events(
        run_id="run-1",
        after_seq="0",
        current_user_id="1",
    ):
        chunks.append(chunk)

    assert len(chunks) == 2
    assert chunks[0].startswith("event: error")
    assert '"reason": "db_error"' in chunks[0]
    assert chunks[1].startswith("event: close")


@pytest.mark.asyncio
async def test_stream_agent_run_events_reads_redis_and_close_terminal(monkeypatch: pytest.MonkeyPatch):
    @asynccontextmanager
    async def fake_session_ctx():
        yield object()

    class Repo:
        def __init__(self, db):
            self.db = db

        async def get_run_for_user(self, run_id: str, user_id: str):
            del run_id, user_id
            return SimpleNamespace(status="completed")

    calls = {"count": 0}

    async def fake_list_events(run_id: str, *, after_seq: str, limit: int):
        del run_id, after_seq, limit
        calls["count"] += 1
        if calls["count"] == 1:
            return [
                {
                    "seq": "1700000000000-0",
                    "event_type": "loading",
                    "payload": {"items": [{"status": "loading", "response": "你"}]},
                    "ts": 1700000000000,
                }
            ]
        return []

    async def fake_last_seq(run_id: str):
        del run_id
        return "1700000000000-0"

    monkeypatch.setattr(agent_run_service.pg_manager, "get_async_session_context", fake_session_ctx)
    monkeypatch.setattr(agent_run_service, "AgentRunRepository", Repo)
    monkeypatch.setattr(agent_run_service, "list_run_stream_events", fake_list_events)
    monkeypatch.setattr(agent_run_service, "get_last_run_stream_seq", fake_last_seq)
    monkeypatch.setattr(agent_run_service, "SSE_POLL_INTERVAL_SECONDS", 0)

    chunks = []
    async for chunk in agent_run_service.stream_agent_run_events(
        run_id="run-1",
        after_seq="0",
        current_user_id="1",
    ):
        chunks.append(chunk)

    assert any(item.startswith("event: loading") for item in chunks)
    assert chunks[-1].startswith("event: close")
    assert '"last_seq": "1700000000000-0"' in chunks[-1]


@pytest.mark.asyncio
async def test_create_agent_run_commits_before_enqueue(monkeypatch: pytest.MonkeyPatch):
    class FakeDB:
        def __init__(self):
            self.order: list[str] = []
            self.committed = False

        async def commit(self):
            self.order.append("commit")
            self.committed = True

        async def rollback(self):
            raise AssertionError("rollback should not be called")

    db = FakeDB()
    created_run = SimpleNamespace(
        id="run-1",
        thread_id="thread-1",
        status="pending",
        request_id="req-1",
        user_id="1",
    )

    class Repo:
        def __init__(self, db_session):
            self.db = db_session

        async def get_run_by_request_id(self, request_id: str):
            del request_id
            return None

        async def create_run(self, **kwargs):
            assert kwargs["request_id"] == "req-1"
            return created_run

    class ConvRepo:
        def __init__(self, db_session):
            self.db = db_session

        async def get_conversation_by_thread_id(self, thread_id: str):
            del thread_id
            return SimpleNamespace(user_id="1", status="active", department_id=1, extra_metadata={"agent_config_id": 1})

    class Queue:
        async def enqueue_job(self, job_name: str, run_id: str, _job_id: str):
            assert job_name == "process_agent_run"
            assert run_id == "run-1"
            assert _job_id == "run:run-1"
            db.order.append("enqueue")
            assert db.committed is True

    async def fake_get_arq_pool():
        return Queue()

    monkeypatch.setattr(agent_run_service.agent_manager, "get_agent", lambda agent_id: object())
    monkeypatch.setattr(agent_run_service, "AgentConfigRepository", FakeConfigRepo)
    monkeypatch.setattr(agent_run_service, "ConversationRepository", ConvRepo)
    monkeypatch.setattr(agent_run_service, "AgentRunRepository", Repo)
    monkeypatch.setattr(agent_run_service, "get_arq_pool", fake_get_arq_pool)

    result = await agent_run_service.create_agent_run_view(
        query="hello",
        agent_config_id=1,
        thread_id="thread-1",
        meta={"request_id": "req-1"},
        image_content=None,
        current_user_id="1",
        db=db,
    )

    assert db.order == ["commit", "enqueue"]
    assert result["run_id"] == "run-1"
    assert result["request_id"] == "req-1"


@pytest.mark.asyncio
async def test_create_agent_run_handles_integrity_error_with_same_user_existing(monkeypatch: pytest.MonkeyPatch):
    class FakeDB:
        def __init__(self):
            self.commit_called = 0
            self.rollback_called = 0

        async def commit(self):
            self.commit_called += 1
            raise IntegrityError("insert", {"request_id": "req-1"}, Exception("duplicate"))

        async def rollback(self):
            self.rollback_called += 1

    db = FakeDB()
    existing_run = SimpleNamespace(
        id="run-existing",
        thread_id="thread-1",
        status="running",
        request_id="req-1",
        user_id="1",
    )
    state = {"lookup_count": 0}

    class Repo:
        def __init__(self, db_session):
            self.db = db_session

        async def get_run_by_request_id(self, request_id: str):
            del request_id
            state["lookup_count"] += 1
            if state["lookup_count"] == 1:
                return None
            return existing_run

        async def create_run(self, **kwargs):
            del kwargs
            return SimpleNamespace(
                id="run-new",
                thread_id="thread-1",
                status="pending",
                request_id="req-1",
                user_id="1",
            )

    class ConvRepo:
        def __init__(self, db_session):
            self.db = db_session

        async def get_conversation_by_thread_id(self, thread_id: str):
            del thread_id
            return SimpleNamespace(user_id="1", status="active", department_id=1, extra_metadata={"agent_config_id": 1})

    async def fake_get_arq_pool():
        raise AssertionError("should not enqueue on integrity fallback")

    monkeypatch.setattr(agent_run_service.agent_manager, "get_agent", lambda agent_id: object())
    monkeypatch.setattr(agent_run_service, "AgentConfigRepository", FakeConfigRepo)
    monkeypatch.setattr(agent_run_service, "ConversationRepository", ConvRepo)
    monkeypatch.setattr(agent_run_service, "AgentRunRepository", Repo)
    monkeypatch.setattr(agent_run_service, "get_arq_pool", fake_get_arq_pool)

    result = await agent_run_service.create_agent_run_view(
        query="hello",
        agent_config_id=1,
        thread_id="thread-1",
        meta={"request_id": "req-1"},
        image_content=None,
        current_user_id="1",
        db=db,
    )

    assert db.commit_called == 1
    assert db.rollback_called == 1
    assert result["run_id"] == "run-existing"
    assert result["status"] == "running"


@pytest.mark.asyncio
async def test_create_agent_run_integrity_error_returns_409_for_other_user(monkeypatch: pytest.MonkeyPatch):
    class FakeDB:
        async def commit(self):
            raise IntegrityError("insert", {"request_id": "req-1"}, Exception("duplicate"))

        async def rollback(self):
            return None

    db = FakeDB()
    existing_run = SimpleNamespace(
        id="run-existing",
        thread_id="thread-1",
        status="pending",
        request_id="req-1",
        user_id="2",
    )
    state = {"lookup_count": 0}

    class Repo:
        def __init__(self, db_session):
            self.db = db_session

        async def get_run_by_request_id(self, request_id: str):
            del request_id
            state["lookup_count"] += 1
            if state["lookup_count"] == 1:
                return None
            return existing_run

        async def create_run(self, **kwargs):
            del kwargs
            return SimpleNamespace(
                id="run-new",
                thread_id="thread-1",
                status="pending",
                request_id="req-1",
                user_id="1",
            )

    class ConvRepo:
        def __init__(self, db_session):
            self.db = db_session

        async def get_conversation_by_thread_id(self, thread_id: str):
            del thread_id
            return SimpleNamespace(user_id="1", status="active", department_id=1, extra_metadata={"agent_config_id": 1})

    monkeypatch.setattr(agent_run_service.agent_manager, "get_agent", lambda agent_id: object())
    monkeypatch.setattr(agent_run_service, "AgentConfigRepository", FakeConfigRepo)
    monkeypatch.setattr(agent_run_service, "ConversationRepository", ConvRepo)
    monkeypatch.setattr(agent_run_service, "AgentRunRepository", Repo)

    with pytest.raises(agent_run_service.HTTPException) as exc:
        await agent_run_service.create_agent_run_view(
            query="hello",
            agent_config_id=1,
            thread_id="thread-1",
            meta={"request_id": "req-1"},
            image_content=None,
            current_user_id="1",
            db=db,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "request_id 冲突"
