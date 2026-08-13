from __future__ import annotations

import asyncio
import contextlib
import hashlib
import io
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import aiofiles
from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from yuxi.agents.backends.sandbox.paths import (
    ensure_workspace_default_files,
    global_user_data_dir,
    sandbox_outputs_dir,
    sandbox_uploads_dir,
    validate_thread_id,
)
from yuxi.repositories.conversation_repository import ConversationRepository
from yuxi.services.file_preview import (
    MAX_BINARY_PREVIEW_SIZE_BYTES,
    OfficePreviewConversionError,
    convert_office_to_pdf,
    detect_media_type,
    detect_preview_type,
    is_binary_preview_type,
    is_office_pdf_preview_file,
    render_preview_payload,
    render_preview_too_large_payload,
)
from yuxi.services.mention_search_service import invalidate_workspace_mention_cache
from yuxi.storage.postgres.models_business import User
from yuxi.utils.datetime_utils import utc_isoformat_from_timestamp
from yuxi.utils.logging_config import logger
from yuxi.utils.paths import (
    CONVERSATION_HISTORY_DIR_NAME,
    LARGE_TOOL_RESULTS_DIR_NAME,
    OUTPUTS_DIR_NAME,
    UPLOADS_DIR_NAME,
    VIRTUAL_PATH_WORKSPACE,
    WORKSPACE_AGENTS_DIR_NAME,
    WORKSPACE_DIR_NAME,
    ensure_within_root,
)
from yuxi.utils.upload_utils import MAX_UPLOAD_SIZE_BYTES, write_upload_to_buffer

EDITABLE_WORKSPACE_SUFFIXES = {".md", ".markdown", ".mdx", ".txt"}
MAX_WORKSPACE_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_BYTES
MAX_WORKSPACE_UPLOAD_FILES = 50
WORKSPACE_CHATS_DIR_NAME = "chats"
_CHAT_READONLY_MESSAGE = "历史对话文件为只读，请在对应对话中修改"
_CHAT_INTERMEDIATE_DIR_NAMES = frozenset(
    {
        LARGE_TOOL_RESULTS_DIR_NAME,
        "large-tool-results",
        "large_tool_history",
        CONVERSATION_HISTORY_DIR_NAME,
    }
)


async def list_workspace_tree(
    *,
    path: str,
    recursive: bool = False,
    files_only: bool = False,
    current_user: User,
    thread_titles: dict[str, str] | None = None,
) -> dict:
    root = _workspace_root(current_user)
    if workspace_path_uses_chat_mapping(path):
        chats_path = root / WORKSPACE_AGENTS_DIR_NAME / WORKSPACE_CHATS_DIR_NAME
        if chats_path.is_symlink() or chats_path.exists():
            raise HTTPException(status_code=409, detail="工作区 agents/chats 已被现有文件或目录占用")
    if _chat_path_parts(path) is not None:
        entries = await asyncio.to_thread(
            _list_chat_directory,
            path,
            thread_titles=thread_titles or {},
            recursive=recursive,
            files_only=files_only,
        )
        return {"entries": entries, "readonly": True}

    target = _resolve_workspace_path(current_user, path)
    if not target.exists():
        return {"entries": []}
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="当前路径不是目录")
    entries = await asyncio.to_thread(_list_directory, root, target, recursive=recursive, files_only=files_only)
    if (
        thread_titles is not None
        and _normalize_workspace_path(path).as_posix().rstrip("/") == f"/{WORKSPACE_AGENTS_DIR_NAME}"
    ):
        entries = [entry for entry in entries if entry["name"] != WORKSPACE_CHATS_DIR_NAME]
        chats_path = f"/{WORKSPACE_AGENTS_DIR_NAME}/{WORKSPACE_CHATS_DIR_NAME}"
        if not files_only:
            entries.append(
                _virtual_entry(
                    chats_path,
                    name=WORKSPACE_CHATS_DIR_NAME,
                    title="历史对话",
                    is_dir=True,
                )
            )
        if recursive:
            entries.extend(
                await asyncio.to_thread(
                    _list_chat_directory,
                    chats_path,
                    thread_titles=thread_titles,
                    recursive=True,
                    files_only=files_only,
                )
            )
        entries = _sort_entries(entries)
    return {"entries": entries}


