"""PostgreSQL concurrency coverage for Agent request intake."""

from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.repositories.agent_run_request_repository import AgentRunRequestRepository
from yuxi.services import agent_request_queue_service
from yuxi.services import run_worker
from yuxi.services.input_message_service import build_chat_input_message
from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, Conversation, Message
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _cleanup_queue_test_thread(session_factory, engine, thread_id: str) -> None:
    async with session_factory() as db:
        conversation_id = await db.scalar(select(Conversation.id).where(Conversation.thread_id == thread_id))
        await db.execute(delete(AgentRunRequest).where(AgentRunRequest.conversation_thread_id == thread_id))
        if conversation_id is not None:
            await db.execute(delete(Message).where(Message.conversation_id == conversation_id))
        await db.execute(delete(AgentRun).where(AgentRun.conversation_thread_id == thread_id))
        await db.execute(delete(Conversation).where(Conversation.thread_id == thread_id))
        await db.commit()
    await engine.dispose()


async def test_concurrent_reject_requests_never_enter_queue(monkeypatch: pytest.MonkeyPatch):
    thread_id = f"pytest-reject-{uuid.uuid4()}"
    uid = f"pytest-user-{uuid.uuid4()}"
    request_ids = [f"reject-{uuid.uuid4()}" for _ in range(2)]
    engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr(agent_request_queue_service, "resolve_agent_run_config", lambda *args: ("model", "default"))

    async with session_factory() as db:
        conversation = Conversation(thread_id=thread_id, uid=uid, agent_id="main", status="active")
        db.add(conversation)
        await db.commit()

    async def submit(request_id: str):
        async with session_factory() as db:
            result = await agent_request_queue_service.intake_request(
                db=db,
                request_id=request_id,
                uid=uid,
                agent_slug="main",
                thread_id=thread_id,
                queue_policy="reject",
                input_message=build_chat_input_message(request_id),
                agent_item=MagicMock(),
                agent_backend=MagicMock(),
            )
            await db.commit()
            return result

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*(submit(request_id) for request_id in request_ids)),
            timeout=10,
        )

        assert sorted(result.status for result in results) == ["dispatched", "rejected"]

        async with session_factory() as db:
            requests = (
                (await db.execute(select(AgentRunRequest).where(AgentRunRequest.request_id.in_(request_ids))))
                .scalars()
                .all()
            )
            messages = (await db.execute(select(Message).where(Message.request_id.in_(request_ids)))).scalars().all()

        assert sorted(request.status for request in requests) == ["dispatched", "rejected"]
        assert sorted(message.delivery_status for message in messages) == ["dispatched", "rejected"]
    finally:
        async with session_factory() as db:
            conversation_id = await db.scalar(select(Conversation.id).where(Conversation.thread_id == thread_id))
            now = utc_now_naive()
            await db.execute(
                update(AgentRun)
                .where(AgentRun.conversation_thread_id == thread_id)
                .values(status="cancelled", finished_at=now, updated_at=now)
            )
            await db.execute(delete(AgentRunRequest).where(AgentRunRequest.conversation_thread_id == thread_id))
            if conversation_id is not None:
                await db.execute(delete(Message).where(Message.conversation_id == conversation_id))
            await db.commit()
        async with session_factory() as db:
            await db.execute(delete(AgentRun).where(AgentRun.conversation_thread_id == thread_id))
            await db.execute(delete(Conversation).where(Conversation.thread_id == thread_id))
            await db.commit()
        await engine.dispose()


