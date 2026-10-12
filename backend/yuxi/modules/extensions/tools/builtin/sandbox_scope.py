"""读取文件工具共用的运行作用域。"""

from langgraph.prebuilt.tool_node import ToolRuntime


def resolve_runtime_sandbox_scope(runtime: ToolRuntime) -> tuple[str, str, str]:
    """读取 execution runtime、用户与 Workdir 路径。"""
    runtime_thread_id = runtime_scope_value(runtime, "runtime_scope_id") or runtime_scope_value(runtime, "thread_id")
    uid = runtime_scope_value(runtime, "uid")
    workdir_path = runtime_scope_value(runtime, "workdir_relative_path")
    if not runtime_thread_id:
        raise ValueError("当前运行时缺少 thread_id")
    if not uid:
        raise ValueError("当前运行时缺少 uid")
    if not workdir_path:
        raise ValueError("当前运行时缺少 workdir_relative_path")
    return runtime_thread_id, uid, workdir_path


def runtime_scope_value(runtime: ToolRuntime, key: str) -> str | None:
    """只读取执行者注入的 Context，配置和模型 state 不拥有身份。"""
    context = getattr(runtime, "context", None)
    value = context.get(key) if isinstance(context, dict) else getattr(context, key, None)
    return value.strip() if isinstance(value, str) and value.strip() else None
