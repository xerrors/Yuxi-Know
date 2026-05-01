from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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
