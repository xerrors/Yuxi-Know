from __future__ import annotations

import asyncio
import contextlib
import errno
import os
import tempfile
from pathlib import Path, PurePosixPath

from yuxi.infrastructure.file_preview import detect_preview_type, preview_too_large
from yuxi.infrastructure.filesystem import await_io
from yuxi.infrastructure.office_conversion import OfficeConversionError
from yuxi.modules.identity.models import User
from yuxi.modules.workspace.errors import FileTransferLimitError
from yuxi.modules.workspace.filesystem import Workspace
from yuxi.modules.workspace.paths import ensure_user_workspace, normalize_workspace_scope, validate_directory_name
from yuxi.modules.workspace.preview import preview_workspace_file
from yuxi.modules.workspace.repositories.projects import ProjectRepository
from yuxi.modules.workspace.runtime_paths import runtime_workspace_path
from yuxi.modules.workspace.services.file_entries import file_entry, sort_file_entries
from yuxi.shared.errors import (
    ContentTooLargeError,
    DomainError,
    InvalidInputError,
    InvalidOperationError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from yuxi.shared.files import MAX_FILE_PREVIEW_BYTES, FileInput, PreparedFile, PreviewResult, detect_media_type

EDITABLE_WORKSPACE_SUFFIXES = {".md", ".markdown", ".mdx", ".txt"}
MAX_WORKSPACE_UPLOAD_SIZE_BYTES = 100 * 1024 * 1024
MAX_WORKSPACE_UPLOAD_FILES = 50
# 完整虚拟路径（含 parent_path）的段数上限，避免创建既有递归删除无法回收的目录树。
MAX_WORKSPACE_UPLOAD_PATH_DEPTH = 64
MAX_WORKSPACE_UPLOAD_NAME_BYTES = 255
MAX_WORKSPACE_UPLOAD_PATH_BYTES = 4096
MAX_WORKSPACE_DOWNLOAD_SIZE_BYTES = 1024 * 1024 * 1024

# 搜索返回条数上限，避免超大工作区一次性返回过多结果
WORKSPACE_SEARCH_MAX_RESULTS = 100
WORKSPACE_SCOPE_ROOT = "/"


async def search_workspace_files(*, query: str, current_user: User) -> dict:
    """按文件名在个人工作区内递归搜索，仅返回文件条目。"""
    normalized_query = (query or "").strip().lower()
    if not normalized_query:
        return {"entries": []}

    backend = _workspace_backend(current_user)
    try:
        matches = await asyncio.to_thread(
            backend.search_authorized_tree,
            WORKSPACE_SCOPE_ROOT,
            normalized_query,
            include_directories=False,
            max_results=WORKSPACE_SEARCH_MAX_RESULTS,
        )
    except FileNotFoundError:
        return {"entries": []}
    return {"entries": [_entry_from_metadata(item["path"], item) for item in matches]}


async def list_workspace_tree(
    *,
    path: str,
    recursive: bool = False,
    files_only: bool = False,
    include_unbound_project_dirs: bool = False,
    current_user: User,
    db,
) -> dict:
    backend = _workspace_backend(current_user)
    workspace_path = _workspace_path(path)
    try:
        if recursive:
            scanned = await asyncio.to_thread(
                backend.search_authorized_tree,
                workspace_path,
                "",
                include_directories=not files_only,
                max_results=5000,
            )
            entries = [_entry_from_metadata(item["path"], item) for item in scanned]
        else:
            entries = await asyncio.to_thread(
                _list_workspace_directory,
                backend,
                workspace_path,
                files_only=files_only,
            )
    except FileNotFoundError:
        return {"entries": []}
    except NotADirectoryError as exc:
        raise InvalidOperationError("当前路径不是目录") from exc
    except PermissionError as exc:
        raise PermissionDeniedError("Access denied") from exc
    if not include_unbound_project_dirs:
        entries = await _filter_project_tree_entries(entries, uid=str(current_user.uid), db=db)
    return {"entries": entries}


async def _filter_project_tree_entries(entries: list[dict], *, uid: str, db) -> list[dict]:
    """隐藏未归属 selectable Project 的 projects 子树。"""
    entries_with_paths = [(entry, PurePosixPath(str(entry.get("path") or "/").strip("/"))) for entry in entries]
    if not any(path.parts[:1] == ("projects",) and path.as_posix() != "projects" for _, path in entries_with_paths):
        return entries

    visible_paths = await ProjectRepository(db).list_selectable_workdir_paths_for_user(uid)
    selected_project_paths = [PurePosixPath(path) for path in visible_paths if PurePosixPath(path).parts[:1] == ("projects",)]

    def is_visible(candidate: PurePosixPath) -> bool:
        if candidate.parts[:1] != ("projects",) or candidate.as_posix() == "projects":
            return True
        return any(
            candidate == selected or candidate.is_relative_to(selected) or selected.is_relative_to(candidate)
            for selected in selected_project_paths
        )

    return [entry for entry, path in entries_with_paths if is_visible(path)]


async def read_workspace_file_bytes(*, path: str, current_user: User) -> tuple[str, bytes]:
    """在 no-follow Workspace 边界内读取知识库导入文件。"""
    backend = _workspace_backend(current_user)
    workspace_path = _workspace_path(path)
    try:
        content = await asyncio.to_thread(
            backend.read_authorized_file,
            workspace_path,
            MAX_WORKSPACE_UPLOAD_SIZE_BYTES,
        )
    except FileTransferLimitError as exc:
        raise InvalidOperationError("文件过大，当前仅支持 100 MB 以内的工作区文件") from exc
    except FileNotFoundError as exc:
        raise ResourceNotFoundError(f"工作区文件不存在: {path}") from exc
    except IsADirectoryError as exc:
        raise InvalidOperationError(f"当前路径不是文件: {path}") from exc
    except (PermissionError, NotADirectoryError, ValueError) as exc:
        raise PermissionDeniedError("Access denied") from exc
    return PurePosixPath(workspace_path).name, content


async def read_workspace_file_content(*, path: str, current_user: User) -> dict | PreviewResult:
    backend = _workspace_backend(current_user)
    workspace_path = _workspace_path(path)
    try:
        raw_content = await asyncio.to_thread(
            backend.read_authorized_file,
            workspace_path,
            MAX_FILE_PREVIEW_BYTES,
        )
    except FileTransferLimitError:
        return preview_too_large().payload()
    except FileNotFoundError as exc:
        raise ResourceNotFoundError("文件不存在") from exc
    except IsADirectoryError as exc:
        raise InvalidOperationError("当前路径不是文件") from exc
    except (PermissionError, NotADirectoryError, ValueError) as exc:
        raise PermissionDeniedError("Access denied") from exc

    try:
        return await preview_workspace_file(
            path,
            raw_content,
            office_cache_key=f"workspace:{current_user.uid}:{workspace_path}",
        )
    except OfficeConversionError as exc:
        raise InvalidOperationError(str(exc)) from exc


async def write_workspace_file_content(*, path: str, content: str, current_user: User) -> dict:
    backend = _workspace_backend(current_user)
    workspace_path = _workspace_path(path)
    if PurePosixPath(workspace_path).suffix.lower() not in EDITABLE_WORKSPACE_SUFFIXES:
        raise InvalidOperationError("当前文件类型不支持编辑")

    try:
        raw_content = await asyncio.to_thread(
            backend.read_authorized_file,
            workspace_path,
            MAX_WORKSPACE_UPLOAD_SIZE_BYTES,
        )
    except FileNotFoundError as exc:
        raise ResourceNotFoundError("文件不存在") from exc
    except IsADirectoryError as exc:
        raise InvalidOperationError("当前路径是目录") from exc
    except (PermissionError, NotADirectoryError, ValueError) as exc:
        raise PermissionDeniedError("Access denied") from exc
    preview_type, supported, _message = detect_preview_type(path, raw_content)
    if preview_type not in {"markdown", "text"} or not supported:
        raise InvalidOperationError("当前文件类型不支持编辑")
    try:
        raw_content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidOperationError("当前文件不是 UTF-8 文本") from exc

    try:
        item = await asyncio.to_thread(backend.write_authorized_file, workspace_path, content.encode("utf-8"))
    except FileNotFoundError as exc:
        raise ResourceNotFoundError("文件不存在") from exc
    except IsADirectoryError as exc:
        raise InvalidOperationError("当前路径是目录") from exc
    except (PermissionError, NotADirectoryError, ValueError) as exc:
        raise PermissionDeniedError("Access denied") from exc

    return {
        "success": True,
        "path": _normalize_workspace_path(path).as_posix(),
        "entry": _entry_from_metadata(workspace_path, item),
    }


async def delete_workspace_path(*, path: str, current_user: User) -> dict:
    backend = _workspace_backend(current_user)
    workspace_path = _workspace_path(path)
    if workspace_path == WORKSPACE_SCOPE_ROOT:
        raise InvalidOperationError("工作区根目录不允许删除")

    try:
        await asyncio.to_thread(
            backend.delete_authorized_path,
            workspace_path,
            root=WORKSPACE_SCOPE_ROOT,
        )
    except FileNotFoundError as exc:
        raise ResourceNotFoundError("文件不存在") from exc
    except (PermissionError, NotADirectoryError, ValueError) as exc:
        raise PermissionDeniedError("Access denied") from exc

    return {"success": True, "path": _normalize_workspace_path(path).as_posix()}


async def create_workspace_directory(*, parent_path: str, name: str, current_user: User) -> dict:
    backend = _workspace_backend(current_user)
    directory_name = _validate_child_name(name, field_name="文件夹名")
    virtual_parent = _workspace_path(parent_path)
    target = f"{virtual_parent.rstrip('/')}/{directory_name}"

    try:
        item = await asyncio.to_thread(
            backend.create_authorized_directory,
            virtual_parent,
            directory_name,
            root=WORKSPACE_SCOPE_ROOT,
        )
    except FileExistsError as exc:
        raise InvalidOperationError("同名文件或文件夹已存在") from exc
    except FileNotFoundError as exc:
        raise ResourceNotFoundError("目标目录不存在") from exc
    except (PermissionError, NotADirectoryError, ValueError) as exc:
        raise PermissionDeniedError("Access denied") from exc

    return {"success": True, "entry": _entry_from_metadata(target, item)}


async def upload_workspace_files(
    *,
    parent_path: str,
    files: list[FileInput],
    relative_paths: list[str] | None = None,
    current_user: User,
) -> dict:
    """把借用的文件流写入用户工作区，失败时撤销本批次已写入文件。"""
    if not files:
        raise InvalidOperationError("请选择至少一个文件")
    if len(files) > MAX_WORKSPACE_UPLOAD_FILES:
        raise InvalidOperationError(f"一次最多上传 {MAX_WORKSPACE_UPLOAD_FILES} 个文件")
    if relative_paths is not None and len(relative_paths) != len(files):
        raise InvalidInputError("相对路径数量与文件数量不一致")

    backend = _workspace_backend(current_user)
    parent = _workspace_path(parent_path)
    try:
        parent_stat = await asyncio.to_thread(backend.stat_authorized_path, parent, root=WORKSPACE_SCOPE_ROOT)
    except FileNotFoundError as exc:
        raise ResourceNotFoundError("目标目录不存在") from exc
    except (PermissionError, NotADirectoryError, ValueError) as exc:
        raise PermissionDeniedError("Access denied") from exc
    if not parent_stat["is_dir"]:
        raise InvalidOperationError("目标路径不是目录")
    parent_depth = len(PurePosixPath(parent).parts) - 1
    if parent_depth >= MAX_WORKSPACE_UPLOAD_PATH_DEPTH:
        raise InvalidInputError("目标目录层级过深")
    seen_targets: set[str] = set()
    upload_targets: list[tuple[FileInput, str]] = []

    for index, file in enumerate(files):
        if relative_paths is None:
            file_name = _validate_child_name(Path(file.filename or "").name, field_name="文件名")
            target = f"{parent.rstrip('/')}/{file_name}"
        else:
            relative_path = _normalize_upload_relative_path(relative_paths[index], parent_depth=parent_depth)
            target = f"{parent.rstrip('/')}/{relative_path}"
        if target in seen_targets:
            raise InvalidOperationError(f"上传目标重复: {target}")
        seen_targets.add(target)
        upload_targets.append((file, target))

    for _file, target in upload_targets:
        if any(str(ancestor) in seen_targets for ancestor in PurePosixPath(target).parents):
            raise InvalidOperationError(f"文件与文件夹路径冲突: {target}", code="workspace_upload_path_conflict")

    await _ensure_upload_targets_available(backend, upload_targets)

    completed_entries: list[tuple[str, dict]] = []
    try:
        for file, target in upload_targets:
            item = await _write_workspace_upload(file, backend, target)
            completed_entries.append((target, item))
    except DomainError:
        for target, _item in completed_entries:
            with contextlib.suppress(OSError):
                await asyncio.to_thread(
                    backend.delete_authorized_path,
                    target,
                    root=WORKSPACE_SCOPE_ROOT,
                )
        raise

    entries = [_entry_from_metadata(target, item) for target, item in completed_entries]
    return {"success": True, "entries": entries}


async def download_workspace_file(*, path: str, current_user: User) -> PreparedFile:
    backend = _workspace_backend(current_user)
    workspace_path = _workspace_path(path)
    file_name = PurePosixPath(workspace_path).name or "download"
    media_type = detect_media_type(file_name)
    descriptor, temp_path = tempfile.mkstemp(prefix="yuxi-workspace-download-", suffix=PurePosixPath(file_name).suffix)
    os.close(descriptor)
    try:
        await asyncio.to_thread(
            backend.download_authorized_file_to_path,
            workspace_path,
            temp_path,
            MAX_WORKSPACE_DOWNLOAD_SIZE_BYTES,
        )
    except FileNotFoundError as exc:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_path)
        raise ResourceNotFoundError("文件不存在") from exc
    except FileTransferLimitError as exc:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_path)
        raise ContentTooLargeError("文件超过下载大小限制") from exc
    except (PermissionError, IsADirectoryError, NotADirectoryError, ValueError) as exc:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_path)
        raise PermissionDeniedError("Access denied") from exc
    return PreparedFile(
        path=temp_path,
        media_type=media_type,
        filename=file_name,
        explicit_disposition=True,
    )


