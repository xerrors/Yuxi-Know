"""通过实际构图检查智能体保留的工具与状态能力。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from yuxi.modules.agents.runtime.agent_backends.chatbot import graph as chatbot_graph
from yuxi.modules.agents.runtime.checkpoint_cleanup import CheckpointCleanupModel
from yuxi.modules.agents.runtime.middlewares import summary as summary_module


@pytest.mark.asyncio
@pytest.mark.parametrize("checkpoint_only", [False, True])
async def test_shipping_graph_has_no_todo_tool_or_state(monkeypatch, checkpoint_only):
    """新会话和维护图均不能重新暴露已移除的待办能力。"""
    context = SimpleNamespace(
        uid="tool-surface-user",
        thread_id="tool-surface-thread",
        model="test-provider:test-model",
        workdir_relative_path="projects/tool-surface",
        workdir_path="/home/user/workspace/projects/tool-surface",
        tool_approval_mode="default",
        _runtime_prepared=True,
    )
    monkeypatch.setattr(chatbot_graph, "get_langgraph_checkpointer", lambda _: InMemorySaver())
    monkeypatch.setattr(chatbot_graph, "sync_agent_context_skills", AsyncMock())
    monkeypatch.setattr(chatbot_graph, "resolve_configured_runtime_tools", AsyncMock(return_value=[]))
    monkeypatch.setattr(chatbot_graph, "create_agent_composite_backend", lambda _: None)
    monkeypatch.setattr(chatbot_graph, "build_prompt_with_context", lambda _: "")
    monkeypatch.setattr(chatbot_graph, "load_chat_model", lambda **_: CheckpointCleanupModel())
    monkeypatch.setattr(summary_module, "load_chat_model", lambda **_: CheckpointCleanupModel())
    monkeypatch.setattr(chatbot_graph, "create_memory_middleware", AsyncMock(return_value=None))
    monkeypatch.setattr(chatbot_graph, "create_cooperation_middleware", lambda _: None)

    graph = await chatbot_graph.ChatbotAgent().get_graph(context=context, checkpoint_only=checkpoint_only)

    tools = graph.nodes["tools"].bound.tools_by_name
    assert "read_file" in tools
    assert "write_todos" not in tools
    assert "todos" not in graph.channels
