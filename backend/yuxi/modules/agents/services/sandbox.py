"""用户设置的环境状态与重建用例。"""

import asyncio

from yuxi.infrastructure.filesystem import await_io
from yuxi.modules.agents.runtime.sandbox.provider import get_sandbox_provider


async def get_user_sandbox(uid: str) -> dict:
    """读取控制状态，不唤醒环境。"""
    return await asyncio.to_thread(get_sandbox_provider().status, uid)


async def rebuild_user_sandbox(uid: str) -> dict:
    """取消请求时也等待持有生命周期锁的外部操作完成。"""
    return await await_io(asyncio.to_thread(get_sandbox_provider().rebuild, uid))


async def get_user_sandbox_disk_usage(uid: str) -> dict:
    """显式查询磁盘，等待普通用户命令及其清理完成。"""
    return await await_io(asyncio.to_thread(get_sandbox_provider().disk_usage, uid))
