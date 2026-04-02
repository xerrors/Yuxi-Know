from __future__ import annotations

import re
from pathlib import Path

from yuxi import config as conf
from yuxi.utils.paths import OUTPUTS_DIR_NAME, UPLOADS_DIR_NAME, VIRTUAL_PATH_PREFIX, WORKSPACE_DIR_NAME

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def get_virtual_path_prefix() -> str:
    return "/" + VIRTUAL_PATH_PREFIX.strip("/")


def _validate_thread_id(thread_id: str) -> str:
    value = str(thread_id or "").strip()
    if not value:
        raise ValueError("thread_id is required")
    if not _SAFE_ID_RE.match(value):
        raise ValueError("thread_id contains invalid characters")
    return value


def _thread_root_dir(thread_id: str) -> Path:
    safe_thread_id = _validate_thread_id(thread_id)
    return Path(conf.save_dir) / "threads" / safe_thread_id / "user-data"


def _validate_user_id(user_id: str) -> str:
    value = str(user_id or "").strip()
    if not value:
        raise ValueError("user_id is required")
    if not _SAFE_ID_RE.match(value):
        raise ValueError("user_id contains invalid characters")
    return value


def _global_user_data_dir(user_id: str) -> Path:
    """Return the shared host-side directory used for one user's workspace files."""
    safe_user_id = _validate_user_id(user_id)
    return Path(conf.save_dir) / "threads" / "shared" / safe_user_id


def sandbox_user_data_dir(thread_id: str) -> Path:
    return _thread_root_dir(thread_id)


def sandbox_workspace_dir(thread_id: str, user_id: str) -> Path:
    _validate_thread_id(thread_id)
    return _global_user_data_dir(user_id) / WORKSPACE_DIR_NAME


def sandbox_uploads_dir(thread_id: str) -> Path:
    return _thread_root_dir(thread_id) / UPLOADS_DIR_NAME


def sandbox_outputs_dir(thread_id: str) -> Path:
    return _thread_root_dir(thread_id) / OUTPUTS_DIR_NAME


def ensure_thread_dirs(thread_id: str, user_id: str) -> None:
    _global_user_data_dir(user_id).mkdir(parents=True, exist_ok=True)
    sandbox_workspace_dir(thread_id, user_id).mkdir(parents=True, exist_ok=True)
    sandbox_uploads_dir(thread_id).mkdir(parents=True, exist_ok=True)
    sandbox_outputs_dir(thread_id).mkdir(parents=True, exist_ok=True)


def _resolve_user_data_base_dir(thread_id: str, user_id: str, relative_path: str) -> tuple[Path, Path]:
    """Map a virtual user-data path to the correct host-side base directory."""
    parts = Path(relative_path).parts
    if not parts:
        base_dir = sandbox_user_data_dir(thread_id)
        return base_dir.resolve(), base_dir.resolve()

    namespace = parts[0]
    if namespace == WORKSPACE_DIR_NAME:
        # Workspace is shared across one user's threads, so it lives outside the per-thread root.
        base_dir = sandbox_workspace_dir(thread_id, user_id)
        target_path = base_dir.joinpath(*parts[1:]) if len(parts) > 1 else base_dir
        return base_dir.resolve(), target_path.resolve()
    if namespace == UPLOADS_DIR_NAME:
        base_dir = sandbox_uploads_dir(thread_id)
        target_path = base_dir.joinpath(*parts[1:]) if len(parts) > 1 else base_dir
        return base_dir.resolve(), target_path.resolve()
    if namespace == OUTPUTS_DIR_NAME:
        base_dir = sandbox_outputs_dir(thread_id)
        target_path = base_dir.joinpath(*parts[1:]) if len(parts) > 1 else base_dir
        return base_dir.resolve(), target_path.resolve()

    base_dir = sandbox_user_data_dir(thread_id)
    return base_dir.resolve(), (base_dir / relative_path).resolve()


def resolve_virtual_path(thread_id: str, virtual_path: str, *, user_id: str) -> Path:
    clean_virtual_path = "/" + str(virtual_path or "").strip().lstrip("/")
    virtual_prefix = get_virtual_path_prefix()

    if clean_virtual_path != virtual_prefix and not clean_virtual_path.startswith(f"{virtual_prefix}/"):
        raise ValueError(f"path must start with {virtual_prefix}")

    relative_path = clean_virtual_path[len(virtual_prefix) :].lstrip("/")
    base_dir, target_path = _resolve_user_data_base_dir(thread_id, user_id, relative_path)

    try:
        target_path.relative_to(base_dir)
    except ValueError as exc:
        raise ValueError("path traversal detected") from exc

    return target_path


def virtual_path_for_thread_file(thread_id: str, path: str | Path, *, user_id: str) -> str:
    target_path = Path(path).resolve()
    thread_root = sandbox_user_data_dir(thread_id).resolve()
    global_workspace_root = sandbox_workspace_dir(thread_id, user_id).resolve()

    try:
        relative_path = target_path.relative_to(global_workspace_root)
    except ValueError:
        try:
            relative_path = target_path.relative_to(thread_root)
        except ValueError as exc:
            raise ValueError("file is outside allowed user-data directories") from exc
        relative_path_str = relative_path.as_posix()
    else:
        workspace_relative = relative_path.as_posix()
        relative_path_str = (
            WORKSPACE_DIR_NAME if workspace_relative in {"", "."} else f"{WORKSPACE_DIR_NAME}/{workspace_relative}"
        )

    prefix = get_virtual_path_prefix().rstrip("/")
    if not relative_path_str:
        return prefix
    return f"{prefix}/{relative_path_str}"