async def test_concurrent_steer_requests_keep_one_pending(monkeypatch: pytest.MonkeyPatch):
    """Conversation 行锁保证同一线程只接受一个待处理 Steer。"""
    thread_id = f"pytest-steer-{uuid.uuid4()}"
    uid = f"pytest-user-{uuid.uuid4()}"
    active_run_id = f"active-{uuid.uuid4()}"
    active_request_id = f"active-request-{uuid.uuid4()}"
    request_ids = [f"steer-{uuid.uuid4()}" for _ in range(2)]
    engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr(agent_request_queue_service, "resolve_agent_run_config", lambda *args: ("model", "default"))

    async with session_factory() as db:
        conversation = Conversation(thread_id=thread_id, uid=uid, agent_id="main", status="active")
        db.add(conversation)
        await db.flush()
        active_message = Message(
            conversation_id=conversation.id,
            request_id=active_request_id,
            role="user",
            content="active",
            delivery_status="dispatched",
        )
        db.add(active_message)
        await db.flush()
        db.add(
            AgentRunRequest(
                request_id=active_request_id,
                uid=uid,
                agent_slug="main",
                conversation_thread_id=thread_id,
                source="chat",
                queue_policy="enqueue",
                status="dispatched",
                input_message_id=active_message.id,
                input_payload={},
            )
        )
        db.add(
            AgentRun(
                id=active_run_id,
                conversation_thread_id=thread_id,
                agent_slug="main",
                uid=uid,
                status="running",
                request_id=active_request_id,
                conversation_id=conversation.id,
                run_type="chat",
                input_payload={},
            )
        )
        await db.commit()

    async def submit(request_id: str):
        async with session_factory() as db:
            try:
                result = await agent_request_queue_service.intake_request(
                    db=db,
                    request_id=request_id,
                    uid=uid,
                    agent_slug="main",
                    thread_id=thread_id,
                    queue_policy="steer",
                    input_message=build_chat_input_message(request_id),
                    agent_item=MagicMock(),
                    agent_backend=MagicMock(),
                )
                await db.commit()
                return result
            except Exception:
                await db.rollback()
                raise

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*(submit(request_id) for request_id in request_ids), return_exceptions=True),
            timeout=10,
        )

        accepted = [result for result in results if not isinstance(result, Exception)]
        conflicts = [result for result in results if isinstance(result, HTTPException)]
        assert len(accepted) == 1
        assert accepted[0].status == "queued"
        assert accepted[0].queue_policy == "steer"
        assert len(conflicts) == 1
        assert conflicts[0].status_code == 409
        assert conflicts[0].detail["code"] == "steer_already_pending"

        async with session_factory() as db:
            requests = (
                await db.scalars(select(AgentRunRequest).where(AgentRunRequest.request_id.in_(request_ids)))
            ).all()
        assert len(requests) == 1
        assert requests[0].queue_policy == "steer"
        assert requests[0].status == "queued"
    finally:
        await _cleanup_queue_test_thread(session_factory, engine, thread_id)


async def test_concurrent_enqueue_dispatches_fifo_head(monkeypatch: pytest.MonkeyPatch):
    thread_id = f"pytest-enqueue-{uuid.uuid4()}"
    uid = f"pytest-user-{uuid.uuid4()}"
    request_ids = [f"enqueue-first-{uuid.uuid4()}", f"enqueue-second-{uuid.uuid4()}"]
    engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr(agent_request_queue_service, "resolve_agent_run_config", lambda *args: ("model", "default"))

    original_create = AgentRunRequestRepository.create
    first_request_created = asyncio.Event()
    release_first_request = asyncio.Event()
    second_request_finished = asyncio.Event()

    async def controlled_create(self, **kwargs):
        request = await original_create(self, **kwargs)
        if kwargs["request_id"] == request_ids[0]:
            first_request_created.set()
            await asyncio.wait_for(release_first_request.wait(), timeout=5)
        return request

    monkeypatch.setattr(AgentRunRequestRepository, "create", controlled_create)

    async with session_factory() as db:
        db.add(Conversation(thread_id=thread_id, uid=uid, agent_id="main", status="active"))
        await db.commit()

    async def submit(request_id: str):
        async with session_factory() as db:
            result = await agent_request_queue_service.intake_request(
                db=db,
                request_id=request_id,
                uid=uid,
                agent_slug="main",
                thread_id=thread_id,
                queue_policy="enqueue",
                input_message=build_chat_input_message(request_id),
                agent_item=MagicMock(),
                agent_backend=MagicMock(),
            )
            await db.commit()
            if request_id == request_ids[1]:
                second_request_finished.set()
            return result

    try:
        first_task = asyncio.create_task(submit(request_ids[0]))
        await asyncio.wait_for(first_request_created.wait(), timeout=5)
        second_task = asyncio.create_task(submit(request_ids[1]))

        try:
            await asyncio.wait_for(second_request_finished.wait(), timeout=1)
        except TimeoutError:
            pass
        finally:
            release_first_request.set()

        results = await asyncio.wait_for(asyncio.gather(first_task, second_task), timeout=10)

        async with session_factory() as db:
            requests = (
                (await db.execute(select(AgentRunRequest).where(AgentRunRequest.request_id.in_(request_ids))))
                .scalars()
                .all()
            )
        requests_by_id = {request.request_id: request for request in requests}
        results_by_id = {result.request_id: result for result in results}

        assert requests_by_id[request_ids[0]].status == "dispatched"
        assert results_by_id[request_ids[0]].status == "dispatched"
        assert requests_by_id[request_ids[1]].status == "queued"
        assert results_by_id[request_ids[1]].status == "queued"
    finally:
        await _cleanup_queue_test_thread(session_factory, engine, thread_id)


