"""E2E Turn 清理使用覆盖单次 HTTP 请求的总等待预算。"""

import asyncio

import pytest

from test.e2e import e2e_helpers


@pytest.mark.asyncio
async def test_archive_thread_cancels_blocked_status_request_at_deadline(monkeypatch):
    """状态接口卡住时，单次 HTTP 请求不能越过 Turn 清理期限。"""
    monkeypatch.setattr(e2e_helpers, "RUN_TIMEOUT_SECONDS", 0.02)

    class BlockedClient:
        async def get(self, *_args, **_kwargs):
            await asyncio.sleep(1)

    with pytest.raises(pytest.fail.Exception, match="测试 Turn 取消后未收敛"):
        await e2e_helpers.archive_public_thread(BlockedClient(), {}, "blocked-thread", turn_id="blocked-turn")