def _workspace_backend(user: User) -> Workspace:
    """物化并返回 uid 级 no-follow 文件系统。"""
    backend = Workspace(str(user.uid))
    try:
        ensure_user_workspace(str(user.uid))
    except (OSError, ValueError) as exc:
        raise PermissionDeniedError("Access denied") from exc
    return backend


def _normalize_workspace_path(path: str | None) -> PurePosixPath:
    raw_path = (path or "/").strip() or "/"
    if not raw_path.startswith("/"):
        raw_path = f"/{raw_path}"
    try:
        return PurePosixPath(normalize_workspace_scope(raw_path))
    except ValueError as exc:
        raise PermissionDeniedError("Access denied") from exc


def _workspace_path(path: str | None) -> str:
    return _normalize_workspace_path(path).as_posix()


def _validate_child_name(name: str, *, field_name: str) -> str:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise InvalidInputError(f"{field_name} 不能为空")
    try:
        validate_directory_name(clean_name)
    except ValueError as exc:
        raise InvalidInputError(f"{field_name} 不能包含路径分隔符") from exc
    return clean_name


def _normalize_upload_relative_path(value: str, *, parent_depth: int = 0) -> str:
    """校验文件夹上传的相对路径，只接受普通 POSIX 路径组件。"""
    raw = str(value or "")
    if not raw or raw.startswith("/") or raw.endswith("/") or "\\" in raw or "\0" in raw:
        raise InvalidInputError("相对路径无效")
    parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise InvalidInputError("相对路径无效")
    if parent_depth + len(parts) > MAX_WORKSPACE_UPLOAD_PATH_DEPTH:
        raise InvalidInputError("相对路径层级过深")
    try:
        raw_bytes = raw.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise InvalidInputError("相对路径无效") from exc
    if len(raw_bytes) > MAX_WORKSPACE_UPLOAD_PATH_BYTES:
        raise InvalidInputError("相对路径过长")
    if len(parts[0]) == 2 and parts[0][1] == ":" and parts[0][0].isalpha():
        raise InvalidInputError("相对路径无效")
    for part in parts:
        # scope 的既有规范化会裁掉路径尾部空白，目录也必须能单独寻址。
        if part[-1].isspace():
            raise InvalidInputError("路径组件不能以空白字符结尾", code="workspace_upload_path_invalid")
        if len(part.encode("utf-8")) > MAX_WORKSPACE_UPLOAD_NAME_BYTES:
            raise InvalidInputError("相对路径组件过长")
        try:
            validate_directory_name(part)
        except ValueError as exc:
            raise InvalidInputError("相对路径无效") from exc
    return raw


