"""复用会话时 Run origin 来源快照回填会话 extra_metadata 的集成测试。"""

from __future__ import annotations

import asyncio
import os
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.services import agent_request_service
from yuxi.services.agent_request_service import AgentRequestInput, RunOrigin
from yuxi.services.input_message_service import build_chat_input_message
from yuxi.storage.postgres.models_business import AgentRun, AgentRunRequest, Conversation, Message, Project, User

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _seed_conversation(session_factory, *, thread_id: str, uid: str, extra_metadata: dict | None):
    async with session_factory() as db:
        db.add(User(username=uid, uid=uid, password_hash="test"))
        await db.flush()
        project_id = str(uuid.uuid4())
        db.add(
            Project(
                id=project_id,
                uid=uid,
                selection_status="implicit",
                workdir_path=f"projects/{project_id}",
                directory_mode="managed",
            )
        )
        db.add(
            Conversation(
                thread_id=thread_id,
                uid=uid,
                project_id=project_id,
                agent_id="default-chatbot",
                status="active",
                extra_metadata=extra_metadata,
            )
        )
        await db.commit()


async def _persist_eval_request(session_factory, *, thread_id: str, uid: str, metadata: dict | None = None):
    request_id = f"origin-{uuid.uuid4()}"
    async with session_factory() as db:
        current_user = (await db.execute(select(User).where(User.uid == uid))).scalar_one()
        await agent_request_service.submit_agent_request(
            request_input=AgentRequestInput(
                request_id=request_id,
                agent_slug="default-chatbot",
                thread_id=thread_id,
                input_message=build_chat_input_message(request_id),
                queue_policy="reject",
                origin=RunOrigin(
                    source="agent_evaluation",
                    channel="api",
                    metadata=metadata or {"evaluation_batch": "batch-1"},
                ),
            ),
            current_user=current_user,
            db=db,
        )
        await db.commit()


async def _cleanup(session_factory, *, thread_id: str, uid: str) -> None:
    async with session_factory() as db:
        row = (await db.execute(select(Conversation.id).where(Conversation.thread_id == thread_id))).one_or_none()
        await db.execute(delete(AgentRunRequest).where(AgentRunRequest.conversation_thread_id == thread_id))
        if row is not None:
            await db.execute(delete(Message).where(Message.conversation_id == row.id))
        await db.execute(delete(AgentRun).where(AgentRun.conversation_thread_id == thread_id))
        await db.execute(delete(Conversation).where(Conversation.thread_id == thread_id))
        await db.execute(delete(Project).where(Project.uid == uid))
        await db.execute(delete(User).where(User.uid == uid))
        await db.commit()


async def test_reused_conversation_backfills_missing_origin(monkeypatch: pytest.MonkeyPatch):
    """复用无来源快照的会话时，本次 Run 的 origin 键被补写且不破坏既有元数据。"""
    monkeypatch.setattr(agent_request_service, "resolve_agent_run_config", AsyncMock(return_value=("model", "default")))
    monkeypatch.setattr(agent_request_service, "enqueue_agent_run", AsyncMock(return_value=None))
    engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    thread_id = f"pytest-origin-{uuid.uuid4()}"
    uid = f"pytest-origin-user-{uuid.uuid4()}"
    try:
        await _seed_conversation(session_factory, thread_id=thread_id, uid=uid, extra_metadata={"pinned": True})
        await _persist_eval_request(session_factory, thread_id=thread_id, uid=uid)
        async with session_factory() as db:
            metadata = await db.scalar(select(Conversation.extra_metadata).where(Conversation.thread_id == thread_id))
        assert metadata["pinned"] is True
        assert metadata["source"] == "agent_evaluation"
        assert metadata["channel"] == "api"
        assert metadata["evaluation_batch"] == "batch-1"
    finally:
        await _cleanup(session_factory, thread_id=thread_id, uid=uid)
        await engine.dispose()


async def test_reused_conversation_keeps_existing_origin(monkeypatch: pytest.MonkeyPatch):
    """已有来源的会话不被后续请求覆盖：回填仅补缺失键。"""
    monkeypatch.setattr(agent_request_service, "resolve_agent_run_config", AsyncMock(return_value=("model", "default")))
    monkeypatch.setattr(agent_request_service, "enqueue_agent_run", AsyncMock(return_value=None))
    engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    thread_id = f"pytest-origin-{uuid.uuid4()}"
    uid = f"pytest-origin-user-{uuid.uuid4()}"
    try:
        await _seed_conversation(session_factory, thread_id=thread_id, uid=uid, extra_metadata={"source": "chat"})
        await _persist_eval_request(session_factory, thread_id=thread_id, uid=uid)
        async with session_factory() as db:
            metadata = await db.scalar(select(Conversation.extra_metadata).where(Conversation.thread_id == thread_id))
        assert metadata["source"] == "chat"
        assert metadata["channel"] == "api"
    finally:
        await _cleanup(session_factory, thread_id=thread_id, uid=uid)
        await engine.dispose()


async def test_concurrent_reuse_merges_both_origins_without_lost_update(monkeypatch: pytest.MonkeyPatch):
    """两个不同来源并发复用同一无来源会话：锁内重读合并，两边的键都不丢失。

    负向：回填若发生在行锁之前（陈旧快照整体覆写），本用例会因先提交者的键被后提交者
    丢失而失败（batch_a/batch_b 不再同时存在）。
    """
    monkeypatch.setattr(agent_request_service, "resolve_agent_run_config", AsyncMock(return_value=("model", "default")))
    monkeypatch.setattr(agent_request_service, "enqueue_agent_run", AsyncMock(return_value=None))
    engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    thread_id = f"pytest-origin-{uuid.uuid4()}"
    uid = f"pytest-origin-user-{uuid.uuid4()}"

    async def submit(source: str, channel: str, metadata: dict) -> None:
        request_id = f"origin-{uuid.uuid4()}"
        async with session_factory() as db:
            current_user = (await db.execute(select(User).where(User.uid == uid))).scalar_one()
            await agent_request_service.submit_agent_request(
                request_input=AgentRequestInput(
                    request_id=request_id,
                    agent_slug="default-chatbot",
                    thread_id=thread_id,
                    input_message=build_chat_input_message(request_id),
                    queue_policy="reject",
                    origin=RunOrigin(source=source, channel=channel, metadata=metadata),
                ),
                current_user=current_user,
                db=db,
            )
            await db.commit()

    try:
        await _seed_conversation(session_factory, thread_id=thread_id, uid=uid, extra_metadata=None)
        await asyncio.gather(
            submit("agent_evaluation", "api", {"batch_a": "1"}),
            submit("chat", "web", {"batch_b": "2"}),
        )
        async with session_factory() as db:
            metadata = await db.scalar(select(Conversation.extra_metadata).where(Conversation.thread_id == thread_id))
        assert metadata is not None
        assert metadata.get("batch_a") == "1"
        assert metadata.get("batch_b") == "2"
        assert metadata.get("source") in {"agent_evaluation", "chat"}
        assert metadata.get("channel") in {"api", "web"}
    finally:
        await _cleanup(session_factory, thread_id=thread_id, uid=uid)
        await engine.dispose()
