from __future__ import annotations

import asyncio
import re
import shlex
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.agents.backends.sandbox import ProvisionerSandboxBackend
from yuxi.agents.backends.sandbox.download import download_sandbox_directory
from yuxi.agents.backends.sandbox.paths import sandbox_user_data_dir, sandbox_workspace_dir
from yuxi.agents.backends.sandbox.provider import get_sandbox_provider
from yuxi.agents.skills.service import import_skill_dir, is_valid_skill_slug
from yuxi.config.options import remote_skill_source_policy
from yuxi.utils.logging_config import logger

if TYPE_CHECKING:
    from yuxi.storage.postgres.models_business import Skill

ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
CONTROL_SEQUENCE_RE = re.compile(r"\x1B\][^\x07]*(?:\x07|\x1B\\)|\x1B[\(\)][A-Za-z0-9]")
CLI_TIMEOUT_SECONDS = 300
GITHUB_REPO_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?/(?!\.{1,2}$)[A-Za-z0-9_.-]+$")
GITHUB_HOST = "github.com"
INVALID_SOURCE_MESSAGE = "source 仅支持远程 Skill 来源白名单中的 HTTPS 地址"
REMOTE_SKILL_SANDBOX_ROOT = "/home/gem/user-data/outputs"


@dataclass(slots=True)
class RemoteSkillsBatchPreparation:
    temp_home: str | None
    results: list[dict]

    async def cleanup(self) -> None:
        if self.temp_home:
            await asyncio.to_thread(shutil.rmtree, self.temp_home, ignore_errors=True)


@dataclass(slots=True)
class _RemoteSkillSandbox:
    """在一次性 Sandbox 中执行不可信的远程 Skill CLI。"""

    thread_id: str
    home: str
    backend: ProvisionerSandboxBackend

    @classmethod
    def create(cls) -> _RemoteSkillSandbox:
        thread_id = f"remote-skill-{uuid.uuid4().hex}"
        home = f"{REMOTE_SKILL_SANDBOX_ROOT}/.{thread_id}"
        return cls(
            thread_id=thread_id,
            home=home,
            # 远程仓库不可信，不能接触全局或用户级 Sandbox 凭据。
            backend=ProvisionerSandboxBackend(thread_id=thread_id, uid=thread_id, inherit_env=False),
        )

    async def run(self, args: list[str]) -> str:
        """执行 Skills CLI，并返回原始命令输出。"""
        workspace = f"{self.home}/workspace"
        command = " && ".join(
            [
                f"mkdir -p {shlex.quote(workspace)}",
                f"cd {shlex.quote(workspace)}",
                f"HOME={shlex.quote(self.home)} {shlex.join(args)}",
            ]
        )
        result = await asyncio.to_thread(self.backend.execute, command, timeout=CLI_TIMEOUT_SECONDS)
        output = str(result.output or "")
        if result.exit_code != 0:
            cleaned_lines = _clean_cli_output(output)
            error_msg = "\n".join(line for line in cleaned_lines if line)[:500]
            raise ValueError(error_msg or "skills CLI 执行失败")
        return output

    async def download_skill(self, name: str, target_dir: Path) -> None:
        """将 Sandbox 内的一个 Skill 下载到宿主临时目录。"""
        remote_dir = f"{self.home}/.agents/skills/{name}"
        await asyncio.to_thread(
            download_sandbox_directory,
            self.backend,
            remote_dir,
            target_dir,
            empty_message="skills CLI 未生成预期的技能目录",
        )

    async def cleanup(self) -> None:
        """删除一次性 Sandbox 及其线程目录。"""
        try:
            await asyncio.to_thread(
                get_sandbox_provider().release,
                self.thread_id,
                uid=self.thread_id,
                clear_cache_on_delete_failure=True,
            )
        except Exception as exc:
            logger.error(f"销毁远程 Skill Sandbox 失败: {exc}")
            raise
        finally:
            thread_dir = sandbox_user_data_dir(self.thread_id).parent
            workspace_dir = sandbox_workspace_dir(self.thread_id, self.thread_id).parent
            await asyncio.to_thread(shutil.rmtree, thread_dir, ignore_errors=True)
            await asyncio.to_thread(shutil.rmtree, workspace_dir, ignore_errors=True)