async def test_dispatch_retry_reenqueues_existing_pending_run(monkeypatch: pytest.MonkeyPatch):
    thread_id = f"pytest-dispatch-retry-{uuid.uuid4()}"
    uid = f"pytest-user-{uuid.uuid4()}"
    request_id = f"dispatch-retry-{uuid.uuid4()}"
    engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    enqueue_calls: list[str] = []

    async def flaky_enqueue(run_id: str):
        enqueue_calls.append(run_id)
        if len(enqueue_calls) == 1:
            raise ConnectionError("simulated Redis outage after commit")

    @asynccontextmanager
    async def session_context():
        async with session_factory() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    monkeypatch.setattr(agent_request_queue_service, "enqueue_agent_run", flaky_enqueue)
    monkeypatch.setattr(agent_request_queue_service.pg_manager, "get_async_session_context", session_context)

    async with session_factory() as db:
        conversation = Conversation(thread_id=thread_id, uid=uid, agent_id="main", status="active")
        db.add(conversation)
        await db.flush()
        message = Message(
            conversation_id=conversation.id,
            role="user",
            content="queued",
            request_id=request_id,
            delivery_status="queued",
        )
        db.add(message)
        await db.flush()
        await AgentRunRequestRepository(db).create(
            request_id=request_id,
            uid=uid,
            agent_slug="main",
            conversation_thread_id=thread_id,
            input_message_id=message.id,
            input_payload={"model_spec": "model", "tool_approval_mode": "default"},
        )
        await db.commit()

    try:
        with pytest.raises(ConnectionError, match="Redis outage"):
            await agent_request_queue_service.dispatch_next_request(
                uid=uid,
                agent_slug="main",
                thread_id=thread_id,
            )

        recovered_run_id = await agent_request_queue_service.dispatch_next_request(
            uid=uid,
            agent_slug="main",
            thread_id=thread_id,
        )

        async with session_factory() as db:
            request = await db.scalar(select(AgentRunRequest).where(AgentRunRequest.request_id == request_id))
            run = await db.scalar(select(AgentRun).where(AgentRun.request_id == request_id))

        assert request.status == "dispatched"
        assert run.status == "pending"
        assert recovered_run_id == run.id
        assert enqueue_calls == [run.id, run.id]
    finally:
        await _cleanup_queue_test_thread(session_factory, engine, thread_id)


async def test_startup_recovery_reenqueues_pending_runs_without_queue_requests(monkeypatch: pytest.MonkeyPatch):
    uid = f"pytest-user-{uuid.uuid4()}"
    run_specs = [
        (f"pytest-resume-{uuid.uuid4()}", "main", "resume"),
        (f"pytest-subagent-{uuid.uuid4()}", "worker", "subagent"),
    ]
    run_ids = [str(uuid.uuid4()) for _ in run_specs]
    engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    enqueue_calls: list[str] = []

    @asynccontextmanager
    async def session_context():
        async with session_factory() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    async def fake_enqueue(run_id: str):
        enqueue_calls.append(run_id)

    monkeypatch.setattr(agent_request_queue_service, "enqueue_agent_run", fake_enqueue)
    monkeypatch.setattr(agent_request_queue_service.pg_manager, "get_async_session_context", session_context)

    async with session_factory() as db:
        conversations = [
            Conversation(thread_id=thread_id, uid=uid, agent_id=agent_slug, status="active")
            for thread_id, agent_slug, _ in run_specs
        ]
        db.add_all(conversations)
        await db.flush()
        db.add_all(
            [
                AgentRun(
                    id=run_id,
                    conversation_thread_id=thread_id,
                    agent_slug=agent_slug,
                    uid=uid,
                    request_id=f"startup-{run_type}-{uuid.uuid4()}",
                    conversation_id=conversation.id,
                    input_payload={"model_spec": "model"},
                    status="pending",
                    run_type=run_type,
                )
                for run_id, conversation, (thread_id, agent_slug, run_type) in zip(
                    run_ids, conversations, run_specs, strict=True
                )
            ]
        )
        await db.commit()

    try:
        await agent_request_queue_service.recover_pending_dispatches()

        async with session_factory() as db:
            request_count = len(
                (
                    await db.scalars(
                        select(AgentRunRequest).where(
                            AgentRunRequest.conversation_thread_id.in_([s[0] for s in run_specs])
                        )
                    )
                ).all()
            )

        assert sorted(enqueue_calls) == sorted(run_ids)
        assert request_count == 0
    finally:
        async with session_factory() as db:
            await db.execute(delete(AgentRun).where(AgentRun.id.in_(run_ids)))
            await db.execute(delete(Conversation).where(Conversation.thread_id.in_([s[0] for s in run_specs])))
            await db.commit()
        await engine.dispose()


