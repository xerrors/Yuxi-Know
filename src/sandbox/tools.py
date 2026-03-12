"""沙盒工具集 - 提供给 LangGraph Agent 使用的沙盒文件/命令操作工具。

参考 deer-flow 的 tools.py 实现，适配 Yuxi-Know 的 @tool 注册机制。
工具通过 RunnableConfig 中的 thread_id 获取对应沙盒实例（懒初始化、幂等获取）。
中间件 SandboxMiddleware 负责在 Agent 执行结束后统一释放资源。
"""

import logging
from typing import Annotated

from langchain_core.runnables import RunnableConfig

from src.agents.common.toolkits.registry import tool
from src.sandbox.base import Sandbox
from src.sandbox.provider import get_sandbox_provider

logger = logging.getLogger(__name__)


def ensure_sandbox_initialized(config: RunnableConfig) -> Sandbox:
    """从 RunnableConfig 中提取 thread_id，获取或创建对应的沙盒实例。

    provider.acquire 是幂等操作：首次调用创建沙盒，后续调用返回同一实例。
    与 SandboxMiddleware 共享同一个 provider 单例，因此 after_agent 可以正确释放。
    """
    configurable = config.get("configurable", {})
    thread_id = configurable.get("thread_id", "default_thread")
    provider = get_sandbox_provider()
    return provider.acquire(sandbox_id=thread_id)


# =============================================================================
# bash - 通用命令执行（含 python / pip install 等）
# =============================================================================

@tool(
    category="buildin",
    tags=["命令", "沙盒"],
    display_name="Bash 命令执行",
    name_or_callable="bash",
)
def bash_tool(
    description: Annotated[str, "简要说明执行此命令的目的"],
    command: Annotated[str, "要执行的 bash 命令，文件和目录请使用绝对路径"],
    config: RunnableConfig,
) -> str:
    """在沙盒的 Linux 环境中执行 bash 命令。

    - 使用 `python` 运行 Python 代码
    - 使用 `pip install` 安装 Python 包
    """
    try:
        sandbox = ensure_sandbox_initialized(config)
        return sandbox.execute_command(command)
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


# =============================================================================
# ls - 列出目录内容
# =============================================================================

@tool(
    category="buildin",
    tags=["文件", "沙盒"],
    display_name="列出目录内容",
    name_or_callable="ls",
)
def ls_tool(
    description: Annotated[str, "简要说明列出此目录的目的"],
    path: Annotated[str, "要列出内容的目录的绝对路径"],
    config: RunnableConfig,
) -> str:
    """列出目录内容（最多 2 层深度的树状结构）。"""
    try:
        sandbox = ensure_sandbox_initialized(config)
        children = sandbox.list_dir(path)
        if not children:
            return "(empty)"
        return "\n".join(children)
    except FileNotFoundError:
        return f"Error: Directory not found: {path}"
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


# =============================================================================
# read_file - 读取文件内容
# =============================================================================

@tool(
    category="buildin",
    tags=["文件", "沙盒"],
    display_name="读取文件内容",
    name_or_callable="read_file",
)
def read_file_tool(
    description: Annotated[str, "简要说明读取此文件的目的"],
    path: Annotated[str, "要读取的文件的绝对路径"],
    start_line: Annotated[int | None, "可选的起始行号（从 1 开始）"] = None,
    end_line: Annotated[int | None, "可选的结束行号（从 1 开始）"] = None,
    config: RunnableConfig = None,  # type: ignore[assignment]
) -> str:
    """读取文本文件内容。可用于查看源代码、配置文件、日志或任何文本文件。"""
    try:
        sandbox = ensure_sandbox_initialized(config)
        content = sandbox.read_file(path)
        if not content:
            return "(empty)"
        if start_line is not None and end_line is not None:
            lines = content.splitlines()
            content = "\n".join(lines[start_line - 1 : end_line])
        return content
    except FileNotFoundError:
        return f"Error: File not found: {path}"
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except IsADirectoryError:
        return f"Error: Path is a directory: {path}"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


# =============================================================================
# write_file - 写入文件
# =============================================================================

@tool(
    category="buildin",
    tags=["文件", "沙盒"],
    display_name="写入文件",
    name_or_callable="write_file",
)
def write_file_tool(
    description: Annotated[str, "简要说明写入此文件的目的"],
    path: Annotated[str, "要写入的文件的绝对路径"],
    content: Annotated[str, "要写入文件的内容"],
    append: Annotated[bool, "是否追加而非覆盖"] = False,
    config: RunnableConfig = None,  # type: ignore[assignment]
) -> str:
    """将文本内容写入文件。如果文件不存在则创建。"""
    try:
        sandbox = ensure_sandbox_initialized(config)
        sandbox.write_file(path, content, append)
        return "OK"
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except IsADirectoryError:
        return f"Error: Path is a directory: {path}"
    except OSError as e:
        return f"Error: Failed to write '{path}': {e}"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"


# =============================================================================
# str_replace - 文件内字符串替换
# =============================================================================

@tool(
    category="buildin",
    tags=["文件", "沙盒"],
    display_name="字符串替换",
    name_or_callable="str_replace",
)
def str_replace_tool(
    description: Annotated[str, "简要说明执行替换的目的"],
    path: Annotated[str, "要执行替换的文件的绝对路径"],
    old_str: Annotated[str, "要被替换的原始子字符串"],
    new_str: Annotated[str, "替换后的新子字符串"],
    replace_all: Annotated[bool, "是否替换所有匹配项；False 则仅替换第一个"] = False,
    config: RunnableConfig = None,  # type: ignore[assignment]
) -> str:
    """在文件中将指定子字符串替换为新字符串。
    如果 replace_all=False（默认），则要求被替换字符串在文件中恰好出现一次。
    """
    try:
        sandbox = ensure_sandbox_initialized(config)
        content = sandbox.read_file(path)
        if not content:
            return "OK"
        if old_str not in content:
            return f"Error: String to replace not found in file: {path}"
        count = 0 if replace_all else 1
        content = content.replace(old_str, new_str, count)
        sandbox.write_file(path, content)
        return "OK"
    except FileNotFoundError:
        return f"Error: File not found: {path}"
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"
