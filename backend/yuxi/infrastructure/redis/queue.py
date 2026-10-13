"""进程级 ARQ 连接生命周期，业务域各自拥有投递语义。"""

import asyncio

from yuxi.infrastructure.redis import close_async_redis_client, create_arq_redis_pool

_arq_pool = None
_arq_lock = asyncio.Lock()


async def get_arq_pool():
    """串行初始化当前进程的 ARQ 连接池。"""
    global _arq_pool
    if _arq_pool is not None:
        return _arq_pool
    async with _arq_lock:
        if _arq_pool is None:
            _arq_pool = await create_arq_redis_pool()
        return _arq_pool


async def close_queue_clients() -> None:
    """请求停止后关闭共用连接，失败交给进程 shutdown 边界记录。"""
    global _arq_pool, _arq_lock
    try:
        if _arq_pool is not None:
            await _arq_pool.aclose()
    finally:
        _arq_pool = None
        _arq_lock = asyncio.Lock()
        await close_async_redis_client()
