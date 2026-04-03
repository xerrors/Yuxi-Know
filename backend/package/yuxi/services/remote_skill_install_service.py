from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession
from yuxi.services.skill_service import import_skill_dir, is_valid_skill_slug

if TYPE_CHECKING:
    from yuxi.storage.postgres.models_business import Skill

ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
CONTROL_SEQUENCE_RE = re.compile(r"\x1B\][^\x07]*(?:\x07|\x1B\\)|\x1B[\(\)][A-Za-z0-9]")
CLI_TIMEOUT_SECONDS = 300


def _normalize_source(source: str) -> str:
    value = str(source or "").strip()
    if not value:
        raise ValueError("source 不能为空")
    if any(ch in value for ch in ("\n", "\r", "\x00")):
        raise ValueError("source 包含非法字符")
    return value


def _normalize_skill_name(skill: str) -> str:
    value = str(skill or "").strip()
    if not is_valid_skill_slug(value):
        raise ValueError("skill 名称不合法")
    return value


def _clean_cli_output(output: str) -> list[str]:
    cleaned = ANSI_ESCAPE_RE.sub("", output or "")
    cleaned = CONTROL_SEQUENCE_RE.sub("", cleaned)
    cleaned = cleaned.replace("\r", "\n")
    normalized_lines: list[str] = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        stripped = re.sub(r"^[│┌└◇◒◐◓◑■●]+\s*", "", stripped)
        normalized_lines.append(stripped.strip())
    return normalized_lines


def _parse_available_skills(output: str) -> list[dict[str, str]]:
    lines = _clean_cli_output(output)
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    collecting = False

    for idx, line in enumerate(lines):
        if not collecting:
            if "Available Skills" in line:
                collecting = True
            continue

        if not line:
            continue
        if "Use --skill " in line:
            break
        if not is_valid_skill_slug(line):
            continue
        if line in seen:
            continue

        description = ""
        next_index = idx + 1
        while next_index < len(lines):
            next_line = lines[next_index]
            next_index += 1
            if not next_line:
                continue
            if "Use --skill " in next_line:
                break
            if is_valid_skill_slug(next_line):
                break
            if next_line and next_line[0].isalpha():
                description = next_line
            else:
                continue
            break

        seen.add(line)
        items.append({"name": line, "description": description})

    return items


async def _run_skills_cli(
    args: list[str],
    *,
    env: dict[str, str],
    cwd: str,
) -> str:
    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=CLI_TIMEOUT_SECONDS)
    except TimeoutError:
        process.kill()
        await process.communicate()
        raise ValueError("skills CLI 执行超时") from None

    output = (stdout or b"").decode("utf-8", errors="replace")
    error_output = (stderr or b"").decode("utf-8", errors="replace")
    combined = "\n".join(part for part in [output.strip(), error_output.strip()] if part)
    if process.returncode != 0:
        cleaned_lines = _clean_cli_output(combined)
        error_msg = "\n".join(line for line in cleaned_lines if line)[:500]
        raise ValueError(error_msg or "skills CLI 执行失败")
    return combined


def _create_isolated_workdir() -> tuple[str, dict[str, str], str]:
    temp_home = tempfile.mkdtemp(prefix=".remote-skills-")
    env = os.environ.copy()
    env["HOME"] = temp_home
    workdir = str(Path(temp_home) / "workspace")
    Path(workdir).mkdir(parents=True, exist_ok=True)
    return temp_home, env, workdir


async def list_remote_skills(source: str) -> list[dict[str, str]]:
    normalized_source = _normalize_source(source)

    temp_home, env, workdir = _create_isolated_workdir()
    try:
        output = await _run_skills_cli(
            ["npx", "-y", "skills", "add", normalized_source, "--list"],
            env=env,
            cwd=workdir,
        )
    finally:
        shutil.rmtree(temp_home, ignore_errors=True)

    skills = _parse_available_skills(output)
    if not skills:
        raise ValueError("未发现可安装的 skills")
    return skills


async def install_remote_skill(
    db: AsyncSession,
    *,
    source: str,
    skill: str,
    created_by: str | None,
) -> Skill:
    normalized_source = _normalize_source(source)
    normalized_skill = _normalize_skill_name(skill)

    temp_home, env, workdir = _create_isolated_workdir()
    try:
        available_skills = _parse_available_skills(
            await _run_skills_cli(
                ["npx", "-y", "skills", "add", normalized_source, "--list"],
                env=env,
                cwd=workdir,
            )
        )
        available_names = {item["name"] for item in available_skills}
        if normalized_skill not in available_names:
            raise ValueError(f"远程仓库中不存在 skill: {normalized_skill}")

        await _run_skills_cli(
            [
                "npx",
                "-y",
                "skills",
                "add",
                normalized_source,
                "--skill",
                normalized_skill,
                "-g",
                "-y",
                "--copy",
            ],
            env=env,
            cwd=workdir,
        )

        base_dir = Path(temp_home).resolve()
        skills_dir = base_dir / ".agents" / "skills"
        # Scan for the installed skill directory rather than constructing the path
        # from user input, to avoid path traversal concerns
        installed_dir = None
        if skills_dir.is_dir():
            for candidate in skills_dir.iterdir():
                if candidate.name == normalized_skill and candidate.is_dir():
                    installed_dir = candidate
                    break
        if installed_dir is None:
            raise ValueError("skills CLI 未生成预期的技能目录")

        return await import_skill_dir(
            db,
            source_dir=installed_dir,
            created_by=created_by,
        )
    finally:
        shutil.rmtree(temp_home, ignore_errors=True)
