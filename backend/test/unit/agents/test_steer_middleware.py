"""Steer/Guided Middleware 单元测试。"""

from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import AIMessage
from yuxi.services import agent_request_queue_service

import pytest

import yuxi.agents.middlewares.steer as steer_module
from yuxi.agents.middlewares.steer import SteerMiddleware

pytestmark = [pytest.mark.unit]


def _runtime(run_id="run-1"):
    return SimpleNamespace(context=SimpleNamespace(run_id=run_id))


@pytest.mark.asyncio
async def test_before_model_injects_pending_guided_messages(monkeypatch):
    from langchain.messages import HumanMessage

    middleware = SteerMiddleware()
    messages = [HumanMessage(content="补充：只看 2024 年后的数据", id="m-1")]

    async def fake_take(run_id):
        assert run_id == "run-1"
        return messages

    async def fake_steer(run_id):
        return False

    monkeypatch.setattr(steer_module, "take_pending_guided_messages", fake_take, raising=False)
    monkeypatch.setattr(
        "yuxi.services.agent_request_queue_service.take_pending_guided_messages", fake_take
    )
    monkeypatch.setattr(
        "yuxi.services.agent_request_queue_service.should_end_run_for_steer", fake_steer
    )

    result = await middleware.abefore_model({}, _runtime())

    assert result == {"messages": messages}


@pytest.mark.asyncio
async def test_before_model_returns_none_without_interventions(monkeypatch):
    middleware = SteerMiddleware()

    async def fake_take(run_id):
        return []

    async def fake_steer(run_id):
        return False

    monkeypatch.setattr(
        "yuxi.services.agent_request_queue_service.take_pending_guided_messages", fake_take
    )
    monkeypatch.setattr(
        "yuxi.services.agent_request_queue_service.should_end_run_for_steer", fake_steer
    )

    assert await middleware.abefore_model({}, _runtime()) is None


@pytest.mark.asyncio
async def test_before_model_prefers_steer_jump_when_both_pending(monkeypatch):
    from langchain.messages import HumanMessage

    middleware = SteerMiddleware()

    async def fake_take(run_id):
        return [HumanMessage(content="guided")]

    async def fake_steer(run_id):
        return True

    monkeypatch.setattr(
        "yuxi.services.agent_request_queue_service.take_pending_guided_messages", fake_take
    )
    monkeypatch.setattr(
        "yuxi.services.agent_request_queue_service.should_end_run_for_steer", fake_steer
    )

    result = await middleware.abefore_model({}, _runtime())

    assert result == {"jump_to": "end"}


@pytest.mark.asyncio
async def test_before_model_guided_failure_does_not_break_run(monkeypatch):
    middleware = SteerMiddleware()

    async def fake_take(run_id):
        raise RuntimeError("db down")

    async def fake_steer(run_id):
        return False

    monkeypatch.setattr(
        "yuxi.services.agent_request_queue_service.take_pending_guided_messages", fake_take
    )
    monkeypatch.setattr(
        "yuxi.services.agent_request_queue_service.should_end_run_for_steer", fake_steer
    )

    assert await middleware.abefore_model({}, _runtime()) is None


@pytest.mark.asyncio
async def test_before_model_without_run_id_skips_queries(monkeypatch):
    middleware = SteerMiddleware()

    async def fail_take(run_id):
        raise AssertionError("无 run_id 不应查询 guided")

    async def fail_steer(run_id):
        raise AssertionError("无 run_id 不应查询 steer")

    monkeypatch.setattr(
        "yuxi.services.agent_request_queue_service.take_pending_guided_messages", fail_take
    )
    monkeypatch.setattr(
        "yuxi.services.agent_request_queue_service.should_end_run_for_steer", fail_steer
    )

    assert await middleware.abefore_model({}, SimpleNamespace(context=SimpleNamespace())) is None


@pytest.mark.asyncio
async def test_before_model_ends_run_when_steer_is_waiting(monkeypatch: pytest.MonkeyPatch):
    """存在待处理 Steer 时，在下一次模型调用前结束当前 Graph。"""

    async def should_end(run_id: str) -> bool:
        return run_id == "run-1"

    monkeypatch.setattr(agent_request_queue_service, "should_end_run_for_steer", should_end)
    runtime = SimpleNamespace(context=SimpleNamespace(run_id="run-1"))

    result = await SteerMiddleware().abefore_model({}, runtime)

    assert result == {"jump_to": "end"}

@pytest.mark.asyncio
async def test_before_model_continues_without_steer(monkeypatch: pytest.MonkeyPatch):
    """没有 Steer 时继续正常模型调用。"""

    async def should_end(run_id: str) -> bool:
        return False

    monkeypatch.setattr(agent_request_queue_service, "should_end_run_for_steer", should_end)
    runtime = SimpleNamespace(context=SimpleNamespace(run_id="run-1"))

    assert await SteerMiddleware().abefore_model({}, runtime) is None

@pytest.mark.asyncio
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

@pytest.mark.asyncio
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

@pytest.mark.asyncio
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
