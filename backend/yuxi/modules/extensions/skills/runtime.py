"""Skill 运行时解析。"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from yuxi.infrastructure.filesystem import open_regular_file_fd
from yuxi.infrastructure.observability.logging import logger
from yuxi.modules.extensions.skills.access import lock_accessible_shared_skills_for_runtime, resolved_shared_skill
from yuxi.modules.extensions.skills.package import normalize_string_list
from yuxi.modules.extensions.skills.personal import list_personal_skills
from yuxi.modules.extensions.skills.projection import refresh_user_skill_projection_async
from yuxi.modules.extensions.skills.resolved import RuntimeSkill, SkillRuntimeSnapshot
from yuxi.modules.identity.models import User
from yuxi.modules.workspace.runtime_paths import PERSONAL_SKILLS_PATH, SHARED_SKILLS_PATH


async def sync_agent_context_skills(context) -> None:
    """构图前校验运行身份，并刷新用户获授权的共享 Skill 投影。"""
    thread_id = context.get("thread_id") if isinstance(context, dict) else getattr(context, "thread_id", None)
    if not isinstance(thread_id, str) or not thread_id.strip():
        raise ValueError("thread_id is required in runtime context")
    uid = context.get("uid") if isinstance(context, dict) else getattr(context, "uid", None)
    if not isinstance(uid, str) or not uid.strip():
        raise ValueError("uid is required in runtime context")
    await refresh_user_skill_projection_async(uid.strip())


async def resolve_runtime_skills_for_context(
    context,
    *,
    db: AsyncSession,
    user: User,
    agent=None,
) -> SkillRuntimeSnapshot:
    """合并已选共享与全部个人 Skill，派生运行范围和预加载快照。"""
    selected = normalize_string_list(getattr(context, "skills", None))
    personal_items = await list_personal_skills(str(user.uid))
    personal_slugs = {item.slug for item in personal_items}
    bound_slug = None
    agent_slug = getattr(context, "agent_slug", None)
    if agent_slug:
        from yuxi.modules.agents.repositories.definitions import AgentRepository
        from yuxi.modules.extensions.skills.repository import SkillRepository

        if agent is None:
            agent = await AgentRepository(db).get_visible_by_slug(slug=agent_slug, user=user)
        if agent is None:
            raise PermissionError("智能体不存在或无权限访问")
        bound = await SkillRepository(db).get_by_bound_agent_id(agent.id)
        previous = context.skill_runtime_snapshot
        if bound is not None and previous is not None:
            prepared_bound = {slug for slug, metadata in previous["skill_metadata"].items() if metadata["source_scope"] == "agent_bound"}
            # 执行边界只复核已准备绑定；中途新增绑定在下一 Run 生效。
            if bound.slug not in prepared_bound:
                bound = None
        if bound is not None:
            if bound.slug in personal_slugs:
                raise ValueError("个人 Skill 与智能体专属 Skill 标识冲突，请重命名个人 Skill")
            bound_slug = bound.slug
            selected = [*selected, bound_slug]
    shared_rows = await lock_accessible_shared_skills_for_runtime(
        db,
        user,
        selected,
        shadowed_slugs=personal_slugs,
        **({"bound_slug": bound_slug} if bound_slug else {}),
    )
    skill_items_by_slug = {item.slug: resolved_shared_skill(item) for item in shared_rows if item.slug}
    skill_items_by_slug.update({item.slug: item for item in personal_items if item.slug})
    runtime_skills = build_runtime_skills(list(skill_items_by_slug.values()))
    selected_skills = [slug for slug in selected if slug in skill_items_by_slug]
    context_skills = normalize_string_list([*selected_skills, *(item.slug for item in personal_items)])
    effective_skills = expand_skill_closure(context_skills, runtime_skills)
    limited = any(dependency not in runtime_skills for slug in effective_skills for dependency in runtime_skills[slug]["skills"])
    configured_preloads = normalize_string_list(getattr(context, "preload_skills", None))
    context_preload_skills = [slug for slug in configured_preloads if slug in selected_skills]
    if bound_slug:
        if bound_slug not in runtime_skills:
            raise PermissionError("智能体专属 Skill 不可用")
        context_preload_skills = normalize_string_list([*context_preload_skills, bound_slug])
    preloaded_skills = expand_skill_closure(context_preload_skills, runtime_skills)
    preloaded_contents = (
        await asyncio.to_thread(_read_preloaded_skill_contents, preloaded_skills, skill_items_by_slug) if preloaded_skills else {}
    )
    return {
        "capability_limited": limited,
        "context_skills": context_skills,
        "context_preload_skills": context_preload_skills,
        "effective_skills": effective_skills,
        "runtime_skills": runtime_skills,
        "skill_metadata": {
            slug: {
                "source_scope": skill_items_by_slug[slug].source_scope,
                "version": skill_items_by_slug[slug].version,
                "content_hash": skill_items_by_slug[slug].content_hash,
            }
            for slug in effective_skills
        },
        "preloaded_skills": preloaded_skills,
        "preloaded_skill_contents": preloaded_contents,
    }


def build_runtime_skills(skills: list) -> dict[str, RuntimeSkill]:
    """从已授权 Skill 构建运行时信息。"""
    result: dict[str, RuntimeSkill] = {}
    for item in skills:
        if not item.slug:
            continue
        root = PERSONAL_SKILLS_PATH if getattr(item, "source_scope", None) == "personal" else SHARED_SKILLS_PATH
        result[item.slug] = {
            "name": item.name,
            "description": item.description,
            "path": f"{root}/{item.slug}/SKILL.md",
            "tools": normalize_string_list(item.tool_dependencies or []),
            "mcps": normalize_string_list(item.mcp_dependencies or []),
            "skills": normalize_string_list(item.skill_dependencies or []),
        }
    return result


def expand_skill_closure(
    slugs: list[str] | None,
    runtime_skills: dict[str, RuntimeSkill],
) -> list[str]:
    """展开 Skill 依赖闭包并保持根与依赖的声明顺序。"""
    ordered_roots = normalize_string_list(slugs)
    if not ordered_roots:
        return []

    result: list[str] = []
    seen: set[str] = set()

    def dfs(slug: str, stack: set[str]) -> None:
        if slug in stack:
            logger.warning(f"Cycle detected in skill dependencies, skip: {' -> '.join([*stack, slug])}")
            return
        if slug in seen:
            return

        node = runtime_skills.get(slug)
        if not node:
            logger.warning(f"Skill dependency target not found in DB, skip: {slug}")
            return

        seen.add(slug)
        result.append(slug)
        next_stack = set(stack)
        next_stack.add(slug)
        for dep in node.get("skills", []):
            dfs(dep, next_stack)

    for root in ordered_roots:
        dfs(root, set())
    return result


def build_dependency_bundle(
    activated_skills: list[str],
    runtime_skills: dict[str, RuntimeSkill],
) -> dict[str, list[str]]:
    """汇总直接激活 Skill 的本地工具和 MCP 依赖。"""
    tools: list[str] = []
    mcps: list[str] = []
    seen_tools: set[str] = set()
    seen_mcps: set[str] = set()

    for slug in activated_skills:
        dependency = runtime_skills.get(slug, {})
        for tool_name in dependency.get("tools", []):
            if tool_name in seen_tools:
                continue
            seen_tools.add(tool_name)
            tools.append(tool_name)
        for mcp_name in dependency.get("mcps", []):
            if mcp_name in seen_mcps:
                continue
            seen_mcps.add(mcp_name)
            mcps.append(mcp_name)

    return {"tools": tools, "mcps": mcps}


def _read_preloaded_skill_contents(slugs: list[str], skill_items: dict[str, Any]) -> dict[str, str]:
    """从授权解析得到的真实来源读取根级 SKILL.md。"""

    contents: dict[str, str] = {}
    for slug in slugs:
        try:
            source_dir = Path(skill_items[slug].source_dir)
            if not source_dir.is_absolute() or ".." in source_dir.parts:
                raise OSError("Skill 来源目录必须是规范化绝对路径")
            with open_regular_file_fd(
                Path(source_dir.anchor),
                (*source_dir.parts[1:], "SKILL.md"),
            ) as (file_fd, _file_stat):
                with os.fdopen(os.dup(file_fd), encoding="utf-8") as skill_file:
                    contents[slug] = skill_file.read()
        except (OSError, UnicodeError) as exc:
            raise RuntimeError(f"预加载 Skill '{slug}' 失败：根级 SKILL.md 不可读") from exc
    return contents
