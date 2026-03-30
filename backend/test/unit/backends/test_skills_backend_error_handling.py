from __future__ import annotations

from deepagents.backends import FilesystemBackend
import pytest

from yuxi.agents.backends.skills_backend import SelectedSkillsReadonlyBackend


def test_skills_backend_read_outside_root_returns_error_message(monkeypatch) -> None:
    def _fake_read(self, file_path: str, offset: int = 0, limit: int = 2000):
        raise ValueError(
            "Path:/app/package/yuxi/agents/skills/buildin/reporter "
            "outside root directory: /app/saves/skills"
        )

    monkeypatch.setattr(FilesystemBackend, "read", _fake_read)

    backend = SelectedSkillsReadonlyBackend(selected_slugs=["reporter"])
    with pytest.raises(ValueError, match="outside root directory"):
        backend.read("/reporter/SKILL.md")


def test_skills_backend_ls_info_outside_root_returns_empty(monkeypatch) -> None:
    def _fake_ls_info(self, path: str):
        raise ValueError("Path outside root directory")

    monkeypatch.setattr(FilesystemBackend, "ls_info", _fake_ls_info)

    backend = SelectedSkillsReadonlyBackend(selected_slugs=["reporter"])
    with pytest.raises(ValueError, match="outside root directory"):
        backend.ls_info("/reporter")
