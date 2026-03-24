from __future__ import annotations

import re
from pathlib import Path

from yuxi import config as conf

DEFAULT_VIRTUAL_PATH_PREFIX = "/mnt/user-data"
VIRTUAL_PATH_PREFIX = DEFAULT_VIRTUAL_PATH_PREFIX

_SAFE_THREAD_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def get_virtual_path_prefix() -> str:
    configured = str(getattr(conf, "sandbox_virtual_path_prefix", "") or "").strip()
    if not configured:
        return DEFAULT_VIRTUAL_PATH_PREFIX
    return "/" + configured.strip("/")


def _validate_thread_id(thread_id: str) -> str:
    value = str(thread_id or "").strip()
    if not value:
        raise ValueError("thread_id is required")
    if not _SAFE_THREAD_ID_RE.match(value):
        raise ValueError("thread_id contains invalid characters")
    return value


def _thread_root_dir(thread_id: str) -> Path:
    safe_thread_id = _validate_thread_id(thread_id)
    return Path(conf.save_dir) / "threads" / safe_thread_id / "user-data"


def sandbox_user_data_dir(thread_id: str) -> Path:
    return _thread_root_dir(thread_id)


def sandbox_workspace_dir(thread_id: str) -> Path:
    return _thread_root_dir(thread_id) / "workspace"


def sandbox_uploads_dir(thread_id: str) -> Path:
    return _thread_root_dir(thread_id) / "uploads"


def sandbox_outputs_dir(thread_id: str) -> Path:
    return _thread_root_dir(thread_id) / "outputs"


def ensure_thread_dirs(thread_id: str) -> None:
    sandbox_workspace_dir(thread_id).mkdir(parents=True, exist_ok=True)
    sandbox_uploads_dir(thread_id).mkdir(parents=True, exist_ok=True)
    sandbox_outputs_dir(thread_id).mkdir(parents=True, exist_ok=True)


def resolve_virtual_path(thread_id: str, virtual_path: str) -> Path:
    clean_virtual_path = "/" + str(virtual_path or "").strip().lstrip("/")
    virtual_prefix = get_virtual_path_prefix()

    if clean_virtual_path != virtual_prefix and not clean_virtual_path.startswith(f"{virtual_prefix}/"):
        raise ValueError(f"path must start with {virtual_prefix}")

    relative_path = clean_virtual_path[len(virtual_prefix) :].lstrip("/")
    base_dir = sandbox_user_data_dir(thread_id).resolve()
    target_path = (base_dir / relative_path).resolve()

    try:
        target_path.relative_to(base_dir)
    except ValueError as exc:
        raise ValueError("path traversal detected") from exc

    return target_path


def virtual_path_for_thread_file(thread_id: str, path: str | Path) -> str:
    base_dir = sandbox_user_data_dir(thread_id).resolve()
    target_path = Path(path).resolve()

    try:
        relative_path = target_path.relative_to(base_dir)
    except ValueError as exc:
        raise ValueError("file is outside thread user-data directory") from exc

    prefix = get_virtual_path_prefix().rstrip("/")
    if not str(relative_path):
        return prefix
    return f"{prefix}/{relative_path.as_posix()}"