def resolve_workspace_file_path(*, path: str, current_user: User, thread_titles: dict[str, str] | None = None) -> Path:
    if _chat_path_parts(path) is not None:
        root = _workspace_root(current_user)
        chats_path = root / WORKSPACE_AGENTS_DIR_NAME / WORKSPACE_CHATS_DIR_NAME
        if chats_path.is_symlink() or chats_path.exists():
            raise HTTPException(status_code=409, detail="工作区 agents/chats 已被现有文件或目录占用")
        target, _display_path = _resolve_chat_path(path, thread_titles)
        if target is None:
            raise HTTPException(status_code=400, detail=f"当前路径不是文件: {path}")
    else:
        target = _resolve_workspace_path(current_user, path)
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"工作区文件不存在: {path}")
    if not target.is_file():
        raise HTTPException(status_code=400, detail=f"当前路径不是文件: {path}")
    return target


async def read_workspace_file_content(
    *, path: str, current_user: User, thread_titles: dict[str, str] | None = None
) -> dict | StreamingResponse:
    target = resolve_workspace_file_path(path=path, current_user=current_user, thread_titles=thread_titles)
    if not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    stat = await asyncio.to_thread(target.stat)
    if stat.st_size > MAX_BINARY_PREVIEW_SIZE_BYTES:
        return render_preview_too_large_payload()

    if is_office_pdf_preview_file(path):
        pdf_content = await _convert_workspace_office_to_pdf(current_user, target, target.name)
        return _preview_binary_response(
            filename=f"{target.stem or 'preview'}.pdf",
            content=pdf_content,
            media_type="application/pdf",
            preview_type="pdf",
        )

    raw_content = await asyncio.to_thread(target.read_bytes)
    preview_type, supported, message = detect_preview_type(path, raw_content)
    if is_binary_preview_type(preview_type) and supported:
        return _preview_binary_response(
            filename=target.name or "preview",
            content=raw_content,
            media_type=detect_media_type(path, raw_content),
            preview_type=preview_type,
        )
    if not supported:
        return {
            "content": None,
            "preview_type": preview_type,
            "supported": False,
            "message": message,
            "truncated": False,
            "limit": None,
        }
    return render_preview_payload(path, raw_content)


async def write_workspace_file_content(*, path: str, content: str, current_user: User) -> dict:
    if _chat_path_parts(path) is not None:
        raise HTTPException(status_code=403, detail=_CHAT_READONLY_MESSAGE)
    root = _workspace_root(current_user)
    target = _resolve_workspace_path(current_user, path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    if not target.is_file():
        raise HTTPException(status_code=400, detail="当前路径是目录")
    if target.suffix.lower() not in EDITABLE_WORKSPACE_SUFFIXES:
        raise HTTPException(status_code=400, detail="当前文件类型不支持编辑")

    raw_content = await asyncio.to_thread(target.read_bytes)
    preview_type, supported, _message = detect_preview_type(path, raw_content)
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
    if _chat_path_parts(path) is not None:
        raise HTTPException(status_code=403, detail=_CHAT_READONLY_MESSAGE)
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

    await invalidate_workspace_mention_cache(str(current_user.uid))
    return {"success": True, "path": _normalize_workspace_path(path).as_posix()}


async def create_workspace_directory(*, parent_path: str, name: str, current_user: User) -> dict:
    if _chat_path_parts(parent_path) is not None:
        raise HTTPException(status_code=403, detail=_CHAT_READONLY_MESSAGE)
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

    await invalidate_workspace_mention_cache(str(current_user.uid))
    return {"success": True, "entry": _entry_for_path(root, target)}


async def upload_workspace_files(*, parent_path: str, files: list[UploadFile], current_user: User) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="请选择至少一个文件")
    if len(files) > MAX_WORKSPACE_UPLOAD_FILES:
        raise HTTPException(status_code=400, detail=f"一次最多上传 {MAX_WORKSPACE_UPLOAD_FILES} 个文件")

    if _chat_path_parts(parent_path) is not None:
        raise HTTPException(status_code=403, detail=_CHAT_READONLY_MESSAGE)
    root = _workspace_root(current_user)
    parent = _resolve_parent_directory(current_user, parent_path)
    seen_names = set()
    upload_targets: list[tuple[UploadFile, Path]] = []

    for file in files:
        file_name = _validate_child_name(Path(file.filename or "").name, field_name="文件名")
        if file_name in seen_names:
            raise HTTPException(status_code=400, detail=f"选择的文件中存在重复文件名: {file_name}")
        seen_names.add(file_name)
        upload_targets.append((file, _resolve_new_child(root, parent, file_name)))

    completed_targets: list[Path] = []
    try:
        for file, target in upload_targets:
            await _write_workspace_upload(file, target)
            completed_targets.append(target)
    except HTTPException:
        for target in completed_targets:
            with contextlib.suppress(OSError):
                await asyncio.to_thread(target.unlink)
        raise

    await invalidate_workspace_mention_cache(str(current_user.uid))
    return {"success": True, "entries": [_entry_for_path(root, target) for _file, target in upload_targets]}


