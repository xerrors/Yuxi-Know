from pathlib import PurePosixPath
from typing import Literal

from langchain.agents.middleware import HumanInTheLoopMiddleware
from yuxi.modules.agents.runtime.sandbox.paths import normalize_runtime_path

ToolApprovalMode = Literal["default", "always_trust"]

DEFAULT_TOOL_APPROVAL_MODE: ToolApprovalMode = "default"
TOOL_APPROVAL_MODES = frozenset({"default", "always_trust"})
_ALLOWED_DECISIONS = ["approve", "reject"]


def normalize_tool_approval_mode(value: object) -> ToolApprovalMode:
    mode = value.strip() if isinstance(value, str) else value
    if mode not in TOOL_APPROVAL_MODES:
        raise ValueError(f"不支持的 tool_approval_mode: {value}")
    return mode


def create_tool_approval_middleware(
    mode: ToolApprovalMode,
    *,
    current_project_path: str | None = None,
):
    """按审批模式与当前 Project 构造敏感工具审批。"""
    if mode == "always_trust":
        return None

    write_requires_approval = _project_write_requires_approval(current_project_path or "")
    return HumanInTheLoopMiddleware(
        interrupt_on={
            "write_file": {"allowed_decisions": _ALLOWED_DECISIONS, "when": write_requires_approval},
            "edit_file": {"allowed_decisions": _ALLOWED_DECISIONS, "when": write_requires_approval},
            "execute": {"allowed_decisions": _ALLOWED_DECISIONS},
        }
    )


def _project_write_requires_approval(current_project_path: str):
    """创建仅豁免当前 Project 写入的审批谓词。"""
    project_root = _normalize_runtime_path(current_project_path)

    def requires_approval(request) -> bool:
        """非法路径或 Project 外路径继续请求人工确认。"""
        args = request.tool_call.get("args")
        file_path = _normalize_runtime_path(args.get("file_path") if isinstance(args, dict) else None)
        if project_root is None or file_path is None:
            return True
        return file_path != project_root and project_root not in file_path.parents

    return requires_approval


def _normalize_runtime_path(value: object) -> PurePosixPath | None:
    """将审批参数收敛为无跳转的 Sandbox 绝对路径。"""
    if not isinstance(value, str):
        return None
    try:
        return PurePosixPath(normalize_runtime_path(value))
    except ValueError:
        return None
