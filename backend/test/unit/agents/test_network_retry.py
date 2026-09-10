"""NetworkRetryMiddleware 单元测试。"""

from __future__ import annotations

import asyncio

import pytest

from yuxi.agents.middlewares.network_retry import NetworkRetryMiddleware, is_network_error

pytestmark = [pytest.mark.unit]


class FakeError(Exception):
    pass


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Connection error.", True),
        ("OpenAIConnectionError: Connection error", True),
        ("Connection refused to api host", True),
        ("APITimeoutError: Request timed out", True),
        ("httpx.ReadTimeout while reading", True),
        ("503 Service Unavailable", True),
        ("502 Bad Gateway from upstream", True),
        ("RateLimitError: 429 too many requests", False),
        ("AuthenticationError: invalid api key", False),
        ("NotFoundError: model not found", False),
        ("invalid_request_error: bad parameter", False),
        ("This is a logic bug", False),
    ],
)
def test_is_network_error_classifies(message, expected):
    assert is_network_error(FakeError(message)) is expected


def test_is_network_error_inspects_cause_chain():
    inner = FakeError("Connection reset by peer")
    outer = FakeError("model call wrapper failed")
    outer.__cause__ = inner
    assert is_network_error(outer) is True


@pytest.mark.asyncio
async def test_retries_network_error_until_success():
    mw = NetworkRetryMiddleware(budget_seconds=30, initial_delay=0.01, max_delay=0.02)
    calls = {"n": 0}

    async def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            raise FakeError("OpenAIConnectionError: Connection error")
        return "ok"

    result = await mw.awrap_model_call(object(), handler)
    assert result == "ok"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_non_network_error_propagates_immediately():
    mw = NetworkRetryMiddleware(budget_seconds=30, initial_delay=0.01, max_delay=0.02)
    calls = {"n": 0}

    async def handler(request):
        calls["n"] += 1
        raise FakeError("AuthenticationError: bad key")

    with pytest.raises(FakeError):
        await mw.awrap_model_call(object(), handler)
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_budget_exhaustion_raises():
    mw = NetworkRetryMiddleware(budget_seconds=0.05, initial_delay=0.03, max_delay=0.03)
    calls = {"n": 0}

    async def handler(request):
        calls["n"] += 1
        raise FakeError("Connection refused")

    with pytest.raises(FakeError):
        await mw.awrap_model_call(object(), handler)
    # 预算内至少重试过一次
    assert calls["n"] >= 2


@pytest.mark.asyncio
async def test_cancellation_not_swallowed():
    mw = NetworkRetryMiddleware(budget_seconds=30, initial_delay=0.01, max_delay=0.01)

    async def handler(request):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await mw.awrap_model_call(object(), handler)
