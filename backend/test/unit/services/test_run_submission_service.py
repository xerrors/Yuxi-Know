from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from yuxi.services import run_submission_service as svc
from yuxi.services.input_message_service import build_chat_input_message


class _EmptyRequestRepo:
    def __init__(self, db):
        del db

    async def get_by_request_id(self, request_id):
        del request_id
        return None


class _EmptyRunRepo:
    def __init__(self, db):
        del db

    async def get_run_by_request_id(self, request_id):
        del request_id
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "channel", "detail"),
    [
        ("x" * 33, "web", "Run origin source 不能超过 32 个字符"),
        ("chat", "x" * 33, "Run origin channel 不能超过 32 个字符"),
    ],
)
async def test_submit_run_command_rejects_overlong_origin_before_repository_access(source, channel, detail):
    command = svc.RunSubmissionCommand(
        agent_slug="translator",
        thread_id="thread-1",
        request_id="req-1",
        input_message=build_chat_input_message("hello"),
        origin=svc.RunOrigin(source=source, channel=channel),
    )

    with pytest.raises(HTTPException) as exc_info:
        await svc.submit_run_command(
            command=command,
            current_user=SimpleNamespace(uid="user-1"),
            db=object(),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == detail


@pytest.mark.asyncio
async def test_submit_run_command_shares_conversation_intake_and_finalize(monkeypatch: pytest.MonkeyPatch):
    calls: dict[str, object] = {}
    current_user = SimpleNamespace(uid="user-1", role="user")

    class Db:
        @asynccontextmanager
        async def begin_nested(self):
            yield

    class AgentRepo:
        def __init__(self, db):
            del db

        async def get_visible_by_slug(self, *, slug: str, user, kind="main"):
            assert user is current_user
            assert kind == "main"
            return SimpleNamespace(slug=slug, backend_id="ChatbotAgent")

    class ConvRepo:
        def __init__(self, db):
            del db

        async def get_conversation_by_thread_id(self, thread_id: str):
            calls["thread_id"] = thread_id
            return None

        async def add_conversation(self, **kwargs):
            calls["conversation"] = kwargs
            return SimpleNamespace(id=1, thread_id=kwargs["thread_id"])

    async def fake_intake_request(**kwargs):
        calls["intake"] = kwargs
        return SimpleNamespace(
            request_id="req-1",
            status="dispatched",
            queue_policy="enqueue",
            queue_position=None,
            message_id=10,
            run_id="run-1",
            thread_id="thread-1",
        )

    async def fake_finalize_intake(**kwargs):
        calls["finalize"] = kwargs

    monkeypatch.setattr(svc, "AgentRepository", AgentRepo)
    monkeypatch.setattr(svc, "AgentRunRequestRepository", _EmptyRequestRepo)
    monkeypatch.setattr(svc, "AgentRunRepository", _EmptyRunRepo)
    monkeypatch.setattr(svc, "ConversationRepository", ConvRepo)
    monkeypatch.setattr(svc.agent_manager, "get_agent", lambda backend_id: object())
    monkeypatch.setattr(svc, "intake_request", fake_intake_request)
    monkeypatch.setattr(svc, "finalize_intake", fake_finalize_intake)

    command = svc.RunSubmissionCommand(
        agent_slug="translator",
        thread_id="thread-1",
        request_id="req-1",
        input_message=build_chat_input_message("hello"),
        origin=svc.RunOrigin(
            source="agent_call",
            channel="api",
            external_id="external-1",
            metadata={
                "source": "spoofed",
                "channel": "spoofed",
                "agent_invocation_meta": {"trace_id": "trace-1"},
            },
        ),
        request_metadata={"request_id": "req-1", "channel": "spoofed"},
        model_spec="provider:model",
        create_conversation=True,
        conversation_title="Agent Call Run",
    )

    result = await svc.submit_run_command(command=command, current_user=current_user, db=Db())

    assert calls["conversation"]["metadata"] == {
        "source": "agent_call",
        "channel": "api",
        "agent_invocation_meta": {"trace_id": "trace-1"},
    }
    assert calls["intake"]["source"] == "agent_call"
    assert calls["intake"]["channel"] == "api"
    assert calls["intake"]["external_id"] == "external-1"
    assert calls["intake"]["origin_metadata"] == {"agent_invocation_meta": {"trace_id": "trace-1"}}
    assert calls["intake"]["meta"] == {
        "request_id": "req-1",
        "channel": "api",
        "agent_invocation_meta": {"trace_id": "trace-1"},
    }
    assert result == {
        "request_id": "req-1",
        "status": "dispatched",
        "queue_policy": "enqueue",
        "queue_position": None,
        "message_id": 10,
        "run_id": "run-1",
        "stream_url": "/api/agent/runs/run-1/events",
        "request_events_url": None,
        "thread_id": "thread-1",
    }
    assert calls["finalize"]["intake"].run_id == "run-1"


@pytest.mark.asyncio
async def test_submit_run_command_requires_existing_conversation_for_web_chat(
    monkeypatch: pytest.MonkeyPatch,
):
    current_user = SimpleNamespace(uid="user-1", role="user")

    class AgentRepo:
        def __init__(self, db):
            del db

        async def get_visible_by_slug(self, *, slug: str, user, kind="main"):
            del user, kind
            return SimpleNamespace(slug=slug, backend_id="ChatbotAgent")

    class ConvRepo:
        def __init__(self, db):
            del db

        async def get_conversation_by_thread_id(self, thread_id: str):
            del thread_id
            return None

        async def add_conversation(self, **kwargs):
            raise AssertionError(f"web chat must not create a conversation: {kwargs}")

    monkeypatch.setattr(svc, "AgentRepository", AgentRepo)
    monkeypatch.setattr(svc, "AgentRunRequestRepository", _EmptyRequestRepo)
    monkeypatch.setattr(svc, "AgentRunRepository", _EmptyRunRepo)
    monkeypatch.setattr(svc, "ConversationRepository", ConvRepo)
    monkeypatch.setattr(svc.agent_manager, "get_agent", lambda backend_id: object())

    command = svc.RunSubmissionCommand(
        agent_slug="translator",
        thread_id="missing-thread",
        request_id="req-1",
        input_message=build_chat_input_message("hello"),
        origin=svc.RunOrigin(source="chat", channel="web"),
    )

    with pytest.raises(HTTPException) as exc_info:
        await svc.submit_run_command(command=command, current_user=current_user, db=object())

    assert exc_info.value.status_code == 404
