"""Sandbox provider 共用的可信 Run/attempt 执行上下文。"""

from contextvars import ContextVar

# 工具自建 Backend 仍继承当前可信 Run/attempt，模型无法覆盖执行身份。
sandbox_run_owner: ContextVar[tuple[str, str] | None] = ContextVar("sandbox_run_owner", default=None)
sandbox_run_env: ContextVar[dict[str, str] | None] = ContextVar("sandbox_run_env", default=None)

__all__ = ["sandbox_run_env", "sandbox_run_owner"]