async def download_workspace_file(
    *, path: str, current_user: User, thread_titles: dict[str, str] | None = None
) -> StreamingResponse | FileResponse:
    target = resolve_workspace_file_path(path=path, current_user=current_user, thread_titles=thread_titles)
    if not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    file_name = target.name or "download"
    media_type = detect_media_type(file_name)
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(file_name)}"}
    if target.stat().st_size > 1024 * 1024 * 16:
        return FileResponse(path=target, media_type=media_type, headers=headers)

    content = await asyncio.to_thread(target.read_bytes)
    return StreamingResponse(io.BytesIO(content), media_type=media_type, headers=headers)


async def build_owned_thread_titles(db: AsyncSession, uid: str) -> dict[str, str]:
    """查询用户全部 active 对话，返回网页历史文件映射使用的标题。"""
    repo = ConversationRepository(db)
    conversations = await repo.list_active_conversations_for_user(str(uid))
    thread_titles = {}
    for conversation in conversations:
        try:
            thread_id = validate_thread_id(conversation.thread_id)
        except ValueError:
            logger.warning(f"跳过无法映射到文件系统的历史对话 thread_id: {conversation.thread_id}")
            continue
        created_date = conversation.created_at.strftime("%Y-%m-%d")
        title = (conversation.title or "").strip() or "未命名对话"
        thread_titles[thread_id] = f"{created_date}-{title}"
    return thread_titles


def is_workspace_chat_path(path: str | None) -> bool:
    """判断网页工作区路径是否属于历史对话虚拟命名空间。"""
    return _chat_path_parts(path) is not None


def workspace_path_uses_chat_mapping(path: str | None) -> bool:
    """判断工作区列表或文件请求是否需要加载用户对话白名单。"""
    normalized = _normalize_workspace_path(path).as_posix().rstrip("/") or "/"
    return normalized == f"/{WORKSPACE_AGENTS_DIR_NAME}" or is_workspace_chat_path(path)


def _workspace_root(user: User) -> Path:
    try:
        user_data_root = global_user_data_dir(str(user.uid)).resolve()
        root = user_data_root / WORKSPACE_DIR_NAME
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc
    if root.is_symlink():
        raise HTTPException(status_code=403, detail="Access denied")
    root.mkdir(parents=True, exist_ok=True)
    resolved_root = root.resolve()
    try:
        ensure_within_root(resolved_root, user_data_root, error_message="Access denied")
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc
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
    target = (root.joinpath(*relative_parts) if relative_parts else root).resolve(strict=False)
    try:
        ensure_within_root(target, root, error_message="Access denied")
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc
    return target


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
        ensure_within_root(target.resolve(strict=False), root, error_message="Access denied")
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc
    if target.exists():
        raise HTTPException(status_code=400, detail="同名文件或文件夹已存在")
    return target


def _validate_child_name(name: str, *, field_name: str) -> str:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise HTTPException(status_code=422, detail=f"{field_name} 不能为空")
    if clean_name in {".", ".."} or "/" in clean_name or "\\" in clean_name:
        raise HTTPException(status_code=422, detail=f"{field_name} 不能包含路径分隔符")
    if PurePosixPath(clean_name).name != clean_name:
        raise HTTPException(status_code=422, detail=f"{field_name} 不能包含路径分隔符")
    return clean_name


def _entry_for_path(root: Path, path: Path) -> dict:
    stat = path.stat()
    is_dir = path.is_dir()
    relative = path.relative_to(root).as_posix()
    display_path = f"/{relative}" if relative else "/"
    if is_dir and display_path != "/" and not display_path.endswith("/"):
        display_path = f"{display_path}/"
    virtual_path = VIRTUAL_PATH_WORKSPACE if display_path == "/" else f"{VIRTUAL_PATH_WORKSPACE}{display_path}"
    entry = {
        "path": display_path,
        "virtual_path": virtual_path,
        "name": path.name or "工作区",
        "is_dir": is_dir,
        "size": 0 if is_dir else stat.st_size,
        "modified_at": utc_isoformat_from_timestamp(stat.st_mtime) or "",
    }
    return entry


def _sort_entries(entries: list[dict]) -> list[dict]:
    return sorted(entries, key=lambda item: (not bool(item.get("is_dir")), str(item.get("name") or "").lower()))


def _sort_chat_entries(entries: list[dict]) -> list[dict]:
    return sorted(entries, key=lambda item: str(item.get("title") or item.get("name") or "").lower(), reverse=True)