async def test_terminal_status_loser_does_not_change_message_delivery_status(monkeypatch: pytest.MonkeyPatch):
    thread_id = f"pytest-terminal-{uuid.uuid4()}"
    uid = f"pytest-user-{uuid.uuid4()}"
    request_id = f"terminal-{uuid.uuid4()}"
    run_id = str(uuid.uuid4())
    engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def session_context():
        async with session_factory() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    monkeypatch.setattr(run_worker.pg_manager, "get_async_session_context", session_context)

    async with session_factory() as db:
        conversation = Conversation(thread_id=thread_id, uid=uid, agent_id="main", status="active")
        db.add(conversation)
        await db.flush()
        message = Message(
            conversation_id=conversation.id,
            role="user",
            content="input",
            request_id=request_id,
            delivery_status="dispatched",
        )
        db.add(message)
        await db.flush()
        db.add(
            AgentRun(
                id=run_id,
                conversation_thread_id=thread_id,
                agent_slug="main",
                uid=uid,
                request_id=request_id,
                conversation_id=conversation.id,
                input_message_id=message.id,
                input_payload={},
                status="running",
                run_type="chat",
            )
        )
        await db.commit()

    try:
        completed = await run_worker.mark_run_terminal(run_id, "completed")
        cancelled = await run_worker.mark_run_terminal(
            run_id,
            "cancelled",
            error_type="cancelled",
            error_message="late cancel",
        )

        async with session_factory() as db:
            run = await db.scalar(select(AgentRun).where(AgentRun.id == run_id))
            message = await db.scalar(select(Message).where(Message.request_id == request_id))

        assert completed.changed is True
        assert completed.status == "completed"
        assert cancelled.changed is False
        assert cancelled.status == "completed"
        assert run.status == "completed"
        assert message.delivery_status == "complete"
    finally:
        async with session_factory() as db:
            conversation_id = await db.scalar(select(Conversation.id).where(Conversation.thread_id == thread_id))
            await db.execute(delete(AgentRun).where(AgentRun.id == run_id))
            if conversation_id is not None:
                await db.execute(delete(Message).where(Message.conversation_id == conversation_id))
            await db.execute(delete(Conversation).where(Conversation.thread_id == thread_id))
            await db.commit()
        await engine.dispose()


async def test_concurrent_request_id_reuse_across_threads_returns_scope_conflict(monkeypatch: pytest.MonkeyPatch):
    thread_ids = [f"pytest-idem-a-{uuid.uuid4()}", f"pytest-idem-b-{uuid.uuid4()}"]
    uid = f"pytest-user-{uuid.uuid4()}"
    request_id = f"shared-request-{uuid.uuid4()}"
    engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr(agent_request_queue_service, "resolve_agent_run_config", lambda *args: ("model", "default"))

    async with session_factory() as db:
        db.add_all(
            [Conversation(thread_id=thread_id, uid=uid, agent_id="main", status="active") for thread_id in thread_ids]
        )
        await db.commit()

    async def submit(thread_id: str):
        async with session_factory() as db:
            try:
                result = await agent_request_queue_service.intake_request(
                    db=db,
                    request_id=request_id,
                    uid=uid,
                    agent_slug="main",
                    thread_id=thread_id,
                    queue_policy="enqueue",
                    input_message=build_chat_input_message(thread_id),
                    agent_item=MagicMock(),
                    agent_backend=MagicMock(),
                )
                await db.commit()
                return result
            except Exception:
                await db.rollback()
                raise

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*(submit(thread_id) for thread_id in thread_ids), return_exceptions=True),
            timeout=10,
        )

        successful = [result for result in results if not isinstance(result, Exception)]
        conflicts = [result for result in results if isinstance(result, HTTPException)]
        assert len(successful) == 1
        assert successful[0].status == "dispatched"
        assert len(conflicts) == 1
        assert conflicts[0].status_code == 409
        assert conflicts[0].detail["code"] == "request_id_conflict"

        async with session_factory() as db:
            requests = (await db.scalars(select(AgentRunRequest).where(AgentRunRequest.request_id == request_id))).all()
            messages = (await db.scalars(select(Message).where(Message.request_id == request_id))).all()
            runs = (await db.scalars(select(AgentRun).where(AgentRun.request_id == request_id))).all()
        assert len(requests) == 1
        assert len(messages) == 1
        assert len(runs) == 1
    finally:
        async with session_factory() as db:
            now = utc_now_naive()
            await db.execute(
                update(AgentRun)
                .where(AgentRun.conversation_thread_id.in_(thread_ids))
                .values(status="cancelled", finished_at=now, updated_at=now)
            )
            await db.execute(delete(AgentRunRequest).where(AgentRunRequest.conversation_thread_id.in_(thread_ids)))
            conversation_ids = list(
                (await db.scalars(select(Conversation.id).where(Conversation.thread_id.in_(thread_ids)))).all()
            )
            if conversation_ids:
                await db.execute(delete(Message).where(Message.conversation_id.in_(conversation_ids)))
            await db.commit()
        async with session_factory() as db:
            await db.execute(delete(AgentRun).where(AgentRun.conversation_thread_id.in_(thread_ids)))
            await db.execute(delete(Conversation).where(Conversation.thread_id.in_(thread_ids)))
            await db.commit()
        await engine.dispose()
