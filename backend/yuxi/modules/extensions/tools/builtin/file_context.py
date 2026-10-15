"""读取文件工具需要的用户与工作目录。"""

from langgraph.prebuilt.tool_node import ToolRuntime


def resolve_file_context(runtime: ToolRuntime) -> tuple[str, str]:
    """只读取执行者注入的用户身份与 Project 工作目录。"""
    uid = runtime_context_value(runtime, "uid")
    workdir_path = runtime_context_value(runtime, "workdir_relative_path")
    if not uid:
        raise ValueError("当前运行时缺少 uid")
    if not workdir_path:
        raise ValueError("当前运行时缺少 workdir_relative_path")
    return uid, workdir_path


def runtime_context_value(runtime: ToolRuntime, key: str) -> str | None:
    """只读取执行者注入的 Context，配置和模型 state 不拥有身份。"""
    context = getattr(runtime, "context", None)
    value = context.get(key) if isinstance(context, dict) else getattr(context, key, None)
    return value.strip() if isinstance(value, str) and value.strip() else None
