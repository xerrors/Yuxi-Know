from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from yuxi import config as conf
from yuxi.agents.backends.sandbox import (
    ensure_thread_dirs,
    resolve_virtual_path,
    sandbox_user_data_dir,
    virtual_path_for_thread_file,
)
from yuxi.repositories.conversation_repository import ConversationRepository
from yuxi.services.conversation_service import require_user_conversation


def _get_virtual_root() -> str:
    prefix = str(getattr(conf, "sandbox_virtual_path_prefix", "/home/gem/user-data") or "/home/gem/user-data")
    return "/" + prefix.strip("/")


def _to_iso8601(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()


async def list_thread_files_view(
    *,
    thread_id: str,
    current_user_id: str,
    db,
    path: str | None = None,
    recursive: bool = False,
) -> dict:
    conv_repo = ConversationRepository(db)
    await require_user_conversation(conv_repo, thread_id, str(current_user_id))

    ensure_thread_dirs(thread_id)
    virtual_path = path or _get_virtual_root()
    try:
        actual_path = resolve_virtual_path(thread_id, virtual_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not actual_path.exists():
        return {"path": virtual_path, "files": []}
    if not actual_path.is_dir():
        raise HTTPException(status_code=400, detail="path must be a directory")

    if recursive:
        return _list_files_recursive(thread_id, actual_path, virtual_path)

    entries: list[dict[str, Any]] = []
    for child in sorted(actual_path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        stat = child.stat()
        child_virtual_path = virtual_path_for_thread_file(thread_id, child)
        entries.append(
            {
                "path": child_virtual_path,
                "name": child.name,
                "is_dir": child.is_dir(),
                "size": stat.st_size if child.is_file() else 0,
                "modified_at": _to_iso8601(stat.st_mtime),
                "artifact_url": None
                if child.is_dir()
                else f"/api/chat/thread/{thread_id}/artifacts/{child_virtual_path.lstrip('/')}",
            }
        )

    return {"path": virtual_path, "files": entries}


def _list_files_recursive(thread_id: str, actual_path: Path, virtual_path: str) -> dict:
    entries: list[dict[str, Any]] = []

    def _scan_dir(base_actual_path: Path, base_virtual_path: str):
        try:
            for child in sorted(base_actual_path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
                stat = child.stat()
                child_virtual_path = virtual_path_for_thread_file(thread_id, child)
                entries.append(
                    {
                        "path": child_virtual_path,
                        "name": child.name,
                        "is_dir": child.is_dir(),
                        "size": stat.st_size if child.is_file() else 0,
                        "modified_at": _to_iso8601(stat.st_mtime),
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
    await require_user_conversation(conv_repo, thread_id, str(current_user_id))

    try:
        actual_path = resolve_virtual_path(thread_id, path)
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
    await require_user_conversation(conv_repo, thread_id, str(current_user_id))

    ensure_thread_dirs(thread_id)

    normalized = "/" + path.lstrip("/")
    try:
        actual_path = resolve_virtual_path(thread_id, normalized)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not actual_path.exists():
        raise HTTPException(status_code=404, detail="artifact not found")
    if not actual_path.is_file():
        raise HTTPException(status_code=400, detail="artifact path is not a file")

    # Additional guard to ensure path remains under thread root even if helper changes.
    thread_root = sandbox_user_data_dir(thread_id).resolve()
    try:
        actual_path.resolve().relative_to(thread_root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="access denied") from exc

    return actual_path