def _list_directory(
    root: Path,
    target: Path,
    *,
    recursive: bool = False,
    files_only: bool = False,
) -> list[dict]:
    children = list(target.iterdir())
    entries = [_entry_for_path(root, child) for child in children if not files_only or child.is_file()]
    if recursive:
        for child in children:
            if child.is_dir() and not child.is_symlink():
                entries.extend(_list_directory(root, child, recursive=True, files_only=files_only))
    return _sort_entries(entries)


def _chat_path_parts(path: str | None) -> tuple[str, ...] | None:
    parts = tuple(part for part in _normalize_workspace_path(path).parts if part not in {"/", ""})
    prefix = (WORKSPACE_AGENTS_DIR_NAME, WORKSPACE_CHATS_DIR_NAME)
    if parts[:2] != prefix:
        return None
    return parts[2:]


def _resolve_chat_path(path: str | None, thread_titles: dict[str, str] | None) -> tuple[Path | None, str]:
    """将网页工作区的虚拟 chats 路径解析到对应 thread 文件目录。"""
    parts = _chat_path_parts(path)
    if parts is None:
        raise HTTPException(status_code=400, detail="当前路径不是历史对话路径")
    if not parts:
        return None, "/agents/chats"

    thread_id = parts[0]
    if thread_id not in (thread_titles or {}):
        raise HTTPException(status_code=403, detail="Access denied")
    if len(parts) == 1:
        return None, f"/agents/chats/{thread_id}"

    namespace = parts[1]
    if len(parts) > 2 and parts[2] in _CHAT_INTERMEDIATE_DIR_NAMES:
        raise HTTPException(status_code=404, detail="历史对话文件不存在")
    if namespace == UPLOADS_DIR_NAME:
        base_dir = sandbox_uploads_dir(thread_id).resolve(strict=False)
    elif namespace == OUTPUTS_DIR_NAME:
        base_dir = sandbox_outputs_dir(thread_id).resolve(strict=False)
    else:
        raise HTTPException(status_code=404, detail="历史对话目录不存在")

    target = base_dir.joinpath(*parts[2:]).resolve(strict=False)
    try:
        ensure_within_root(target, base_dir, error_message="Access denied")
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc
    return target, f"/agents/chats/{'/'.join(parts)}"


def _virtual_entry(path: str, *, name: str, is_dir: bool, title: str | None = None, source: Path | None = None) -> dict:
    display_path = f"{path.rstrip('/')}/" if is_dir else path
    stat = source.stat() if source and source.exists() else None
    entry = {
        "path": display_path,
        "virtual_path": f"{VIRTUAL_PATH_WORKSPACE}{display_path}",
        "name": name,
        "is_dir": is_dir,
        "size": 0 if is_dir or stat is None else stat.st_size,
        "modified_at": utc_isoformat_from_timestamp(stat.st_mtime) if stat else "",
        "readonly": True,
    }
    if title:
        entry["title"] = title
    return entry


def _is_chat_intermediate_path(path: Path, namespace_root: Path) -> bool:
    try:
        relative = path.resolve(strict=False).relative_to(namespace_root.resolve(strict=False))
    except ValueError:
        return True
    return bool(relative.parts and relative.parts[0] in _CHAT_INTERMEDIATE_DIR_NAMES)


def _directory_has_visible_entries(directory: Path) -> bool:
    if not directory.is_dir():
        return False
    root = directory.resolve(strict=False)
    for child in directory.iterdir():
        if _is_chat_intermediate_path(child, directory):
            continue
        try:
            ensure_within_root(child.resolve(strict=False), root, error_message="Access denied")
        except ValueError:
            continue
        return True
    return False


def _nonempty_chat_namespaces(thread_id: str) -> list[tuple[str, Path]]:
    return [
        (namespace, directory)
        for namespace, directory in (
            (UPLOADS_DIR_NAME, sandbox_uploads_dir(thread_id)),
            (OUTPUTS_DIR_NAME, sandbox_outputs_dir(thread_id)),
        )
        if _directory_has_visible_entries(directory)
    ]


