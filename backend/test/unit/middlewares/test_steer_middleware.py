"""Steer Middleware 单元测试。"""

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage
from yuxi.agents.middlewares.steer import SteerMiddleware
from yuxi.services import agent_request_queue_service

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_before_model_ends_run_when_steer_is_waiting(monkeypatch: pytest.MonkeyPatch):
    """存在待处理 Steer 时，在下一次模型调用前结束当前 Graph。"""

    async def should_end(run_id: str) -> bool:
        return run_id == "run-1"

    monkeypatch.setattr(agent_request_queue_service, "should_end_run_for_steer", should_end)
    runtime = SimpleNamespace(context=SimpleNamespace(run_id="run-1"))

    result = await SteerMiddleware().abefore_model({}, runtime)

    assert result == {"jump_to": "end"}


async def test_before_model_continues_without_steer(monkeypatch: pytest.MonkeyPatch):
    """没有 Steer 时继续正常模型调用。"""

    async def should_end(run_id: str) -> bool:
        return False

    monkeypatch.setattr(agent_request_queue_service, "should_end_run_for_steer", should_end)
    runtime = SimpleNamespace(context=SimpleNamespace(run_id="run-1"))

    assert await SteerMiddleware().abefore_model({}, runtime) is None


async def test_before_model_ignores_context_without_run_id(monkeypatch: pytest.MonkeyPatch):
    """缺少 Run 上下文时不查询队列。"""
    called = False

    async def should_end(run_id: str) -> bool:
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(agent_request_queue_service, "should_end_run_for_steer", should_end)
    runtime = SimpleNamespace(context=SimpleNamespace())

    assert await SteerMiddleware().abefore_model({}, runtime) is None
    assert called is False


async def test_after_model_ends_tool_free_turn_when_steer_arrives(monkeypatch: pytest.MonkeyPatch):
    """模型轮次结束后才到达的 Steer 仍会让旧 Run 让位。"""

    async def should_end(run_id: str) -> bool:
        return run_id == "run-1"

    monkeypatch.setattr(agent_request_queue_service, "should_end_run_for_steer", should_end)
    runtime = SimpleNamespace(context=SimpleNamespace(run_id="run-1"))

    result = await SteerMiddleware().aafter_model(
        {"messages": [AIMessage(content="已完成当前回答")]},
        runtime,
    )

    assert result == {"jump_to": "end"}


async def test_after_model_does_not_skip_tool_batch(monkeypatch: pytest.MonkeyPatch):
    """模型生成工具调用时，Steer 不能跳过尚未执行的工具批次。"""
    called = False

    async def should_end(run_id: str) -> bool:
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(agent_request_queue_service, "should_end_run_for_steer", should_end)
    runtime = SimpleNamespace(context=SimpleNamespace(run_id="run-1"))

    result = await SteerMiddleware().aafter_model(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{"id": "call-1", "name": "tool", "args": {}}],
                )
            ]
        },
        runtime,
    )

    assert result is None
    assert called is False
