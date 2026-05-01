from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from yuxi.agents.backends.sandbox import paths as workspace_paths
from yuxi.services import workspace_service as svc


def test_workspace_root_creates_default_agents_prompt_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(workspace_paths.conf, "save_dir", str(tmp_path))

    root = svc._workspace_root(SimpleNamespace(id="user-1"))

    agents_file = root / "agents" / "AGENTS.md"
    assert agents_file.is_file()
    assert agents_file.read_text(encoding="utf-8") == ""


def test_ensure_thread_dirs_creates_default_agents_prompt_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(workspace_paths.conf, "save_dir", str(tmp_path))

    workspace_paths.ensure_thread_dirs("thread-1", "user-1")

    agents_file = tmp_path / "threads" / "shared" / "user-1" / "workspace" / "agents" / "AGENTS.md"
    assert agents_file.is_file()
    assert agents_file.read_text(encoding="utf-8") == ""


def test_workspace_root_keeps_existing_agents_prompt_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(workspace_paths.conf, "save_dir", str(tmp_path))
    agents_dir = tmp_path / "threads" / "shared" / "user-1" / "workspace" / "agents"
    agents_dir.mkdir(parents=True)
    agents_file = agents_dir / "AGENTS.md"
    agents_file.write_text("保留已有内容", encoding="utf-8")

    root = svc._workspace_root(SimpleNamespace(id="user-1"))

    assert root == tmp_path / "threads" / "shared" / "user-1" / "workspace"
    assert agents_file.read_text(encoding="utf-8") == "保留已有内容"


def test_workspace_root_rejects_symlink_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(workspace_paths.conf, "save_dir", str(tmp_path))
    user_root = tmp_path / "threads" / "shared" / "user-1"
    outside_root = tmp_path / "outside"
    user_root.mkdir(parents=True)
    outside_root.mkdir()
    (user_root / "workspace").symlink_to(outside_root, target_is_directory=True)

    with pytest.raises(HTTPException) as exc_info:
        svc._workspace_root(SimpleNamespace(id="user-1"))

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_read_workspace_file_content_returns_unsupported_for_non_utf8_text(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(workspace_paths.conf, "save_dir", str(tmp_path))
    user = SimpleNamespace(id="user-1")
    root = svc._workspace_root(user)
    target = root / "bad.txt"
    target.write_bytes(b"\xff\xfe\x00")

    result = await svc.read_workspace_file_content(path="/bad.txt", current_user=user)

    assert result["content"] is None
    assert result["preview_type"] == "unsupported"
    assert result["supported"] is False


@pytest.mark.asyncio
async def test_write_workspace_file_content_updates_markdown_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(workspace_paths.conf, "save_dir", str(tmp_path))
    user = SimpleNamespace(id="user-1")
    root = svc._workspace_root(user)
    target = root / "note.md"
    target.write_text("旧内容", encoding="utf-8")

    result = await svc.write_workspace_file_content(path="/note.md", content="# 新内容", current_user=user)

    assert result["success"] is True
    assert result["path"] == "/note.md"
    assert result["entry"]["path"] == "/note.md"
    assert target.read_text(encoding="utf-8") == "# 新内容"


@pytest.mark.asyncio
async def test_write_workspace_file_content_updates_txt_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(workspace_paths.conf, "save_dir", str(tmp_path))
    user = SimpleNamespace(id="user-1")
    root = svc._workspace_root(user)
    target = root / "note.txt"
    target.write_text("old", encoding="utf-8")

    await svc.write_workspace_file_content(path="/note.txt", content="new", current_user=user)

    assert target.read_text(encoding="utf-8") == "new"


@pytest.mark.asyncio
async def test_write_workspace_file_content_rejects_unsupported_suffix(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(workspace_paths.conf, "save_dir", str(tmp_path))
    user = SimpleNamespace(id="user-1")
    root = svc._workspace_root(user)
    target = root / "script.py"
    target.write_text("print('hello')", encoding="utf-8")

    with pytest.raises(HTTPException) as exc_info:
        await svc.write_workspace_file_content(path="/script.py", content="print('bye')", current_user=user)

    assert exc_info.value.status_code == 400
    assert target.read_text(encoding="utf-8") == "print('hello')"


@pytest.mark.asyncio
async def test_write_workspace_file_content_rejects_directory_and_missing_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(workspace_paths.conf, "save_dir", str(tmp_path))
    user = SimpleNamespace(id="user-1")
    svc._workspace_root(user)

    with pytest.raises(HTTPException) as directory_error:
        await svc.write_workspace_file_content(path="/agents/", content="x", current_user=user)
    with pytest.raises(HTTPException) as missing_error:
        await svc.write_workspace_file_content(path="/missing.md", content="x", current_user=user)

    assert directory_error.value.status_code == 400
    assert missing_error.value.status_code == 404


@pytest.mark.asyncio
async def test_write_workspace_file_content_blocks_path_traversal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(workspace_paths.conf, "save_dir", str(tmp_path))

    with pytest.raises(HTTPException) as exc_info:
        await svc.write_workspace_file_content(
            path="/../outside.md",
            content="x",
            current_user=SimpleNamespace(id="user-1"),
        )

    assert exc_info.value.status_code == 403
