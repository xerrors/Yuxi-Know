"""共享 ARQ 连接的并发装配和失败清理。"""

import asyncio
from unittest.mock import AsyncMock

import pytest
from yuxi.infrastructure.redis import queue


@pytest.mark.asyncio
async def test_concurrent_consumers_share_one_pool_and_close(monkeypatch):
    """恢复无锁创建会产生多个实际客户端，身份断言拒绝该回归。"""
    started = asyncio.Event()
    release = asyncio.Event()
    created = []

    async def create():
        pool = AsyncMock()
        created.append(pool)
        started.set()
        await release.wait()
        return pool

    monkeypatch.setattr(queue, "_arq_pool", None)
    monkeypatch.setattr(queue, "_arq_lock", asyncio.Lock())
    monkeypatch.setattr(queue, "create_arq_redis_pool", create)
    monkeypatch.setattr(queue, "close_async_redis_client", AsyncMock())
    tasks = [asyncio.create_task(queue.get_arq_pool()) for _ in range(12)]
    await started.wait()
    await asyncio.sleep(0)
    release.set()
    pools = await asyncio.gather(*tasks)
    assert len(created) == 1
    assert all(pool is created[0] for pool in pools)
    await queue.close_queue_clients()
    assert queue._arq_pool is None
    created[0].aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_creation_can_retry_and_failed_close_cleans_redis(monkeypatch):
    """失败不会缓存无效客户端，关闭失败仍清理另一连接并保留异常。"""
    pool = AsyncMock()
    failure = ConnectionError("fixture")
    monkeypatch.setattr(queue, "_arq_pool", None)
    monkeypatch.setattr(queue, "_arq_lock", asyncio.Lock())
    monkeypatch.setattr(queue, "create_arq_redis_pool", AsyncMock(side_effect=[failure, pool]))
    close_redis = AsyncMock()
    monkeypatch.setattr(queue, "close_async_redis_client", close_redis)
    with pytest.raises(ConnectionError) as raised:
        await queue.get_arq_pool()
    assert raised.value is failure
    assert await queue.get_arq_pool() is pool
    pool.aclose.side_effect = failure
    with pytest.raises(ConnectionError):
        await queue.close_queue_clients()
    assert queue._arq_pool is None
    close_redis.assert_awaited_once()
