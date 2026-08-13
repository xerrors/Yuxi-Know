"""Steer 实施 Gate：验证 LangGraph 的工具后 ``before_model`` 安全点。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, hook_config
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from yuxi.agents.middlewares.steer import SteerMiddleware
from yuxi.services import agent_request_queue_service

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


class _ParallelToolModel(BaseChatModel):
    """首次模型调用生成两个并行工具；安全接替后不应再次调用模型。"""

    call_count: int = 0

    @property
    def _llm_type(self) -> str:
        return "steer-safety-gate"

    def bind_tools(self, tools, **kwargs):  # noqa: ARG002
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ARG002
        self.call_count += 1
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {"id": "call-one", "name": "gate_tool_one", "args": {}},
                            {"id": "call-two", "name": "gate_tool_two", "args": {}},
                        ],
                    )
                )
            ]
        )


class _FinalAnswerModel(BaseChatModel):
    """只返回最终文本，模拟 Steer 到达最后一次模型检查后的窗口。"""

    call_count: int = 0

    @property
    def _llm_type(self) -> str:
        return "steer-final-answer"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ARG002
        self.call_count += 1
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="旧 Run 已完成当前回答"))])


@dataclass
class _RunContext:
    run_id: str


class _SafetyPointMiddleware(AgentMiddleware):
    """测试专用安全点：Steer 到达后在下一次模型调用前结束 Graph。"""

    def __init__(self) -> None:
        self.steer_requested = False
        self.messages_at_safe_point: list = []

    @hook_config(can_jump_to=["end"])
    async def abefore_model(self, state, runtime):  # noqa: ARG002
        if not self.steer_requested:
            return None
        self.messages_at_safe_point = list(state["messages"])
        return {"jump_to": "end"}


async def test_parallel_tools_finish_before_steer_ends_graph_and_checkpoint_is_complete():
    """Steer 只能在整批工具结果进入 checkpoint 后阻止下一次模型调用。"""
    both_started = asyncio.Event()
    release_tools = asyncio.Event()
    started = 0
    started_lock = asyncio.Lock()

    async def wait_for_release(result: str) -> str:
        nonlocal started
        async with started_lock:
            started += 1
            if started == 2:
                both_started.set()
        await release_tools.wait()
        return result

    @tool
    async def gate_tool_one() -> str:
        """返回第一个 Gate 工具结果。"""
        return await wait_for_release("result-one")

    @tool
    async def gate_tool_two() -> str:
        """返回第二个 Gate 工具结果。"""
        return await wait_for_release("result-two")

    model = _ParallelToolModel()
    middleware = _SafetyPointMiddleware()
    checkpointer = InMemorySaver()
    agent = create_agent(
        model=model,
        tools=[gate_tool_one, gate_tool_two],
        middleware=[middleware],
        checkpointer=checkpointer,
    )
    config = {"configurable": {"thread_id": "steer-gate-thread"}}

    async def consume_graph() -> None:
        async for _ in agent.astream(
            {"messages": [HumanMessage("执行两个工具")]},
            config=config,
            stream_mode="updates",
        ):
            pass

    graph_task = asyncio.create_task(consume_graph())
    await asyncio.wait_for(both_started.wait(), timeout=5)
    middleware.steer_requested = True
    release_tools.set()
    await asyncio.wait_for(graph_task, timeout=5)

    safe_point_results = {
        message.tool_call_id: message.content
        for message in middleware.messages_at_safe_point
        if isinstance(message, ToolMessage)
    }
    persisted_state = await agent.aget_state(config)
    checkpoint_results = {
        message.tool_call_id: message.content
        for message in persisted_state.values["messages"]
        if isinstance(message, ToolMessage)
    }

    assert model.call_count == 1
    assert safe_point_results == {"call-one": "result-one", "call-two": "result-two"}
    assert checkpoint_results == safe_point_results


async def test_tool_free_model_turn_keeps_steer_intent_for_handoff(monkeypatch: pytest.MonkeyPatch):
    """Steer 在最后一次 before_model 检查后到达时，仍能安全结束旧 Graph。"""
    checks = 0

    async def should_end(run_id: str) -> bool:
        nonlocal checks
        assert run_id == "run-final-answer"
        checks += 1
        return checks >= 2

    monkeypatch.setattr(agent_request_queue_service, "should_end_run_for_steer", should_end)
    model = _FinalAnswerModel()
    checkpointer = InMemorySaver()
    agent = create_agent(
        model=model,
        middleware=[SteerMiddleware()],
        context_schema=_RunContext,
        checkpointer=checkpointer,
    )
    config = {"configurable": {"thread_id": "steer-final-answer-thread"}}

    async for _ in agent.astream(
        {"messages": [HumanMessage("完成当前回答")]},
        config=config,
        context=_RunContext(run_id="run-final-answer"),
        stream_mode="updates",
    ):
        pass

    state = await agent.aget_state(config)
    assert model.call_count == 1
    assert checks == 2
    assert state.values["messages"][-1].content == "旧 Run 已完成当前回答"
