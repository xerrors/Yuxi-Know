from __future__ import annotations

import asyncio
import contextlib
import io
import mimetypes
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import aiofiles
from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from yuxi.agents.backends.sandbox.paths import _global_user_data_dir, ensure_workspace_default_files
from yuxi.services.viewer_filesystem_service import _detect_preview_type
from yuxi.storage.postgres.models_business import User
from yuxi.utils.datetime_utils import utc_isoformat_from_timestamp
from yuxi.utils.paths import WORKSPACE_DIR_NAME


EDITABLE_WORKSPACE_SUFFIXES = {".md", ".markdown", ".mdx", ".txt"}


def _workspace_root(user: User) -> Path:
    try:
        root = _global_user_data_dir(str(user.id)) / WORKSPACE_DIR_NAME
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc
    root.mkdir(parents=True, exist_ok=True)
    resolved_root = root.resolve()
    ensure_workspace_default_files(resolved_root)
    return resolved_root


def _normalize_workspace_path(path: str | None) -> PurePosixPath:
    raw_path = (path or "/").strip() or "/"
    if not raw_path.startswith("/"):
        raw_path = f"/{raw_path}"
    normalized = PurePosixPath(raw_path)
    if ".." in normalized.parts:
        raise HTTPException(status_code=403, detail="Access denied")
    return normalized


def _resolve_workspace_path(user: User, path: str | None) -> Path:
    root = _workspace_root(user)
    normalized = _normalize_workspace_path(path)
    relative_parts = [part for part in normalized.parts if part not in {"/", ""}]
    target = (root.joinpath(*relative_parts) if relative_parts else root).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc
    return target


def _entry_for_path(root: Path, path: Path) -> dict:
    stat = path.stat()
    is_dir = path.is_dir()
    relative = path.relative_to(root).as_posix()
    display_path = f"/{relative}" if relative else "/"
    if is_dir and display_path != "/" and not display_path.endswith("/"):
        display_path = f"{display_path}/"
    return {
        "path": display_path,
        "name": path.name or "工作区",
        "is_dir": is_dir,
        "size": 0 if is_dir else stat.st_size,
        "modified_at": utc_isoformat_from_timestamp(stat.st_mtime) or "",
    }


def _sort_entries(entries: list[dict]) -> list[dict]:
    return sorted(entries, key=lambda item: (not bool(item.get("is_dir")), str(item.get("name") or "").lower()))


def _validate_child_name(name: str, *, field_name: str) -> str:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise HTTPException(status_code=422, detail=f"{field_name} 不能为空")
    if clean_name in {".", ".."} or "/" in clean_name or "\\" in clean_name:
        raise HTTPException(status_code=422, detail=f"{field_name} 不能包含路径分隔符")
    if PurePosixPath(clean_name).name != clean_name:
        raise HTTPException(status_code=422, detail=f"{field_name} 不能包含路径分隔符")
    return clean_name


def _resolve_parent_directory(user: User, parent_path: str) -> Path:
    parent = _resolve_workspace_path(user, parent_path)
    if not parent.exists():
        raise HTTPException(status_code=404, detail="目标目录不存在")
    if not parent.is_dir():
        raise HTTPException(status_code=400, detail="目标路径不是目录")
    return parent


def _resolve_new_child(root: Path, parent: Path, name: str) -> Path:
    target = parent / name
    try:
        target.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc
    if target.exists():
        raise HTTPException(status_code=400, detail="同名文件或文件夹已存在")
    return target


def _list_directory(root: Path, target: Path) -> list[dict]:
    entries = [_entry_for_path(root, child) for child in target.iterdir()]
    return _sort_entries(entries)


async def list_workspace_tree(*, path: str, current_user: User) -> dict:
    root = _workspace_root(current_user)
    target = _resolve_workspace_path(current_user, path)
    if not target.exists():
        return {"entries": []}
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="当前路径不是目录")
    entries = await asyncio.to_thread(_list_directory, root, target)
    return {"entries": entries}


