from __future__ import annotations

from pathlib import Path

import pytest

from yuxi.services import remote_skill_install_service as svc


def test_parse_available_skills_from_cli_output() -> None:
    output = """
    \x1b[38;5;250m███████╗\x1b[0m
    ◇  Available Skills
    Claude Api

        claude-api

          Build apps with the Claude API.

    Example Skills

        frontend-design

          Create distinctive frontend interfaces.

    └  Use --skill <name> to install specific skills
    """

    skills = svc._parse_available_skills(output)

    assert skills == [
        {"name": "claude-api", "description": "Build apps with the Claude API."},
        {"name": "frontend-design", "description": "Create distinctive frontend interfaces."},
    ]


@pytest.mark.asyncio
async def test_list_remote_skills_uses_isolated_home(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    async def fake_run_skills_cli(args: list[str], *, env: dict[str, str], cwd: str) -> str:
        captured["args"] = args
        captured["home"] = env["HOME"]
        captured["cwd"] = cwd
        return """
        ◇  Available Skills

            frontend-design

              Create distinctive frontend interfaces.

        └  Use --skill <name> to install specific skills
        """

    monkeypatch.setattr(svc, "_run_skills_cli", fake_run_skills_cli)

    items = await svc.list_remote_skills("anthropics/skills")

    assert items == [{"name": "frontend-design", "description": "Create distinctive frontend interfaces."}]
    assert captured["args"] == ["npx", "-y", "skills", "add", "anthropics/skills", "--list"]
    assert str(captured["cwd"]).startswith(str(captured["home"]))


@pytest.mark.asyncio
async def test_install_remote_skill_imports_from_cli_output_dir(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[list[str], str]] = []

    async def fake_run_skills_cli(args: list[str], *, env: dict[str, str], cwd: str) -> str:
        calls.append((args, env["HOME"]))
        home = Path(env["HOME"])
        if "--list" in args:
            return """
            ◇  Available Skills

                frontend-design

                  Create distinctive frontend interfaces.

            └  Use --skill <name> to install specific skills
            """
        skill_dir = home / ".agents" / "skills" / "frontend-design"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: frontend-design\ndescription: demo\n---\n# Demo\n",
            encoding="utf-8",
        )
        return "installed"

    captured: dict[str, object] = {}

    async def fake_import_skill_dir(_db, *, source_dir, created_by):
        captured["source_dir"] = Path(source_dir)
        captured["created_by"] = created_by
        return {"slug": "frontend-design"}

    monkeypatch.setattr(svc, "_run_skills_cli", fake_run_skills_cli)
    monkeypatch.setattr(svc, "import_skill_dir", fake_import_skill_dir)

    item = await svc.install_remote_skill(
        None,
        source="anthropics/skills",
        skill="frontend-design",
        created_by="root",
    )

    assert item == {"slug": "frontend-design"}
    assert calls[0][0] == ["npx", "-y", "skills", "add", "anthropics/skills", "--list"]
    assert calls[1][0] == [
        "npx",
        "-y",
        "skills",
        "add",
        "anthropics/skills",
        "--skill",
        "frontend-design",
        "-g",
        "-y",
        "--copy",
    ]
    assert captured["source_dir"] == Path(calls[1][1]) / ".agents" / "skills" / "frontend-design"
    assert captured["created_by"] == "root"


@pytest.mark.asyncio
async def test_install_remote_skill_rejects_missing_remote_skill(monkeypatch: pytest.MonkeyPatch):
    async def fake_run_skills_cli(args: list[str], *, env: dict[str, str], cwd: str) -> str:
        return """
        ◇  Available Skills

            other-skill

              Description

        └  Use --skill <name> to install specific skills
        """

    monkeypatch.setattr(svc, "_run_skills_cli", fake_run_skills_cli)

    with pytest.raises(ValueError, match="不存在 skill"):
        await svc.install_remote_skill(
            None,
            source="anthropics/skills",
            skill="frontend-design",
            created_by="root",
        )
