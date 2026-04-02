from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from yuxi.services import thread_files_service as svc


@pytest.mark.asyncio
async def test_resolve_thread_artifact_view_blocks_symlink_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    thread_root = tmp_path / "threads" / "thread-1" / "user-data"
    uploads_dir = thread_root / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("secret", encoding="utf-8")
    (uploads_dir / "escape.txt").symlink_to(outside_file)

    class _Conversation:
        user_id = "user-1"

    async def _fake_require_user_conversation(_repo, _thread_id: str, _current_user_id: str):
        return _Conversation()

    monkeypatch.setattr(svc, "require_user_conversation", _fake_require_user_conversation)
    monkeypatch.setattr(svc, "ensure_thread_dirs", lambda _thread_id, _user_id: None)
    monkeypatch.setattr(
        svc,
        "sandbox_workspace_dir",
        lambda _thread_id, _user_id: tmp_path / "shared" / _user_id / "workspace",
    )
    monkeypatch.setattr(svc, "sandbox_uploads_dir", lambda _thread_id: uploads_dir)
    monkeypatch.setattr(svc, "sandbox_outputs_dir", lambda _thread_id: thread_root / "outputs")
    monkeypatch.setattr(svc, "resolve_virtual_path", lambda _thread_id, _path, *, user_id: uploads_dir / "escape.txt")
    monkeypatch.setattr(svc, "ConversationRepository", lambda _db: object())

    with pytest.raises(HTTPException, match="access denied"):
        await svc.resolve_thread_artifact_view(
            thread_id="thread-1",
            current_user_id="user-1",
            db=None,
            path="/home/gem/user-data/uploads/escape.txt",
        )
