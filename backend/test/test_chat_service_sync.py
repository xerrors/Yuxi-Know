from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain.messages import AIMessage, HumanMessage

from yuxi.services import chat_service as svc


class _FakeConvRepo:
    def __init__(self, _db):
        self.saved_messages: list[dict] = []

    async def add_message_by_thread_id(
        self,
        *,
        thread_id: str,
        role: str,
        content: str,
        message_type: str = "text",
        extra_metadata: dict | None = None,
        image_content: str | None = None,
    ):
        self.saved_messages.append(
            {
                "thread_id": thread_id,
                "role": role,
                "content": content,
                "message_type": message_type,
                "extra_metadata": extra_metadata,
                "image_content": image_content,
            }
        )
        return SimpleNamespace(id=1)


@pytest.mark.asyncio
async def test_agent_chat_uses_invoke_messages_and_persists_langgraph_state(monkeypatch: pytest.MonkeyPatch):
    calls: dict[str, object] = {}

    class FakeGraph:
        async def aget_state(self, config):
            calls["state_config"] = config
            return SimpleNamespace(values={"messages": [AIMessage(content="Hi from graph")], "todos": ["todo-1"]})

    class FakeAgent:
        async def invoke_messages(self, messages, input_context=None, **kwargs):
            calls["invoke_messages"] = messages
            calls["invoke_input_context"] = input_context
            return {"messages": [messages[0], AIMessage(content="Hi from invoke")]}

        async def stream_messages(self, messages, input_context=None, **kwargs):
            raise AssertionError("stream_messages should not be used by sync chat")

        async def get_graph(self):
            return FakeGraph()

    async def fake_get_agent_config_by_id(db, user, agent_config_id):
        assert user.id == "user-1"
        assert agent_config_id == 123
        return SimpleNamespace(agent_id="test-agent", config_json={"context": {"temperature": 0.1}})

    async def fake_save_messages_from_langgraph_state(*, agent_instance, thread_id, conv_repo, config_dict):
        calls["saved_state"] = {
            "agent_instance": agent_instance,
            "thread_id": thread_id,
            "conv_repo": conv_repo,
            "config_dict": config_dict,
        }

    async def fake_guard_check(_content):
        return False

    monkeypatch.setattr(svc.agent_manager, "get_agent", lambda agent_id: FakeAgent())
    monkeypatch.setattr(svc, "get_agent_config_by_id", fake_get_agent_config_by_id)
    monkeypatch.setattr(svc, "ConversationRepository", _FakeConvRepo)
    monkeypatch.setattr(svc, "save_messages_from_langgraph_state", fake_save_messages_from_langgraph_state)
    monkeypatch.setattr(svc.content_guard, "check", fake_guard_check)

    result = await svc.agent_chat(
        query="hello",
        agent_config_id=123,
        thread_id="thread-1",
        meta={"request_id": "req-1"},
        image_content=None,
        current_user=SimpleNamespace(id="user-1", department_id="dept-1"),
        db=object(),
    )

    assert result["status"] == "finished"
    assert result["response"] == "Hi from invoke"
    assert result["thread_id"] == "thread-1"
    assert result["request_id"] == "req-1"
    assert result["agent_state"] == {"todos": ["todo-1"], "files": {}}

    invoke_messages = calls["invoke_messages"]
    assert isinstance(invoke_messages, list)
    assert len(invoke_messages) == 1
    assert isinstance(invoke_messages[0], HumanMessage)
    assert invoke_messages[0].content == "hello"
    assert calls["invoke_input_context"] == {"temperature": 0.1, "user_id": "user-1", "thread_id": "thread-1"}
    assert calls["saved_state"]["thread_id"] == "thread-1"
    assert calls["saved_state"]["config_dict"] == {"configurable": {"thread_id": "thread-1", "user_id": "user-1"}}


@pytest.mark.asyncio
async def test_agent_chat_sync_returns_finished_even_when_state_has_interrupt(monkeypatch: pytest.MonkeyPatch):
    class FakeGraph:
        async def aget_state(self, config):
            return SimpleNamespace(
                values={
                    "messages": [AIMessage(content="Need input later")],
                    "__interrupt__": [{"questions": [{"question": "继续吗？"}]}],
                }
            )

    class FakeAgent:
        async def invoke_messages(self, messages, input_context=None, **kwargs):
            return {"messages": [messages[0], AIMessage(content="Need input later")]}

        async def stream_messages(self, messages, input_context=None, **kwargs):
            raise AssertionError("stream_messages should not be used by sync chat")

        async def get_graph(self):
            return FakeGraph()

    async def fake_get_agent_config_by_id(db, user, agent_config_id):
        return SimpleNamespace(agent_id="test-agent", config_json={"context": {}})

    async def fake_save_messages_from_langgraph_state(*, agent_instance, thread_id, conv_repo, config_dict):
        return None

    async def fake_guard_check(_content):
        return False

    monkeypatch.setattr(svc.agent_manager, "get_agent", lambda agent_id: FakeAgent())
    monkeypatch.setattr(svc, "get_agent_config_by_id", fake_get_agent_config_by_id)
    monkeypatch.setattr(svc, "ConversationRepository", _FakeConvRepo)
    monkeypatch.setattr(svc, "save_messages_from_langgraph_state", fake_save_messages_from_langgraph_state)
    monkeypatch.setattr(svc.content_guard, "check", fake_guard_check)

    result = await svc.agent_chat(
        query="hello",
        agent_config_id=456,
        thread_id="thread-2",
        meta={"request_id": "req-2"},
        image_content=None,
        current_user=SimpleNamespace(id="user-1", department_id="dept-1"),
        db=object(),
    )

    assert result["status"] == "finished"
    assert result["response"] == "Need input later"
    assert result["thread_id"] == "thread-2"
