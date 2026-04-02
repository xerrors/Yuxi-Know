from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from yuxi import config as conf
from yuxi.agents.backends.sandbox import (
    ensure_thread_dirs,
    resolve_virtual_path,
    sandbox_outputs_dir,
    sandbox_uploads_dir,
    sandbox_user_data_dir,
    sandbox_workspace_dir,
    virtual_path_for_thread_file,
)
from yuxi.repositories.conversation_repository import ConversationRepository
from yuxi.services.conversation_service import require_user_conversation
from yuxi.utils.datetime_utils import utc_isoformat_from_timestamp


def _get_virtual_root() -> str:
    """Return the virtual root exposed by the thread-files API."""
    prefix = str(getattr(conf, "sandbox_virtual_path_prefix", "/home/gem/user-data") or "/home/gem/user-data")
    return "/" + prefix.strip("/")


async def list_thread_files_view(
    *,
    thread_id: str,
    current_user_id: str,
    db,
    path: str | None = None,
    recursive: bool = False,
) -> dict:
    conv_repo = ConversationRepository(db)
    conversation = await require_user_conversation(conv_repo, thread_id, str(current_user_id))
    user_id = str(conversation.user_id)

    ensure_thread_dirs(thread_id, user_id)
    virtual_path = path or _get_virtual_root()
    try:
        actual_path = resolve_virtual_path(thread_id, virtual_path, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not actual_path.exists():
        return {"path": virtual_path, "files": []}
    if not actual_path.is_dir():
        raise HTTPException(status_code=400, detail="path must be a directory")

    if recursive:
        if virtual_path.rstrip("/") == _get_virtual_root():
            return _list_user_data_root_entries(thread_id, user_id, virtual_path, recursive=True)
        return _list_files_recursive(thread_id, user_id, actual_path, virtual_path)

    if virtual_path.rstrip("/") == _get_virtual_root():
        return _list_user_data_root_entries(thread_id, user_id, virtual_path)

    entries: list[dict[str, Any]] = []
    for child in sorted(actual_path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        stat = child.stat()
        child_virtual_path = virtual_path_for_thread_file(thread_id, child, user_id=user_id)
        entries.append(
            {
                "path": child_virtual_path,
                "name": child.name,
                "is_dir": child.is_dir(),
                "size": stat.st_size if child.is_file() else 0,
                "modified_at": utc_isoformat_from_timestamp(stat.st_mtime),
                "artifact_url": None
                if child.is_dir()
                else f"/api/chat/thread/{thread_id}/artifacts/{child_virtual_path.lstrip('/')}",
            }
        )

    return {"path": virtual_path, "files": entries}


def _list_user_data_root_entries(thread_id: str, user_id: str, virtual_path: str, recursive: bool = False) -> dict:
    """List the thread root and inject the user workspace entry if needed."""
    entries: list[dict[str, Any]] = []
    thread_root = sandbox_user_data_dir(thread_id)
    for child in sorted(thread_root.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        stat = child.stat()
        child_virtual_path = virtual_path_for_thread_file(thread_id, child, user_id=user_id)
        if child.is_dir() and not child_virtual_path.endswith("/"):
            child_virtual_path = f"{child_virtual_path}/"
        entries.append(
            {
                "path": child_virtual_path,
                "name": child.name,
                "is_dir": child.is_dir(),
                "size": stat.st_size if child.is_file() else 0,
                "modified_at": utc_isoformat_from_timestamp(stat.st_mtime),
                "artifact_url": None
                if child.is_dir()
                else f"/api/chat/thread/{thread_id}/artifacts/{child_virtual_path.lstrip('/')}",
            }
        )
        if recursive and child.is_dir():
            nested = _list_files_recursive(thread_id, user_id, child, child_virtual_path)
            entries.extend(nested["files"])

    workspace_dir = sandbox_workspace_dir(thread_id, user_id)
    workspace_virtual_path = virtual_path_for_thread_file(thread_id, workspace_dir, user_id=user_id)
    if workspace_virtual_path.rstrip("/") not in {str(entry["path"]).rstrip("/") for entry in entries}:
        # workspace lives outside the per-thread root, so expose it as a top-level entry.
        stat = workspace_dir.stat()
        if not workspace_virtual_path.endswith("/"):
            workspace_virtual_path = f"{workspace_virtual_path}/"
        entries.append(
            {
                "path": workspace_virtual_path,
                "name": workspace_dir.name,
                "is_dir": True,
                "size": 0,
                "modified_at": utc_isoformat_from_timestamp(stat.st_mtime),
                "artifact_url": None,
            }
        )
        if recursive:
            nested = _list_files_recursive(thread_id, user_id, workspace_dir, workspace_virtual_path)
            entries.extend(nested["files"])
    return {"path": virtual_path, "files": entries}


def _list_files_recursive(thread_id: str, user_id: str, actual_path: Path, virtual_path: str) -> dict:
    """Recursively scan a directory while preserving viewer virtual paths."""
    entries: list[dict[str, Any]] = []

    def _scan_dir(base_actual_path: Path, base_virtual_path: str):
        try:
            for child in sorted(base_actual_path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
                stat = child.stat()
                child_virtual_path = virtual_path_for_thread_file(thread_id, child, user_id=user_id)
                entries.append(
                    {
                        "path": child_virtual_path,
                        "name": child.name,
                        "is_dir": child.is_dir(),
                        "size": stat.st_size if child.is_file() else 0,
                        "modified_at": utc_isoformat_from_timestamp(stat.st_mtime),
                        "artifact_url": None
                        if child.is_dir()
                        else f"/api/chat/thread/{thread_id}/artifacts/{child_virtual_path.lstrip('/')}",
                    }
                )
                if child.is_dir():
                    _scan_dir(child, child_virtual_path)
        except PermissionError:
            pass

    _scan_dir(actual_path, virtual_path)
    return {"path": virtual_path, "files": entries}


async def read_thread_file_content_view(
    *,
    thread_id: str,
    current_user_id: str,
    db,
    path: str,
    offset: int = 0,
    limit: int = 2000,
) -> dict:
    conv_repo = ConversationRepository(db)
    conversation = await require_user_conversation(conv_repo, thread_id, str(current_user_id))
    user_id = str(conversation.user_id)

    try:
        actual_path = resolve_virtual_path(thread_id, path, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not actual_path.exists():
        raise HTTPException(status_code=404, detail="file not found")
    if not actual_path.is_file():
        raise HTTPException(status_code=400, detail="path must be a file")

    text = actual_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    start = max(0, int(offset))
    count = min(max(1, int(limit)), 5000)
    selected = lines[start : start + count]

    return {
        "path": path,
        "content": selected,
        "offset": start,
        "limit": count,
        "total_lines": len(lines),
        "artifact_url": f"/api/chat/thread/{thread_id}/artifacts/{path.lstrip('/')}",
    }


async def resolve_thread_artifact_view(
    *,
    thread_id: str,
    current_user_id: str,
    db,
    path: str,
) -> Path:
    conv_repo = ConversationRepository(db)
    conversation = await require_user_conversation(conv_repo, thread_id, str(current_user_id))
    user_id = str(conversation.user_id)

    ensure_thread_dirs(thread_id, user_id)

    normalized = "/" + path.lstrip("/")
    try:
        actual_path = resolve_virtual_path(thread_id, normalized, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not actual_path.exists():
        raise HTTPException(status_code=404, detail="artifact not found")
    if not actual_path.is_file():
        raise HTTPException(status_code=400, detail="artifact path is not a file")

    resolved_path = actual_path.resolve()
    allowed_roots = (
        sandbox_workspace_dir(thread_id, user_id).resolve(),
        sandbox_uploads_dir(thread_id).resolve(),
        sandbox_outputs_dir(thread_id).resolve(),
    )
    if not any(_is_path_within(resolved_path, root) for root in allowed_roots):
        raise HTTPException(status_code=403, detail="access denied")

    return resolved_path


async def save_thread_artifact_to_workspace_view(
    *,
    thread_id: str,
    current_user_id: str,
    db,
    path: str,
) -> dict[str, str]:
    source_path = await resolve_thread_artifact_view(
        thread_id=thread_id,
        current_user_id=current_user_id,
        db=db,
        path=path,
    )

    conv_repo = ConversationRepository(db)
    conversation = await require_user_conversation(conv_repo, thread_id, str(current_user_id))
    user_id = str(conversation.user_id)
    target_dir = sandbox_workspace_dir(thread_id, user_id) / "saved_artifacts"
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = _next_available_artifact_path(target_dir, source_path.name)
    with source_path.open("rb") as src, target_path.open("wb") as dst:
        shutil.copyfileobj(src, dst)

    saved_virtual_path = virtual_path_for_thread_file(thread_id, target_path, user_id=user_id)
    return {
        "name": target_path.name,
        "source_path": "/" + path.lstrip("/"),
        "saved_path": saved_virtual_path,
        "saved_artifact_url": f"/api/chat/thread/{thread_id}/artifacts/{saved_virtual_path.lstrip('/')}",
    }


def _next_available_artifact_path(target_dir: Path, filename: str) -> Path:
    candidate = target_dir / filename
    if not candidate.exists():
        return candidate

    base_name = Path(filename).stem
    suffix = Path(filename).suffix
    index = 1
    while True:
        candidate = target_dir / f"{base_name} ({index}){suffix}"
        if not candidate.exists():
            return candidate

        index += 1
        if index >= 1000:
            # This is a safety check to prevent infinite loops in case of some unexpected issue with file naming.
            raise RuntimeError(f"Unable to find available filename for {filename} after 1000 attempts.")


def _is_path_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
