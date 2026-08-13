"""Agent run request repository unit tests."""

from __future__ import annotations

from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from yuxi.repositories.agent_run_request_repository import AgentRunRequestRepository
from yuxi.storage.postgres.models_business import AgentRunRequest, Base, Conversation, Message
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


@pytest_asyncio.fixture()
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add(Conversation(id=10, thread_id="thread-1", uid="user-1", agent_id="main", status="active"))
        db.add(Message(id=100, conversation_id=10, role="user", content="hello"))
        await db.commit()
        yield db
    await engine.dispose()


def _make_request(
    db,
    *,
    request_id: str,
    created_at,
    status: str = "queued",
    uid: str = "user-1",
    agent_slug: str = "main",
    conversation_thread_id: str = "thread-1",
    input_message_id: int = 100,
) -> AgentRunRequest:
    req = AgentRunRequest(
        request_id=request_id,
        uid=uid,
        agent_slug=agent_slug,
        conversation_thread_id=conversation_thread_id,
        source="chat",
        queue_policy="enqueue",
        status=status,
        input_message_id=input_message_id,
        input_payload={},
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(req)
    return req


async def test_create_persists_request_with_queued_status(session):
    repo = AgentRunRequestRepository(session)
    created = await repo.create(
        request_id="req-new",
        uid="user-1",
        agent_slug="main",
        conversation_thread_id="thread-1",
        input_message_id=100,
    )
    fetched = await repo.get_by_request_id("req-new")
    assert fetched is created
    assert created.status == "queued"


async def test_create_persists_origin_metadata(session):
    created = await AgentRunRequestRepository(session).create(
        request_id="origin-request",
        uid="user-1",
        agent_slug="main",
        conversation_thread_id="thread-1",
        source="agent_call",
        channel="api",
        external_id="external-1",
        origin_metadata={"agent_invocation_meta": {"trace_id": "trace-1"}},
        input_message_id=100,
    )
    await session.commit()

    assert created.source == "agent_call"
    assert created.channel == "api"
    assert created.external_id == "external-1"
    assert created.origin_metadata == {"agent_invocation_meta": {"trace_id": "trace-1"}}


async def test_get_by_request_id_returns_none_when_missing(session):
    repo = AgentRunRequestRepository(session)
    assert await repo.get_by_request_id("nope") is None


async def test_get_queue_head_returns_earliest_queued(session):
    repo = AgentRunRequestRepository(session)
    base = utc_now_naive()
    _make_request(session, request_id="req-later", created_at=base + timedelta(seconds=10))
    _make_request(session, request_id="req-early", created_at=base)
    _make_request(session, request_id="req-other", created_at=base, conversation_thread_id="thread-2")
    _make_request(session, request_id="req-dispatched", created_at=base, status="dispatched")
    await session.commit()

    head = await repo.get_queue_head(uid="user-1", agent_slug="main", conversation_thread_id="thread-1")
    assert head is not None
    assert head.request_id == "req-early"


async def test_get_queue_head_returns_none_when_no_queued(session):
    repo = AgentRunRequestRepository(session)
    _make_request(session, request_id="req-1", created_at=utc_now_naive(), status="dispatched")
    await session.commit()
    assert await repo.get_queue_head(uid="user-1", agent_slug="main", conversation_thread_id="thread-1") is None


async def test_list_queued_returns_in_fifo_order(session):
    repo = AgentRunRequestRepository(session)
    base = utc_now_naive()
    _make_request(session, request_id="req-2", created_at=base + timedelta(seconds=5))
    _make_request(session, request_id="req-1", created_at=base)
    _make_request(session, request_id="req-3", created_at=base, status="cancelled")
    await session.commit()

    queued = await repo.list_queued(uid="user-1", agent_slug="main", conversation_thread_id="thread-1")
    assert [r.request_id for r in queued] == ["req-1", "req-2"]


async def test_mark_dispatched_binds_run_id(session):
    repo = AgentRunRequestRepository(session)
    _make_request(session, request_id="req-1", created_at=utc_now_naive())
    await session.commit()

    result = await repo.mark_dispatched("req-1", run_id="run-abc")
    assert result is not None
    assert result.status == "dispatched"
    assert result.dispatched_run_id == "run-abc"


async def test_mark_dispatched_skips_non_queued(session):
    repo = AgentRunRequestRepository(session)
    _make_request(session, request_id="req-1", created_at=utc_now_naive(), status="cancelled")
    await session.commit()

    result = await repo.mark_dispatched("req-1", run_id="run-abc")
    assert result is None


async def test_get_queue_head_scoped_to_user(session):
    repo = AgentRunRequestRepository(session)
    _make_request(session, request_id="req-user2", created_at=utc_now_naive(), uid="user-2")
    await session.commit()

    head = await repo.get_queue_head(uid="user-1", agent_slug="main", conversation_thread_id="thread-1")
    assert head is None


async def test_fifo_tiebreak_by_id(session):
    """相同 created_at 时按 id 升序（自增主键保持插入顺序）。"""
    repo = AgentRunRequestRepository(session)
    base = utc_now_naive()
    _make_request(session, request_id="req-first", created_at=base)
    _make_request(session, request_id="req-second", created_at=base)
    await session.commit()

    head = await repo.get_queue_head(uid="user-1", agent_slug="main", conversation_thread_id="thread-1")
    assert head is not None
    assert head.request_id == "req-first"