def _entry_from_metadata(workspace_path: str, item: dict) -> dict:
    entry = file_entry(workspace_path, item)
    entry["virtual_path"] = runtime_workspace_path(workspace_path)
    if entry["is_dir"]:
        entry["size"] = 0
        if entry["path"] != "/":
            entry["virtual_path"] += "/"
    return entry


def _list_workspace_directory(
    backend: Workspace,
    target: str,
    *,
    files_only: bool = False,
) -> list[dict]:
    children = backend.list_authorized_directory(target, root=WORKSPACE_SCOPE_ROOT)
    entries = []
    for child in children:
        child_path = f"{target.rstrip('/')}/{child['name']}"
        if not files_only or not child["is_dir"]:
            entries.append(_entry_from_metadata(child_path, child))
    return sort_file_entries(entries)


async def _ensure_upload_targets_available(backend: Workspace, upload_targets: list[tuple[FileInput, str]]) -> None:
    """写入前拒绝已存在的目标和类型冲突，避免留下半批文件。"""
    for _file, target in upload_targets:
        try:
            await asyncio.to_thread(backend.stat_authorized_path, target, root=WORKSPACE_SCOPE_ROOT)
        except FileNotFoundError:
            continue
        except (PermissionError, NotADirectoryError, ValueError) as exc:
            raise InvalidOperationError(f"目标路径不可用: {target}") from exc
        except OSError as exc:
            if exc.errno == errno.ENAMETOOLONG:
                raise InvalidInputError("文件路径过长") from exc
            raise
        raise InvalidOperationError(f"同名文件或文件夹已存在: {target}")


async def _write_workspace_upload(file: FileInput, backend: Workspace, target: str) -> dict:
    """等待文件 I/O 完成后归还输入流，保留原子写入与冲突语义。"""
    try:
        return await await_io(
            asyncio.to_thread(
                backend.upload_authorized_file_from_stream,
                target,
                file.source,
                max_bytes=MAX_WORKSPACE_UPLOAD_SIZE_BYTES,
                overwrite=False,
            )
        )
    except FileExistsError as exc:
        raise InvalidOperationError(f"同名文件或文件夹已存在: {target}") from exc
    except NotADirectoryError as exc:
        raise InvalidOperationError(f"目标路径与已有文件冲突: {target}") from exc
    except FileTransferLimitError as exc:
        raise InvalidOperationError("文件过大，当前仅支持 100 MB 以内的文件") from exc
    except (ValueError, PermissionError) as exc:
        raise InvalidOperationError(str(exc)) from exc
