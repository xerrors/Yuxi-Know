from __future__ import annotations

import contextlib
import errno
import hashlib
import os
import re
import uuid
from datetime import datetime
from pathlib import Path, PurePosixPath

from yuxi.infrastructure.filesystem import open_directory_fd
from yuxi.infrastructure.observability.logging import logger
from yuxi.infrastructure.runtime_settings import get_user_data_dir
from yuxi.shared.datetime import ensure_shanghai, shanghai_now

WORKSPACE_DIR_NAME = "workspace"
WORKSPACE_AGENTS_DIR_NAME = "agents"
WORKSPACE_AGENT_CONTEXT_FILES = {
    "AGENTS.md": "# AGENTS\n\n以下是约束 Agent 行为的一些要求\n",
    "USER.md": "# USER\n\n以下是有关用户的一些信息\n",
    "MEMORY.md": "# MEMORY\n\n以下是 Agent 需要记住的一些信息\n",
}

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_MANAGED_WORKDIR_NAME_RE = re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})_[0-9a-f]{8}(?:-[1-9]\d*)?$")
_MANAGED_WORKDIR_TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"
WORKDIR_PROJECTS_DIR_NAME = "projects"


def normalize_workspace_scope(path: str) -> str:
    """规范化用户文件 scope，拒绝跳转、URL、反斜杠与 NUL。"""
    raw = str(path or "").strip()
    pure = PurePosixPath(raw)
    if not raw or not pure.is_absolute() or ".." in pure.parts or "\\" in raw or "://" in raw or "\0" in raw:
        raise ValueError("invalid Workspace scope path")
    return pure.as_posix()


def validate_directory_name(name: str) -> str:
    """目录创建只接受单个普通 POSIX 组件。"""
    if not name or name in {".", ".."} or any(char in name for char in ("/", "\\", "\0")):
        raise ValueError("directory name must be one path component")
    return name


def validate_thread_id(thread_id: str) -> str:
    value = str(thread_id or "").strip()
    if not value:
        raise ValueError("thread_id is required")
    if not _SAFE_ID_RE.match(value):
        raise ValueError("thread_id contains invalid characters")
    return value


def normalize_workdir_path(workdir_path: str) -> str:
    """规范化数据库中的 UserWorkspace 相对 Workdir 路径。"""
    raw = str(workdir_path or "").strip()
    pure = PurePosixPath(raw)
    if not raw or pure.is_absolute() or "\\" in raw or "://" in raw:
        raise ValueError("workdir_path must be a relative POSIX path")
    if any(part in {"", ".", ".."} for part in raw.split("/")):
        raise ValueError("workdir_path contains invalid path components")
    return pure.as_posix()


def normalize_managed_workdir_path(workdir_path: str) -> str:
    """规范化服务端管理的 Workdir 路径。"""
    error_message = "managed workdir_path must use a supported projects/<managed-id>"
    try:
        pure = PurePosixPath(normalize_workdir_path(workdir_path))
    except ValueError:
        raise ValueError(error_message) from None
    if len(pure.parts) != 2 or pure.parts[0] != WORKDIR_PROJECTS_DIR_NAME:
        raise ValueError(error_message)

    workdir_name = pure.parts[1]
    match = _MANAGED_WORKDIR_NAME_RE.fullmatch(workdir_name)
    if match is None:
        raise ValueError(error_message)
    try:
        datetime.strptime(match.group("timestamp"), _MANAGED_WORKDIR_TIMESTAMP_FORMAT)
    except ValueError:
        raise ValueError(error_message) from None
    return pure.as_posix()


def workspace_uid_dirname(uid: str) -> str:
    """Return a path-safe, stable workspace directory name for a logical UID.

    Database and OIDC subject identifiers may contain characters such as ``:``
    that are valid identity data but unsafe in filesystem path components.
    Identity-safe UIDs keep a readable directory name; all other values use a
    namespaced SHA-256 digest at the filesystem boundary only.
    """
    value = str(uid or "").strip()
    if not value:
        raise ValueError("uid is required")
    if _SAFE_ID_RE.fullmatch(value):
        return value
    return f"uid-{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def global_user_data_dir(uid: str) -> Path:
    """Return the shared host-side directory used for one user's workspace files."""
    safe_uid = workspace_uid_dirname(uid)
    return get_user_data_dir() / "shared" / safe_uid


def user_workspace_dir(uid: str) -> Path:
    """返回用户级实时 Workspace 根。"""
    return global_user_data_dir(uid) / WORKSPACE_DIR_NAME


def user_workdir_host_dir(uid: str, workdir_path: str) -> Path:
    """解析当前用户 Workdir，拒绝任意 symlink 路径组件。"""
    normalized = normalize_workdir_path(workdir_path)
    workspace = user_workspace_dir(uid)
    target = workspace.joinpath(*PurePosixPath(normalized).parts)
    _open_workspace_directory(uid, PurePosixPath(normalized).parts)
    if not target.is_dir():
        raise ValueError("workdir_path does not reference an existing directory")
    return target


