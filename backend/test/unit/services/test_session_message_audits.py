from datetime import datetime
from types import SimpleNamespace

import pytest

import yuxi.modules.agents.services.message_audits as messages
from yuxi.modules.agents.scope import ActorScope


@pytest.mark.asyncio
async def test_get_thread_message_audits_view_serializes_model_and_tool_facts(monkeypatch):
    model_message = SimpleNamespace(
        id=17,
        role="assistant",
        content="模型输出",
        created_at=datetime(2026, 8, 30, 1, 0, 0),
        run_id="run-1",
        turn_id="turn-1",
        message_type="model_audit",
        operation_id="model-1",
        started_at=datetime(2026, 8, 30, 1, 0, 1),
        finished_at=datetime(2026, 8, 30, 1, 0, 2),
        duration_ms=875,
        sequence=12,
        execution_status="completed",
        usage={"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
        extra_metadata={
            "namespace": ["agent", "model"],
            "model_run_id": "langgraph-model-1",
            "finished_sequence": 18,
            "content": [{"type": "text", "text": "模型输出"}],
            "tool_calls": [],
            "private_internal_field": "must-not-leak",
        },
        tool_calls=[],
    )
    tool_message = SimpleNamespace(
        id=18,
        role="tool",
        content="查询结果",
        created_at=datetime(2026, 8, 30, 1, 0, 2),
        run_id="run-1",
        turn_id="turn-1",
        message_type="tool_audit",
        operation_id="call-1",
        started_at=datetime(2026, 8, 30, 1, 0, 2),
        finished_at=datetime(2026, 8, 30, 1, 0, 3),
        duration_ms=120,
        sequence=14,
        execution_status="completed",
        usage=None,
        extra_metadata={
            "namespace": [],
            "tool_call_id": "call-1",
            "tool_name": "search",
            "input": {"q": "Yuxi"},
            "output": {"type": "tool", "content": "查询结果", "status": "success"},
            "error_message": None,
            "source_model_operation_id": "model-1",
            "finished_sequence": 15,
            "private_internal_field": "must-not-leak",
        },
        tool_calls=[],
    )
    run = SimpleNamespace(
        id="run-1",
        status="completed",
        created_at=datetime(2026, 8, 30, 1, 0, 0),
        started_at=datetime(2026, 8, 30, 1, 0, 1),
        prepared_at=datetime(2026, 8, 30, 1, 0, 1),
        first_output_at=datetime(2026, 8, 30, 1, 0, 2),
        finished_at=datetime(2026, 8, 30, 1, 0, 3),
    )

    class FakeSessionRepository:
        def __init__(self, _db):
            pass

        async def get_session_by_thread_id(self, _thread_id):
            return SimpleNamespace(id=7, uid="user-1", app_id=None, status="active")

        async def list_message_audits(self, session_record_id, *, limit):
            assert session_record_id == 7
            assert limit == messages.MESSAGE_AUDIT_LIMIT
            return [model_message, tool_message], True

        async def list_agent_runs_for_trace(self, session_record_id, *, limit):
            assert session_record_id == 7
            assert limit == messages.AGENT_RUN_TRACE_LIMIT
            return [run], True

    monkeypatch.setattr(messages, "MessageRepository", FakeSessionRepository)
    monkeypatch.setattr(messages, "AgentRunRepository", FakeSessionRepository)

    async def visible_thread(**_kwargs):
        """模拟已通过完整作用域查询的 Thread。"""
        return SimpleNamespace(id=7)

    monkeypatch.setattr(messages, "require_thread", visible_thread)

    result = await messages.get_thread_audits(
        thread_id="thread-1",
        scope=ActorScope(uid="user-1", app_id=None, is_superadmin=True),
        db=object(),
    )

    assert [item["type"] for item in result["audits"]] == ["ai", "tool"]
    assert result["truncated"] is True
    assert result["runs_truncated"] is True
    assert result["runs"] == [
        {
            "run_id": "run-1",
            "status": "completed",
            "timing": {
                "created_at": "2026-08-30T01:00:00Z",
                "started_at": "2026-08-30T01:00:01Z",
                "prepared_at": "2026-08-30T01:00:01Z",
                "first_model_request_at": None,
                "first_output_at": "2026-08-30T01:00:02Z",
                "finished_at": "2026-08-30T01:00:03Z",
                "dispatch_latency_ms": 1000,
                "preparation_latency_ms": 0,
                "first_model_request_latency_ms": None,
                "model_first_output_latency_ms": 1000,
                "first_output_latency_ms": 2000,
                "total_latency_ms": 3000,
            },
        }
    ]
    assert result["audits"][0] == {
        "id": 17,
        "type": "ai",
        "content": "模型输出",
        "created_at": "2026-08-30T01:00:00Z",
        "run_id": "run-1",
        "turn_id": "turn-1",
        "message_type": "model_audit",
        "operation_id": "model-1",
        "started_at": "2026-08-30T01:00:01Z",
        "finished_at": "2026-08-30T01:00:02Z",
        "duration_ms": 875,
        "sequence": 12,
        "finished_sequence": 18,
        "execution_status": "completed",
        "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
        "namespace": ["agent", "model"],
        "model_run_id": "langgraph-model-1",
        "content_blocks": [{"type": "text", "text": "模型输出"}],
        "reasoning_content": "",
        "error_type": None,
        "error_message": None,
        "tool_calls": [],
    }
    tool = result["audits"][1]
    assert tool == {
        "id": 18,
        "type": "tool",
        "content": "查询结果",
        "created_at": "2026-08-30T01:00:02Z",
        "run_id": "run-1",
        "turn_id": "turn-1",
        "message_type": "tool_audit",
        "operation_id": "call-1",
        "tool_call_id": "call-1",
        "source": None,
        "tool_name": "search",
        "tool_input": {"q": "Yuxi"},
        "tool_output": {"type": "tool", "content": "查询结果", "status": "success"},
        "error_message": None,
        "source_model_operation_id": "model-1",
        "started_at": "2026-08-30T01:00:02Z",
        "finished_at": "2026-08-30T01:00:03Z",
        "duration_ms": 120,
        "sequence": 14,
        "finished_sequence": 15,
        "execution_status": "completed",
        "usage": None,
        "namespace": [],
    }
    assert "private_internal_field" not in str(result)


@pytest.mark.asyncio
async def test_get_thread_message_audits_view_uses_agent_run_terminal_status(monkeypatch):
    audit = SimpleNamespace(
        id=21,
        role="assistant",
        content="",
        created_at=datetime(2026, 8, 30, 1, 0, 0),
        run_id="run-cancelled",
        turn_id="turn-cancelled",
        message_type="model_audit",
        operation_id="model-cancelled",
        started_at=datetime(2026, 8, 30, 1, 0, 0),
        finished_at=datetime(2026, 8, 30, 1, 0, 1),
        duration_ms=1000,
        sequence=1,
        execution_status="interrupted",
        usage=None,
        extra_metadata={},
        tool_calls=[],
    )
    run = SimpleNamespace(
        id="run-cancelled",
        status="cancelled",
        created_at=datetime(2026, 8, 30, 1, 0, 0),
        started_at=datetime(2026, 8, 30, 1, 0, 0),
        prepared_at=None,
        first_output_at=None,
        finished_at=datetime(2026, 8, 30, 1, 0, 1),
    )

    class FakeSessionRepository:
        def __init__(self, _db):
            pass

        async def get_session_by_thread_id(self, _thread_id):
            return SimpleNamespace(id=7, uid="user-1", app_id=None, status="active")

        async def list_message_audits(self, _session_record_id, *, limit):
            assert limit == messages.MESSAGE_AUDIT_LIMIT
            return [audit], False

        async def list_agent_runs_for_trace(self, _session_record_id, *, limit):
            assert limit == messages.AGENT_RUN_TRACE_LIMIT
            return [run], False

    monkeypatch.setattr(messages, "MessageRepository", FakeSessionRepository)
    monkeypatch.setattr(messages, "AgentRunRepository", FakeSessionRepository)

    async def visible_thread(**_kwargs):
        """模拟已通过完整作用域查询的 Thread。"""
        return SimpleNamespace(id=7)

    monkeypatch.setattr(messages, "require_thread", visible_thread)

    result = await messages.get_thread_audits(
        thread_id="thread-1",
        scope=ActorScope(uid="user-1", app_id=None, is_superadmin=True),
        db=object(),
    )

    assert result["audits"][0]["execution_status"] == "interrupted"
    assert result["runs_truncated"] is False
    assert result["runs"][0]["status"] == "cancelled"
    assert result["runs"][0]["timing"]["total_latency_ms"] == 1000
