from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

import yuxi.agents.middlewares.summary_middleware as summary_middleware
from yuxi.agents.middlewares.summary_middleware import SummaryOffloadMiddleware
from yuxi.utils.paths import VIRTUAL_PATH_OUTPUTS


class _DummyModel:
    _llm_type = "test-chat"
    profile = {"max_input_tokens": 128000}

    def invoke(self, _prompt: str) -> SimpleNamespace:
        return SimpleNamespace(text="summary")


@pytest.mark.unit
def test_offload_tool_result_writes_readable_outputs_path(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def _fake_write(_runtime, file_path: str, content: str) -> tuple[bool, dict]:
        captured["file_path"] = file_path
        captured["content"] = content
        return True, {}

    monkeypatch.setattr(summary_middleware, "_write_offloaded_content", _fake_write)

    message = ToolMessage(content="line1\nline2", tool_call_id="tool-1", name="search", id="msg-1")
    result = summary_middleware._offload_tool_result(
        message,
        threshold=1,
        token_counter=lambda _messages: 10,
        runtime=SimpleNamespace(),
    )

    assert result == {}
    assert captured["file_path"] == f"{VIRTUAL_PATH_OUTPUTS}/summary_offload/search-msg-1.txt"
    assert captured["content"].startswith("=== Tool Invocation ===\nTool: search\nTool Call ID: tool-1\n")
    assert "文件路径: " in str(message.content)
    assert captured["file_path"] in str(message.content)


@pytest.mark.unit
def test_offload_tool_result_skips_non_text_content(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def _fake_write(_runtime, _file_path: str, _content: str) -> tuple[bool, dict]:
        nonlocal called
        called = True
        return True, {}

    monkeypatch.setattr(summary_middleware, "_write_offloaded_content", _fake_write)

    message = ToolMessage(
        content=[{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "abc"}}],
        tool_call_id="tool-1",
        name="read_file",
        id="msg-2",
    )

    result = summary_middleware._offload_tool_result(
        message,
        threshold=1,
        token_counter=lambda _messages: 10,
        runtime=SimpleNamespace(),
    )

    assert result is None
    assert called is False
    assert message.content[0]["type"] == "image"


@pytest.mark.unit
def test_before_model_excludes_system_message_from_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    middleware = SummaryOffloadMiddleware(
        model=_DummyModel(),
        trigger=("tokens", 10),
        keep=("messages", 1),
        token_counter=lambda _messages: 100,
        summary_offload_threshold=10_000,
        max_retention_ratio=0.5,
    )
    captured_ids: list[str] = []

    monkeypatch.setattr(summary_middleware, "_offload_tool_results", lambda *args, **kwargs: ({}, []))
    monkeypatch.setattr(middleware, "_find_cutoff_by_token_limit", lambda _messages, _limit: 2)
    monkeypatch.setattr(
        middleware,
        "_create_summary",
        lambda messages: captured_ids.extend([str(message.id) for message in messages]) or "summary",
    )

    messages = [
        SystemMessage(content="sys", id="sys-1"),
        HumanMessage(content="human-1", id="human-1"),
        AIMessage(content="ai-1", id="ai-1"),
        HumanMessage(content="human-2", id="human-2"),
    ]

    result = middleware.before_model({"messages": messages}, SimpleNamespace())

    assert captured_ids == ["human-1", "ai-1"]
    assert result is not None
    new_messages = result["messages"]
    assert new_messages[1].id == "sys-1"
    assert new_messages[2].content == "Here is a summary of the conversation to date:\n\nsummary"
    assert new_messages[3].id == "human-2"


@pytest.mark.unit
def test_before_model_uses_keep_cutoff_for_message_trigger(monkeypatch: pytest.MonkeyPatch) -> None:
    middleware = SummaryOffloadMiddleware(
        model=_DummyModel(),
        trigger=("messages", 3),
        keep=("messages", 1),
        token_counter=lambda _messages: 1,
        summary_offload_threshold=10_000,
    )

    monkeypatch.setattr(summary_middleware, "_offload_tool_results", lambda *args, **kwargs: ({}, []))
    monkeypatch.setattr(middleware, "_create_summary", lambda _messages: "summary")

    messages = [
        HumanMessage(content="human-1", id="human-1"),
        AIMessage(content="ai-1", id="ai-1"),
        HumanMessage(content="human-2", id="human-2"),
    ]

    result = middleware.before_model({"messages": messages}, SimpleNamespace())

    assert result is not None
    new_messages = result["messages"]
    assert new_messages[1].content == "Here is a summary of the conversation to date:\n\nsummary"
    assert new_messages[2].id == "human-2"