def allocate_default_user_workdir_path(
    uid: str,
    project_id: str,
    *,
    allocated_at: datetime | None = None,
) -> str:
    """按上海时间与 Project ID 分配未占用的 managed Workdir 路径。"""
    canonical_project_id = str(uuid.UUID(str(project_id)))
    timestamp = ensure_shanghai(allocated_at or shanghai_now()).strftime(_MANAGED_WORKDIR_TIMESTAMP_FORMAT)
    base_name = f"{timestamp}_{canonical_project_id[:8]}"
    suffix = 0
    while True:
        name = base_name if suffix == 0 else f"{base_name}-{suffix}"
        if not _user_workspace_entry_exists(uid, name):
            return f"{WORKDIR_PROJECTS_DIR_NAME}/{name}"
        suffix += 1


def _user_workspace_entry_exists(uid: str, workdir_name: str) -> bool:
    """以 no-follow 方式判断 managed Workdir 名称是否已被占用。"""
    try:
        workspace_fd = _open_user_workspace_fd(uid)
    except FileNotFoundError:
        return False

    parent_fd = None
    try:
        try:
            parent_fd = _open_workspace_child_fd(workspace_fd, (WORKDIR_PROJECTS_DIR_NAME,))
        except FileNotFoundError:
            return False
        try:
            os.stat(workdir_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        return True
    finally:
        if parent_fd is not None:
            os.close(parent_fd)
        os.close(workspace_fd)


def ensure_bound_user_workdir(uid: str, workdir_path: str) -> None:
    """物化已提交数据库绑定的 canonical Workdir。"""
    normalized = normalize_managed_workdir_path(workdir_path)
    parts = PurePosixPath(normalized).parts
    try:
        _open_workspace_directory(uid, parts)
        return
    except FileNotFoundError:
        pass
    ensure_user_workspace(uid)
    workspace_fd = _open_user_workspace_fd(uid)
    try:
        directory_fd = _open_workspace_child_fd(workspace_fd, parts, create=True)
        os.close(directory_fd)
    finally:
        os.close(workspace_fd)


def _open_workspace_directory(uid: str, parts: tuple[str, ...]) -> None:
    """逐层以 O_NOFOLLOW 打开 UserWorkspace 目录。"""
    directory_fd = _open_user_workspace_fd(uid)
    try:
        child_fd = _open_workspace_child_fd(directory_fd, parts)
        os.close(child_fd)
    finally:
        os.close(directory_fd)


def _open_user_workspace_fd(uid: str, *, create: bool = False) -> int:
    """从配置根逐层打开 uid 的 Workspace，拒绝中间 symlink。"""
    root = get_user_data_dir()
    if create:
        root.mkdir(parents=True, exist_ok=True)
    try:
        return open_directory_fd(
            root,
            ("shared", workspace_uid_dirname(uid), WORKSPACE_DIR_NAME),
            create=create,
        )
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise ValueError("UserWorkspace 路径包含符号链接或非目录组件") from exc
        raise


def _open_workspace_child_fd(directory_fd: int, parts: tuple[str, ...], *, create: bool = False) -> int:
    """从已固定的 UserWorkspace fd 打开子目录并翻译边界错误。"""
    try:
        return open_directory_fd(directory_fd, parts, create=create)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise ValueError("UserWorkspace 路径包含符号链接或非目录组件") from exc
        raise


def _ensure_workspace_default_files_fd(workspace_fd: int) -> None:
    """通过已校验的 Workspace fd 初始化 Agent 上下文文件。"""
    try:
        agents_fd = open_directory_fd(workspace_fd, (WORKSPACE_AGENTS_DIR_NAME,), create=True)
    except OSError as exc:
        logger.warning(f"工作区默认 Agents 目录初始化失败: {exc}")
        return
    try:
        for filename, default_content in WORKSPACE_AGENT_CONTEXT_FILES.items():
            try:
                file_fd = os.open(
                    filename,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=agents_fd,
                )
            except FileExistsError:
                continue
            except OSError as exc:
                logger.warning(f"工作区默认 {filename} 初始化失败: {exc}")
                continue
            try:
                content = default_content.encode("utf-8")
                offset = 0
                while offset < len(content):
                    offset += os.write(file_fd, content[offset:])
            except BaseException:
                os.close(file_fd)
                file_fd = None
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(filename, dir_fd=agents_fd)
                raise
            finally:
                if file_fd is not None:
                    os.close(file_fd)
    finally:
        os.close(agents_fd)


def ensure_user_workspace(uid: str) -> None:
    """创建用户级 Workspace 与默认 Agent 上下文文件。"""
    workspace_fd = _open_user_workspace_fd(uid, create=True)
    try:
        _ensure_workspace_default_files_fd(workspace_fd)
    finally:
        os.close(workspace_fd)