def _list_chat_directory(
    path: str,
    *,
    thread_titles: dict[str, str],
    recursive: bool,
    files_only: bool,
) -> list[dict]:
    parts = _chat_path_parts(path)
    if parts is None:
        return []
    if not parts:
        entries: list[dict] = []
        for thread_id, title in thread_titles.items():
            if not _nonempty_chat_namespaces(thread_id):
                continue
            thread_path = f"/agents/chats/{thread_id}"
            if not files_only:
                entries.append(_virtual_entry(thread_path, name=thread_id, title=title, is_dir=True))
            if recursive:
                entries.extend(
                    _list_chat_directory(
                        thread_path,
                        thread_titles=thread_titles,
                        recursive=True,
                        files_only=files_only,
                    )
                )
        return _sort_chat_entries(entries)
    if len(parts) == 1:
        thread_id = parts[0]
        if thread_id not in thread_titles:
            raise HTTPException(status_code=403, detail="Access denied")
        entries = []
        for namespace, directory in _nonempty_chat_namespaces(thread_id):
            namespace_path = f"/agents/chats/{thread_id}/{namespace}"
            if not files_only:
                entries.append(_virtual_entry(namespace_path, name=namespace, is_dir=True, source=directory))
            if recursive:
                entries.extend(
                    _list_chat_directory(
                        namespace_path,
                        thread_titles=thread_titles,
                        recursive=True,
                        files_only=files_only,
                    )
                )
        return _sort_entries(entries)

    target, display_root = _resolve_chat_path(path, thread_titles)
    if target is None or not target.exists():
        return []
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="当前路径不是目录")

    entries: list[dict] = []
    namespace_root = target
    if len(parts) > 2:
        namespace_root = (
            sandbox_uploads_dir(parts[0]) if parts[1] == UPLOADS_DIR_NAME else sandbox_outputs_dir(parts[0])
        )
        namespace_root = namespace_root.resolve(strict=False)
    for child in target.iterdir():
        if _is_chat_intermediate_path(child, namespace_root):
            continue
        resolved_child = child.resolve(strict=False)
        try:
            ensure_within_root(resolved_child, target, error_message="Access denied")
        except ValueError:
            continue
        if not files_only or resolved_child.is_file():
            entries.append(
                _virtual_entry(
                    f"{display_root}/{child.name}",
                    name=child.name,
                    is_dir=resolved_child.is_dir(),
                    source=resolved_child,
                )
            )
        if recursive and resolved_child.is_dir() and not child.is_symlink():
            entries.extend(
                _list_chat_directory(
                    f"{display_root}/{child.name}",
                    thread_titles=thread_titles,
                    recursive=True,
                    files_only=files_only,
                )
            )
    return _sort_entries(entries)


def _preview_binary_response(*, filename: str, content: bytes, media_type: str, preview_type: str) -> StreamingResponse:
    headers = {
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
        "X-Yuxi-Preview-Type": preview_type,
        "X-Yuxi-Preview-Filename": quote(filename),
    }
    return StreamingResponse(io.BytesIO(content), media_type=media_type, headers=headers)


async def _write_workspace_upload(file: UploadFile, target: Path) -> None:
    created_file = False
    upload_completed = False

    try:
        async with aiofiles.open(target, "xb") as buffer:
            created_file = True
            await write_upload_to_buffer(
                file,
                buffer,
                max_size_bytes=MAX_WORKSPACE_UPLOAD_SIZE_BYTES,
                too_large_message="文件过大，当前仅支持 100 MB 以内的文件",
            )
        upload_completed = True
    except FileExistsError as exc:
        raise HTTPException(status_code=400, detail="同名文件或文件夹已存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if created_file and not upload_completed and target.exists():
            with contextlib.suppress(OSError):
                await asyncio.to_thread(target.unlink)


async def _convert_workspace_office_to_pdf(user: User, target: Path, file_name: str) -> bytes:
    user_data_root = global_user_data_dir(str(user.uid)).resolve()
    cache_dir = user_data_root / ".office_preview_cache"
    stat = await asyncio.to_thread(target.stat)
    digest = hashlib.sha256(str(target).encode("utf-8")).hexdigest()
    cache_path = cache_dir / f"{digest}-{stat.st_mtime_ns}-{stat.st_size}.pdf"

    cached = await asyncio.to_thread(lambda: cache_path.read_bytes() if cache_path.exists() else None)
    if cached is not None:
        return cached

    content = await asyncio.to_thread(target.read_bytes)
    try:
        pdf_content = await convert_office_to_pdf(file_name, content)
    except OfficePreviewConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await asyncio.to_thread(_store_office_pdf_cache, cache_dir, digest, cache_path, pdf_content)
    return pdf_content


def _store_office_pdf_cache(cache_dir: Path, digest: str, cache_path: Path, pdf_content: bytes) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    for stale in cache_dir.glob(f"{digest}-*.pdf"):
        if stale != cache_path:
            stale.unlink(missing_ok=True)
    cache_path.write_bytes(pdf_content)
