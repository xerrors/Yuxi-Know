from __future__ import annotations

import re
import shlex

from .sandbox_config import (
    LARGE_TOOL_RESULTS_DIR,
    OUTPUTS_DIR,
    UPLOADS_DIR,
    USER_DATA_PATH,
    WORKSPACE_DIR,
)

ALLOWED_PREFIXES = ("/mnt/user-data", "/mnt/skills")
SYSTEM_EXEC_ALLOWED_PREFIXES = ("/bin/", "/usr/bin/", "/usr/local/bin/")
_USER_DATA_ALIAS_PREFIXES = (
    ("/attachments", f"{USER_DATA_PATH}/{UPLOADS_DIR}/attachments"),
    ("/home", f"{USER_DATA_PATH}/{WORKSPACE_DIR}"),
    ("/workspace", f"{USER_DATA_PATH}/{WORKSPACE_DIR}"),
    ("/outputs", f"{USER_DATA_PATH}/{OUTPUTS_DIR}"),
    ("/uploads", f"{USER_DATA_PATH}/{UPLOADS_DIR}"),
    ("/large_tool_results", f"{USER_DATA_PATH}/{LARGE_TOOL_RESULTS_DIR}"),
)
_STATIC_ALIAS_PREFIXES = (("/skills", "/mnt/skills"),)


def _map_virtual_alias(raw: str, alias: str, target: str) -> str | None:
    if raw == alias:
        return target
    prefix = f"{alias}/"
    if raw.startswith(prefix):
        return f"{target}/{raw[len(prefix) :]}".rstrip("/")
    return None


def normalize_virtual_path(path: str, thread_id: str, *, allow_root: bool = False) -> str | None:
    """将输入路径标准化为 /mnt 命名空间路径。"""
    raw = (path or "").strip()
    if not raw:
        return "Error: path is required"

    if not raw.startswith("/"):
        raw = f"/{raw}"

    if raw in {"/", "/mnt", "/mnt/"}:
        if allow_root:
            return "/"
        return "Error: Access denied: path '/' is not writable"

    if raw.startswith("/mnt/"):
        normalized = raw.rstrip("/") if raw != "/mnt/user-data/" else "/mnt/user-data"
        error = ensure_path_allowed(normalized)
        if error:
            return error
        return normalized

    for alias, target in _STATIC_ALIAS_PREFIXES:
        mapped = _map_virtual_alias(raw, alias, target)
        if mapped is not None:
            return mapped

    for alias, target in _USER_DATA_ALIAS_PREFIXES:
        thread_alias = f"{alias}/{thread_id}"
        mapped = _map_virtual_alias(raw, thread_alias, target)
        if mapped is not None:
            return mapped

        mapped = _map_virtual_alias(raw, alias, target)
        if mapped is not None:
            return mapped

    return f"Error: Access denied: '{raw}' is outside /mnt namespace"


def ensure_path_allowed(path: str) -> str | None:
    normalized = path.rstrip("/") if path != "/" else path
    if normalized in {"/mnt", "/mnt/"}:
        return
    if not any(normalized == prefix or normalized.startswith(f"{prefix}/") for prefix in ALLOWED_PREFIXES):
        return f"Error: Access denied: '{path}' is outside allowed namespaces"
    if ".." in normalized.split("/"):
        return "Error: Access denied: path traversal is not allowed"


def is_skills_path(path: str) -> bool:
    p = path.rstrip("/")
    return p == "/mnt/skills" or p.startswith("/mnt/skills/")


def validate_execute_command_paths(command: str) -> str | None:
    """限制命令中的绝对路径只允许 /mnt 或少量系统路径。"""
    try:
        tokens = shlex.split(command)
    except ValueError as e:
        return f"Error: Invalid shell command: {e}"

    for token in tokens:
        # 处理重定向符号后面的路径
        candidate = token
        if token.startswith((">", "<")) and len(token) > 1:
            candidate = token[1:]

        if not candidate.startswith("/"):
            continue

        if candidate.startswith("/mnt/"):
            error = ensure_path_allowed(candidate)
            if error:
                return error
            continue

        if any(candidate.startswith(prefix) for prefix in SYSTEM_EXEC_ALLOWED_PREFIXES):
            continue

        # /usr/lib/python 等运行时依赖路径可能会出现在参数里，放行 /usr/lib
        if candidate.startswith("/usr/lib/"):
            continue

        return f"Error: Access denied: absolute path '{candidate}' is not allowed"


def mask_host_paths(text: str, path_mappings: list[tuple[str, str]]) -> str:
    masked = text
    for host_path, virtual_path in path_mappings:
        if not host_path:
            continue
        escaped = re.escape(host_path)
        masked = re.sub(escaped, virtual_path, masked)
    return masked
