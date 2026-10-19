"""E2E Turn 清理使用覆盖单次 HTTP 请求的总等待预算。"""

import asyncio

import httpx
import pytest

from test.e2e import e2e_helpers


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
async def test_turn_wait_returns_the_owned_terminal_outcome(status):
    """等待只证明指定 Turn 终结，具体成功或取消仍由业务用例断言。"""
    turn = {"id": "turn", "session_id": "thread", "status": status, "yuxi": {"current_run_id": "run"}}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=turn)), base_url="http://test"
    ) as client:
        assert await e2e_helpers.wait_for_terminal_turn(client, {}, "thread", "turn") == turn


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"id": "other-turn"}, {"session_id": "other-thread"}, {"http": 404}])
async def test_turn_wait_rejects_wrong_or_missing_target(change):
    """其他 Turn 的完成和目标消失都不能冒充本次等待成功。"""
    turn = {"id": "turn", "session_id": "thread", "status": "completed", "yuxi": {"current_run_id": "run"}, **change}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(change.get("http", 200), json=turn)), base_url="http://test"
    ) as client:
        with pytest.raises(AssertionError, match="归属|HTTP=404"):
            await e2e_helpers.wait_for_terminal_turn(client, {}, "thread", "turn")


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked_request", [False, True])
async def test_turn_wait_bounds_requests_and_reports_only_state(blocked_request):
    """总预算覆盖卡住的 HTTP；超时不泄漏结果正文或凭据。"""

    async def respond(request):
        """给出未终结快照，或模拟查询本身不返回。"""
        if blocked_request:
            await asyncio.sleep(1)
        return httpx.Response(
            200,
            json={
                "id": "turn",
                "session_id": "thread",
                "status": "in_progress",
                "yuxi": {"current_run_id": "run", "output": "secret-body"},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="http://test") as client:
        with pytest.raises(pytest.fail.Exception, match="thread=thread, turn=turn") as error:
            await e2e_helpers.wait_for_terminal_turn(client, {}, "thread", "turn", timeout=0.02)
    assert "secret-body" not in str(error.value)
    if not blocked_request:
        assert "in_progress" in str(error.value) and "run" in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["valid", "wrong-input", "wrong-thread", "cancelled", "missing-projection"])
async def test_input_wait_requires_owned_consumption_projection(mutation):
    """接收回执不能替代真实消费投影，取消和其他提交立即拒绝。"""
    receipt = {"session_id": "thread", "input_id": "input", "turn_id": None, "run_id": None}
    snapshot = {
        "thread_id": "thread",
        "input_id": "input",
        "status": "consumed",
        "turn_id": "turn",
        "run_id": "run",
        "items": [{"type": "message"}],
    }
    if mutation == "wrong-input":
        snapshot["input_id"] = "other"
    elif mutation == "wrong-thread":
        snapshot["thread_id"] = "other"
    elif mutation == "cancelled":
        snapshot["status"] = "cancelled"
    elif mutation == "missing-projection":
        snapshot["items"] = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=snapshot)), base_url="http://test"
    ) as client:
        if mutation == "valid":
            assert (await e2e_helpers.wait_for_consumed_input(client, {}, receipt))["run_id"] == "run"
        else:
            with pytest.raises(AssertionError, match="归属|取消|投影"):
                await e2e_helpers.wait_for_consumed_input(client, {}, receipt)


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked_request", [False, True])
async def test_input_wait_bounds_queries_and_reports_only_owned_state(blocked_request):
    """消费投影未发布或 HTTP 卡住时，按总预算失败并隐藏正文。"""

    async def respond(request):
        """保持 pending 或阻塞查询本身。"""
        if blocked_request:
            await asyncio.sleep(1)
        return httpx.Response(
            200,
            json={
                "thread_id": "thread",
                "input_id": "input",
                "status": "pending",
                "turn_id": None,
                "run_id": None,
                "items": [{"text": "secret-body"}],
            },
        )

    receipt = {"session_id": "thread", "input_id": "input", "turn_id": None, "run_id": None}
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="http://test") as client:
        with pytest.raises(pytest.fail.Exception, match="thread=thread, input=input") as error:
            await e2e_helpers.wait_for_consumed_input(client, {}, receipt, timeout=0.02)
    assert "secret-body" not in str(error.value)
    if not blocked_request:
        assert "pending" in str(error.value)


@pytest.mark.asyncio
async def test_replay_wait_does_not_complete_before_the_signal():
    """服务明确未开始时保持等待，收到本例信号后才能返回。"""
    observed, release = asyncio.Event(), asyncio.Event()

    async def respond(request):
        """按独立同步信号返回协议状态。"""
        observed.set()
        return httpx.Response(200, json={"started": release.is_set()})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="http://test") as client:
        waiting = asyncio.create_task(e2e_helpers.wait_for_blocked_response(client, "gate"))
        try:
            await observed.wait()
            assert not waiting.done()
            release.set()
            await waiting
        finally:
            waiting.cancel()
            await asyncio.gather(waiting, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 404])
async def test_replay_wait_reports_absence_and_timeout(status):
    """缺失的阻塞点与始终未开始分别提供确定的失败原因。"""
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json={"started": False})), base_url="http://test"
    ) as client:
        if status == 404:
            with pytest.raises(AssertionError, match="token=gate, HTTP=404"):
                await e2e_helpers.wait_for_blocked_response(client, "gate", timeout=0.02)
        else:
            with pytest.raises(pytest.fail.Exception, match="token=gate, started=False"):
                await e2e_helpers.wait_for_blocked_response(client, "gate", timeout=0.02)


@pytest.mark.asyncio
async def test_archive_thread_cancels_blocked_status_request_at_deadline(monkeypatch):
    """状态接口卡住时，单次 HTTP 请求不能越过 Turn 清理期限。"""
    monkeypatch.setattr(e2e_helpers, "RUN_TIMEOUT_SECONDS", 0.02)

    class BlockedClient:
        async def get(self, *_args, **_kwargs):
            await asyncio.sleep(1)

    with pytest.raises(pytest.fail.Exception, match="测试 Turn 取消后未收敛"):
        await e2e_helpers.archive_public_thread(BlockedClient(), {}, "blocked-thread", turn_id="blocked-turn")