def _normalize_source(source: str, allowed_hosts: list[str]) -> str:
    value = str(source or "").strip()
    if not value:
        raise ValueError("source 不能为空")
    if any(ch in value for ch in ("\n", "\r", "\x00")):
        raise ValueError("source 包含非法字符")

    allowed_hosts = {host.strip().lower().rstrip(".") for host in allowed_hosts}
    if GITHUB_REPO_PATTERN.fullmatch(value):
        if GITHUB_HOST not in allowed_hosts:
            raise ValueError(INVALID_SOURCE_MESSAGE)
        return f"https://{GITHUB_HOST}/{value}"

    parsed = urlparse(value)
    try:
        hostname = (parsed.hostname or "").rstrip(".").lower()
        port = parsed.port
    except ValueError:
        raise ValueError(INVALID_SOURCE_MESSAGE) from None

    if (
        parsed.scheme.lower() != "https"
        or not hostname
        or parsed.username
        or parsed.password
        or port not in (None, 443)
        or parsed.query
        or parsed.fragment
        or hostname not in allowed_hosts
    ):
        raise ValueError(INVALID_SOURCE_MESSAGE)

    path = parsed.path.rstrip("/") or "/"
    if hostname == GITHUB_HOST:
        repo_path = path.strip("/")
        if repo_path.endswith(".git"):
            repo_path = repo_path[:-4]
        if not GITHUB_REPO_PATTERN.fullmatch(repo_path):
            raise ValueError(INVALID_SOURCE_MESSAGE)
        return f"https://{GITHUB_HOST}/{repo_path}"

    return parsed._replace(scheme="https", netloc=hostname, path=path).geturl().rstrip("/")


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


async def list_remote_skills(source: str) -> list[dict[str, str]]:
    policy = await remote_skill_source_policy.get()
    normalized_source = _normalize_source(source, policy["allowed_hosts"])

    sandbox = _RemoteSkillSandbox.create()
    try:
        output = await sandbox.run(["npx", "-y", "skills", "add", normalized_source, "--list"])
    finally:
        await sandbox.cleanup()

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
    normalized_skill = _normalize_skill_name(skill)
    preparation = await prepare_remote_skills_batch(source=source, skills=[normalized_skill])
    try:
        result = preparation.results[0]
        if not result.get("success"):
            raise ValueError(result.get("error") or f"远程仓库中不存在 skill: {normalized_skill}")

        return await import_skill_dir(
            db,
            source_dir=result["source_dir"],
            created_by=created_by,
        )
    finally:
        await preparation.cleanup()


async def install_remote_skills_batch(
    db: AsyncSession,
    *,
    source: str,
    skills: list[str],
    created_by: str | None,
) -> list[dict]:
    """批量从同一个远程仓库安装多个 skills（仅一次克隆）。

    Args:
        db: 数据库会话。
        source: 远程 Skill 来源，如 ``owner/repo`` 或允许的 HTTPS URL。
        skills: 需要安装的 skill 名称列表。
        created_by: 操作者标识。

    Returns:
        每个 skill 的安装结果列表，顺序与请求一致: ``[{slug, success, error?}, ...]``
    """
    preparation = await prepare_remote_skills_batch(source=source, skills=skills)
    try:
        results = preparation.results
        for index, result in enumerate(results):
            if not result.get("success"):
                continue

            source_dir = result.get("source_dir")
            try:
                item = await import_skill_dir(
                    db,
                    source_dir=source_dir,
                    created_by=created_by,
                )
                results[index] = {"slug": item.slug, "success": True}
            except Exception as e:
                if hasattr(db, "rollback"):
                    await db.rollback()
                results[index] = {"slug": result["slug"], "success": False, "error": str(e)}

        return results
    finally:
        await preparation.cleanup()


