"""沙盒后端选择、进程装配与就绪检查。"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yuxi.modules.agents.runtime.sandbox.container import ContainerSandboxProvider
    from yuxi.modules.agents.runtime.sandbox.cube_provider import CubeSandboxProvider

    SandboxProvider = CubeSandboxProvider | ContainerSandboxProvider

_sandbox_provider: SandboxProvider | None = None


def get_sandbox_provider() -> SandboxProvider:
    """按部署配置取得本进程无长期连接的执行客户端。"""
    global _sandbox_provider
    if _sandbox_provider is None:
        backend = validate_sandbox_configuration()
        if backend == "cube":
            from yuxi.modules.agents.runtime.sandbox.cube_provider import CubeSandboxProvider

            _sandbox_provider = CubeSandboxProvider()
        else:
            from yuxi.modules.agents.runtime.sandbox.container import ContainerSandboxProvider

            _sandbox_provider = ContainerSandboxProvider()
    return _sandbox_provider


async def check_sandbox_provider() -> None:
    """核对所选执行节点真实就绪；镜像和资源限制由节点自身校验。"""
    await asyncio.to_thread(get_sandbox_provider().health)


def validate_sandbox_configuration() -> str:
    """只校验业务进程连接当前执行后端所需的部署配置。"""
    backend = os.environ.get("SANDBOX_BACKEND", "cube").strip().lower()
    if backend == "cube":
        from yuxi.modules.agents.runtime.sandbox.cube_provider import validate_cube_configuration

        validate_cube_configuration()
    elif backend == "container":
        if len(os.environ.get("SANDBOX_RUNNER_TOKEN", "").strip()) < 16:
            raise RuntimeError("SANDBOX_BACKEND=container 需要至少 16 个字符的 SANDBOX_RUNNER_TOKEN")
    else:
        raise RuntimeError("SANDBOX_BACKEND 必须是 cube 或 container")
    return backend