async def read_workspace_file_content(*, path: str, current_user: User) -> dict:
    target = _resolve_workspace_path(current_user, path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    if not target.is_file():
        raise HTTPException(status_code=400, detail="当前路径是目录")

    raw_content = await asyncio.to_thread(target.read_bytes)
    preview_type, supported, message = _detect_preview_type(path, raw_content)
    if preview_type in {"image", "pdf"} or not supported:
        return {
            "content": None,
            "preview_type": preview_type,
            "supported": supported,
            "message": message,
        }
    return {
        "content": raw_content.decode("utf-8"),
        "preview_type": preview_type,
        "supported": supported,
        "message": message,
    }


async def write_workspace_file_content(*, path: str, content: str, current_user: User) -> dict:
    root = _workspace_root(current_user)
    target = _resolve_workspace_path(current_user, path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    if not target.is_file():
        raise HTTPException(status_code=400, detail="当前路径是目录")
    if target.suffix.lower() not in EDITABLE_WORKSPACE_SUFFIXES:
        raise HTTPException(status_code=400, detail="当前文件类型不支持编辑")

    raw_content = await asyncio.to_thread(target.read_bytes)
    preview_type, supported, _message = _detect_preview_type(path, raw_content)
    if preview_type not in {"markdown", "text"} or not supported:
        raise HTTPException(status_code=400, detail="当前文件类型不支持编辑")
    try:
        raw_content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="当前文件不是 UTF-8 文本") from exc

    try:
        await asyncio.to_thread(target.write_text, content, encoding="utf-8")
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "success": True,
        "path": _normalize_workspace_path(path).as_posix(),
        "entry": _entry_for_path(root, target),
    }


async def delete_workspace_path(*, path: str, current_user: User) -> dict:
    root = _workspace_root(current_user)
    target = _resolve_workspace_path(current_user, path)
    if target == root:
        raise HTTPException(status_code=400, detail="工作区根目录不允许删除")
    if not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        if target.is_dir():
            await asyncio.to_thread(shutil.rmtree, target)
        else:
            await asyncio.to_thread(target.unlink)
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"success": True, "path": _normalize_workspace_path(path).as_posix()}


async def create_workspace_directory(*, parent_path: str, name: str, current_user: User) -> dict:
    root = _workspace_root(current_user)
    directory_name = _validate_child_name(name, field_name="文件夹名")
    parent = _resolve_parent_directory(current_user, parent_path)
    target = _resolve_new_child(root, parent, directory_name)

    try:
        await asyncio.to_thread(target.mkdir)
    except FileExistsError as exc:
        raise HTTPException(status_code=400, detail="同名文件或文件夹已存在") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"success": True, "entry": _entry_for_path(root, target)}


async def upload_workspace_file(*, parent_path: str, file: UploadFile, current_user: User) -> dict:
    root = _workspace_root(current_user)
    file_name = _validate_child_name(Path(file.filename or "").name, field_name="文件名")
    parent = _resolve_parent_directory(current_user, parent_path)
    target = _resolve_new_child(root, parent, file_name)
    created_file = False
    upload_completed = False

    try:
        async with aiofiles.open(target, "xb") as buffer:
            created_file = True
            while chunk := await file.read(1024 * 1024):
                await buffer.write(chunk)
        upload_completed = True
    except FileExistsError as exc:
        raise HTTPException(status_code=400, detail="同名文件或文件夹已存在") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if created_file and not upload_completed and target.exists():
            with contextlib.suppress(OSError):
                await asyncio.to_thread(target.unlink)

    return {"success": True, "entry": _entry_for_path(root, target)}


async def download_workspace_file(*, path: str, current_user: User) -> StreamingResponse | FileResponse:
    target = _resolve_workspace_path(current_user, path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    if not target.is_file():
        raise HTTPException(status_code=400, detail="当前路径是目录")

    file_name = target.name or "download"
    media_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(file_name)}"}
    if target.stat().st_size > 1024 * 1024 * 16:
        return FileResponse(path=target, media_type=media_type, headers=headers)

    content = await asyncio.to_thread(target.read_bytes)
    return StreamingResponse(io.BytesIO(content), media_type=media_type, headers=headers)