async def prepare_remote_skills_batch(
    *,
    source: str,
    skills: list[str],
) -> RemoteSkillsBatchPreparation:
    """批量从远程仓库拉取 skill 目录，但不写数据库。"""
    policy = await remote_skill_source_policy.get()
    normalized_source = _normalize_source(source, policy["allowed_hosts"])
    if not skills:
        raise ValueError("skills 列表不能为空")

    # 预分配结果数组（按请求顺序），校验非法名并记录失败
    results: list[dict] = [{"slug": "", "success": False, "error": "unset"} for _ in range(len(skills))]
    normalized_skills: list[str] = []
    valid_indices: list[int] = []
    for i, skill in enumerate(skills):
        try:
            normalized_skills.append(_normalize_skill_name(skill))
            valid_indices.append(i)
        except ValueError as e:
            results[i] = {"slug": skill, "success": False, "error": str(e)}

    if not normalized_skills:
        return RemoteSkillsBatchPreparation(temp_home=None, results=results)

    sandbox = _RemoteSkillSandbox.create()
    temp_home: str | None = None
    keep_temp_home = False
    try:
        try:
            temp_home = tempfile.mkdtemp(prefix=".remote-skills-")
            skill_args: list[str] = []
            for name in normalized_skills:
                skill_args.extend(["--skill", name])

            cli_failed = False
            try:
                await sandbox.run(
                    [
                        "npx",
                        "-y",
                        "skills",
                        "add",
                        normalized_source,
                        *skill_args,
                        "-g",
                        "-y",
                        "--copy",
                    ]
                )
            except ValueError:
                # CLI 对不匹配的 skill 会退出码非零，但已安装的目录仍在
                cli_failed = True

            downloaded_dirs: dict[str, Path | None] = {}
            for original_index, name in zip(valid_indices, normalized_skills):
                installed_dir = Path(temp_home) / name
                if name not in downloaded_dirs:
                    try:
                        await sandbox.download_skill(name, installed_dir)
                        downloaded_dirs[name] = installed_dir
                    except ValueError:
                        downloaded_dirs[name] = None
                installed_dir = downloaded_dirs[name]
                if installed_dir is None:
                    error_msg = "CLI 安装失败" if cli_failed else "skills CLI 未生成预期的技能目录"
                    results[original_index] = {"slug": name, "success": False, "error": error_msg}
                    continue
                results[original_index] = {"slug": name, "success": True, "source_dir": installed_dir}

            preparation = RemoteSkillsBatchPreparation(temp_home=temp_home, results=results)
        finally:
            await sandbox.cleanup()

        keep_temp_home = True
        return preparation
    finally:
        if temp_home and not keep_temp_home:
            await asyncio.to_thread(shutil.rmtree, temp_home, ignore_errors=True)


def _parse_search_skills(output: str) -> list[dict[str, str]]:
    """解析 npx skills find 命令的输出。"""
    lines = _clean_cli_output(output)
    results: list[dict[str, str]] = []
    # 匹配形如 "owner/repo@skill-name [installs]"
    # 例如：vercel-labs/agent-skills@web-design-guidelines 339.3K installs
    pattern = re.compile(r"^([a-zA-Z0-9_\-\.]+/[a-zA-Z0-9_\-\.]+)\@([a-zA-Z0-9_\-\.]+)(?:\s+(.*))?$")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = pattern.match(line)
        if match:
            source, name, extra = match.groups()
            installs = extra.strip() if extra else ""
            results.append(
                {
                    "source": source,
                    "name": name,
                    "installs": installs,
                }
            )
    return results


async def search_remote_skills(query: str) -> list[dict[str, str]]:
    """使用 npx skills find <query> 搜索远程 skills。"""
    query_val = str(query or "").strip()
    if not query_val:
        return []
    if any(ch in query_val for ch in ("\n", "\r", "\x00")):
        raise ValueError("搜索关键字包含非法字符")

    sandbox = _RemoteSkillSandbox.create()
    try:
        output = await sandbox.run(["npx", "-y", "skills", "find", query_val])
    finally:
        await sandbox.cleanup()

    return _parse_search_skills(output)
