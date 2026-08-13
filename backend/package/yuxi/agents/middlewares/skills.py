"""Skills 中间件 - 处理 skills 提示词注入、依赖展开、动态激活"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Annotated, Any, NotRequired, TypedDict

from deepagents.middleware._utils import append_to_system_message
from deepagents.middleware.skills import SKILLS_SYSTEM_PROMPT
from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.tools.tool_node import ToolCallRequest
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.agents.mcp.service import get_enabled_mcp_tools
from yuxi.agents.skills.repository import SkillRepository
from yuxi.agents.skills.service import (
    PERSONAL_SKILL_SOURCE_TYPE,
    is_valid_skill_slug,
    list_accessible_skills,
    normalize_string_list,
)
from yuxi.agents.toolkits import get_all_tool_instances
from yuxi.storage.postgres.manager import pg_manager
from yuxi.utils.logging_config import logger
from yuxi.utils.paths import VIRTUAL_PATH_WORKSPACE_SKILLS, VIRTUAL_SKILLS_PATH

# =============================================================================
# 类型定义
# =============================================================================


class SkillPromptMetadata(TypedDict):
    name: str
    description: str
    path: str


class SkillDependencyNode(TypedDict):
    tools: list[str]
    mcps: list[str]
    skills: list[str]


# =============================================================================
# 运行时数据加载函数
# =============================================================================


async def _list_skills_from_db(db: AsyncSession | None = None, user=None) -> list:
    """从数据库加载 skills 列表"""
    if db is not None:
        if user is not None:
            return await list_accessible_skills(db, user)
        repo = SkillRepository(db)
        return await repo.list_enabled()

    async with pg_manager.get_async_session_context() as session:
        if user is not None:
            return await list_accessible_skills(session, user)
        repo = SkillRepository(session)
        return await repo.list_enabled()


def build_prompt_metadata(skills: list) -> dict[str, SkillPromptMetadata]:
    """构建 Skill 提示词元数据，并为个人 Skill 使用工作区真实路径。"""
    result: dict[str, SkillPromptMetadata] = {}
    for item in skills:
        if not item.slug:
            continue
        root = (
            VIRTUAL_PATH_WORKSPACE_SKILLS
            if getattr(item, "source_scope", None) == PERSONAL_SKILL_SOURCE_TYPE
            else VIRTUAL_SKILLS_PATH
        )
        result[item.slug] = {
            "name": item.name,
            "description": item.description,
            "path": f"{root}/{item.slug}/SKILL.md",
        }
    return result


def build_dependency_map(skills: list) -> dict[str, SkillDependencyNode]:
    result: dict[str, SkillDependencyNode] = {}
    for item in skills:
        if not item.slug:
            continue
        result[item.slug] = {
            "tools": normalize_string_list(item.tool_dependencies or []),
            "mcps": normalize_string_list(item.mcp_dependencies or []),
            "skills": normalize_string_list(item.skill_dependencies or []),
        }
    return result


def build_source_map(skills: list) -> dict[str, str]:
    """构建需要复制到线程只读目录的 Skill 来源映射。"""
    return {
        item.slug: str(item.source_dir)
        for item in skills
        if item.slug
        and getattr(item, "source_scope", None) != PERSONAL_SKILL_SOURCE_TYPE
        and getattr(item, "source_dir", None)
    }


async def get_prompt_metadata(db: AsyncSession | None = None, user=None) -> dict[str, SkillPromptMetadata]:
    """获取提示词元数据（直接从数据库加载）"""
    return build_prompt_metadata(await _list_skills_from_db(db, user))


async def get_dependency_map(db: AsyncSession | None = None, user=None) -> dict[str, SkillDependencyNode]:
    """获取依赖关系映射（直接从数据库加载）"""
    return build_dependency_map(await _list_skills_from_db(db, user))


def expand_skill_closure(
    slugs: list[str] | None,
    dependency_map: dict[str, SkillDependencyNode],
) -> list[str]:
    """展开 skills 依赖闭包，返回包含所有依赖的列表"""
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

        node = dependency_map.get(slug)
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


async def resolve_runtime_skills_for_context(context, *, db: AsyncSession | None = None, user=None) -> dict[str, Any]:
    skill_items = await _list_skills_from_db(db, user)
    dependency_map = build_dependency_map(skill_items)
    prompt_metadata = build_prompt_metadata(skill_items)
    available = set(dependency_map)
    selected = normalize_string_list(getattr(context, "skills", None))
    context_skills = [slug for slug in selected if slug in available]
    prompt_skills = expand_skill_closure(context_skills, dependency_map)
    return {
        "context_skills": context_skills,
        "prompt_skills": prompt_skills,
        "readable_skills": prompt_skills,
        "runtime_skill_metadata": prompt_metadata,
        "runtime_skill_dependency_map": dependency_map,
        "runtime_skill_sources": build_source_map(skill_items),
    }


def resolve_skill_gated_tools(context) -> list:
    """解析当前 Agent 所有可见 Skill 依赖的本地工具实例。

    这些工具默认不会绑定给模型（由 SkillsMiddleware 在对应 Skill 激活后才放出），
    但必须在构建期注册进 create_agent 的 ToolNode，否则即便模型发起调用，执行器也会
    判定为 "not a valid tool"。调用方应自行排除已在基础工具集中的工具，避免重复门控。
    """
    dependency_map = getattr(context, "_runtime_skill_dependency_map", {}) or {}
    readable_skills = getattr(context, "_readable_skills", []) or []
    tool_names: set[str] = set()
    for slug in readable_skills:
        node = dependency_map.get(slug) or {}
        tool_names.update(node.get("tools", []))
    if not tool_names:
        return []
    return [tool for tool in get_all_tool_instances() if tool.name in tool_names]


def _activated_skills_reducer(left: list[str] | None, right: list[str] | None) -> list[str]:
    """合并 activated_skills 列表"""
    merged: list[str] = []
    seen: set[str] = set()
    for group in (left or [], right or []):
        for value in group:
            if not isinstance(value, str):
                continue
            slug = value.strip()
            if not slug or slug in seen:
                continue
            seen.add(slug)
            merged.append(slug)
    return merged


class SkillsState(AgentState):
    """Skills 状态定义"""

    activated_skills: NotRequired[Annotated[list[str], _activated_skills_reducer]]


class SkillsMiddleware(AgentMiddleware):
    """Skills 中间件 - 处理 skills 提示词注入、依赖展开、动态激活

    职责：
    - Skills 提示词注入（直接从数据库加载）
    - 依赖展开（用户配置 + 动态激活）
    - 工具/MCP 动态加载
    """

    state_schema = SkillsState

    def __init__(
        self,
        *,
        skills_context_name: str = "skills",
        enable_skills_prompt: bool = True,
        skills_sources_for_prompt: list[str] | None = None,
    ):
        """初始化中间件

        Args:
            skills_context_name: 上下文中的 skills 列表字段名称（默认 "skills"）
            enable_skills_prompt: 是否启用 skills 提示段注入（默认 True）
            skills_sources_for_prompt: skills 来源路径（默认展示共享投影和个人工作区）
        """
        super().__init__()
        self.skills_context_name = skills_context_name
        self.enable_skills_prompt = enable_skills_prompt
        self.skills_sources_for_prompt = skills_sources_for_prompt or [
            f"{VIRTUAL_SKILLS_PATH}/",
            f"{VIRTUAL_PATH_WORKSPACE_SKILLS}/",
        ]

    async def awrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        """包装模型调用，处理 skills 提示词注入、动态激活和依赖展开"""
        runtime_context = request.runtime.context

        if self.enable_skills_prompt:
            prompt_skills = getattr(runtime_context, "_prompt_skills", None)
            if isinstance(prompt_skills, list):
                prompt_skills = normalize_string_list(prompt_skills)
                if prompt_skills:
                    skills_meta = self._collect_prompt_metadata(prompt_skills, runtime_context)
                    skills_section = self._build_skills_section(skills_meta)
                    system_message = append_to_system_message(getattr(request, "system_message", None), skills_section)
                    request = request.override(system_message=system_message)

        state = request.state if isinstance(request.state, dict) else {}
        activated = state.get("activated_skills", []) or []
        if not isinstance(activated, list):
            activated = []

        readable_skills = self._get_readable_skills(runtime_context)
        activated = [slug for slug in normalize_string_list(activated) if slug in readable_skills]

        deps_bundle = self._build_dependency_bundle(activated, runtime_context)
        activated_tool_names = set(deps_bundle["tools"])

        # 门控：未激活 Skill 的依赖工具对模型不可见（保持按需加载）。
        # 这些工具已在构建期由 resolve_configured_runtime_tools 注册进 ToolNode，剔除只影响模型可见性、不影响可执行性。
        # 排除基础工具集中的工具（如 present_artifacts），它们始终可见、不受 Skill 激活影响。
        gated_tool_names = self._resolve_gated_tool_names(runtime_context) - activated_tool_names
        model_tools = list(request.tools or [])
        if gated_tool_names:
            model_tools = [t for t in model_tools if t.name not in gated_tool_names]

        # 追加已激活 Skill 的依赖工具：本地工具确保绑定给模型，MCP 工具按需加载
        enabled_tools = []
        if activated_tool_names:
            enabled_tools = [t for t in get_all_tool_instances() if t.name in activated_tool_names]
        if deps_bundle["mcps"]:
            enabled_tools.extend(
                await self._get_mcp_tools_from_context(runtime_context, extra_mcps=deps_bundle["mcps"])
            )

        existing_tool_names = {t.name for t in model_tools}
        for t in enabled_tools:
            if t.name not in existing_tool_names:
                model_tools.append(t)
                existing_tool_names.add(t.name)

        if gated_tool_names or enabled_tools:
            request = request.override(tools=model_tools)

        return await handler(request)

    def _resolve_gated_tool_names(self, runtime_context) -> set[str]:
        """所有可见 Skill 依赖、且不属于基础工具集的工具名集合（即「仅经 Skill 激活才放出」的工具）。"""
        dependency_map = self._get_runtime_dependency_map(runtime_context)
        readable_skills = self._get_readable_skills(runtime_context)
        base_tool_names = set(normalize_string_list(getattr(runtime_context, "tools", None)))
        gated: set[str] = set()
        for slug in readable_skills:
            gated.update(dependency_map.get(slug, {}).get("tools", []))
        return gated - base_tool_names

    def _build_dependency_bundle(self, activated_skills: list[str], runtime_context) -> dict[str, list[str]]:
        """根据直接激活的 skills 构建依赖包（不包含闭包展开的依赖）"""
        dependency_map = self._get_runtime_dependency_map(runtime_context)

        tools: list[str] = []
        mcps: list[str] = []
        seen_tools: set[str] = set()
        seen_mcps: set[str] = set()

        for slug in activated_skills:
            dep = dependency_map.get(slug, {})
            for tool_name in dep.get("tools", []):
                if tool_name in seen_tools:
                    continue
                seen_tools.add(tool_name)
                tools.append(tool_name)
            for mcp_name in dep.get("mcps", []):
                if mcp_name in seen_mcps:
                    continue
                seen_mcps.add(mcp_name)
                mcps.append(mcp_name)

        return {"tools": tools, "mcps": mcps, "skills": activated_skills}

    def _collect_prompt_metadata(self, slugs: list[str], runtime_context) -> list[SkillPromptMetadata]:
        """收集指定 slugs 的提示词元数据"""
        prompt_metadata = self._get_runtime_prompt_metadata(runtime_context)

        result: list[SkillPromptMetadata] = []
        seen: set[str] = set()

        for slug in slugs:
            if not isinstance(slug, str):
                continue
            normalized = slug.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)

            item = prompt_metadata.get(normalized)
            if not item:
                logger.debug(f"Skill slug not found in prompt metadata, skip: {normalized}")
                continue
            result.append(dict(item))

        return result

    async def _get_mcp_tools_from_context(
        self,
        context,
        *,
        extra_mcps: list[str] | None = None,
    ) -> list:
        """从上下文配置中获取 MCP 工具列表"""
        import asyncio

        # MCP 工具（并行加载）
        mcps = getattr(context, "mcps", None) or []
        all_mcp_names: list[str] = []
        for server_name in mcps:
            if isinstance(server_name, str):
                all_mcp_names.append(server_name)
        for server_name in extra_mcps or []:
            if isinstance(server_name, str):
                all_mcp_names.append(server_name)

        # 去重
        unique_mcp_names = list(dict.fromkeys(all_mcp_names))

        async def load_mcp_tools(server_name: str) -> list:
            """加载单个 MCP 服务器的工具"""
            try:
                mcp_tools = await get_enabled_mcp_tools(server_name)
                if not mcp_tools:
                    logger.warning(f"SkillsMiddleware: mcp dependency unavailable, skip: {server_name}")
                return mcp_tools
            except Exception as e:
                logger.warning(f"SkillsMiddleware: failed to load mcp dependency '{server_name}': {e}")
                return []

        # 并行加载所有 MCP 工具
        results = await asyncio.gather(*[load_mcp_tools(name) for name in unique_mcp_names])
        selected_tools = []
        for tools in results:
            selected_tools.extend(tools)

        return selected_tools

    def _process_tool_call_result(self, result: Any, request: ToolCallRequest) -> Any:
        """处理工具调用结果，检查并处理 skill 动态激活"""
        if request.tool_call.get("name") != "read_file":
            return result

        args = request.tool_call.get("args") or {}
        file_path = args.get("file_path") if isinstance(args, dict) else None
        slug = self._extract_skill_slug_from_skill_md_path(file_path)

        if not slug:
            return result

        if not self._is_visible_skill_slug(request, slug):
            logger.warning(f"SkillsMiddleware: deny skill activation for invisible slug: {slug}")
            return result

        logger.debug(f"SkillsMiddleware: activated skill by read_file: {slug}")
        return self._merge_activated_skill_update(result, slug)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ):
        """包装工具调用，处理 skill 动态激活"""
        result = await handler(request)
        return self._process_tool_call_result(result, request)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ):
        """同步版本的工具调用包装"""
        result = handler(request)
        return self._process_tool_call_result(result, request)

    def _extract_skill_slug_from_skill_md_path(self, file_path: Any) -> str | None:
        """从共享投影或个人工作区的 SKILL.md 路径中提取 slug。"""
        if not isinstance(file_path, str):
            return None
        raw = file_path.strip()
        if not raw:
            return None
        pure = PurePosixPath(raw if raw.startswith("/") else f"/{raw}")
        for root in (PurePosixPath(VIRTUAL_SKILLS_PATH), PurePosixPath(VIRTUAL_PATH_WORKSPACE_SKILLS)):
            try:
                relative = pure.relative_to(root)
            except ValueError:
                continue
            if len(relative.parts) == 2 and relative.name == "SKILL.md" and is_valid_skill_slug(relative.parts[0]):
                return relative.parts[0]
        return None

    def _get_readable_skills(self, runtime_context) -> set[str]:
        selected = getattr(runtime_context, "_readable_skills", [])
        return set(normalize_string_list(selected if isinstance(selected, list) else []))

    def _get_runtime_prompt_metadata(self, runtime_context) -> dict[str, SkillPromptMetadata]:
        metadata = getattr(runtime_context, "_runtime_skill_metadata", {})
        return metadata if isinstance(metadata, dict) else {}

    def _get_runtime_dependency_map(self, runtime_context) -> dict[str, SkillDependencyNode]:
        dependency_map = getattr(runtime_context, "_runtime_skill_dependency_map", {})
        return dependency_map if isinstance(dependency_map, dict) else {}

    def _is_visible_skill_slug(self, request: ToolCallRequest, slug: str) -> bool:
        """检查 slug 是否可见"""
        return slug in self._get_readable_skills(request.runtime.context)

    def _merge_activated_skill_update(self, result: Any, slug: str):
        """合并动态激活的 skill 更新"""
        from langchain_core.messages import ToolMessage

        if isinstance(result, Command):
            update = dict(result.update or {})
            current = update.get("activated_skills") or []
            update["activated_skills"] = _activated_skills_reducer(current, [slug])
            return Command(graph=result.graph, update=update, resume=result.resume, goto=result.goto)

        if isinstance(result, ToolMessage):
            return Command(update={"messages": [result], "activated_skills": [slug]})

        return result

    def _format_skills_locations(self, sources: list[str]) -> str:
        """格式化 skills 位置信息"""
        locations = []
        for i, source_path in enumerate(sources):
            name = PurePosixPath(source_path.rstrip("/")).name.capitalize()
            suffix = " (higher priority)" if i == len(sources) - 1 else ""
            locations.append(f"**{name} Skills**: `{source_path}`{suffix}")
        return "\n".join(locations)

    def _format_skills_list(self, skills_meta: list[dict[str, str]]) -> str:
        """格式化 skills 列表"""
        if not skills_meta:
            return f"(No skills available yet. You can create skills in {' or '.join(self.skills_sources_for_prompt)})"

        lines = []
        for skill in skills_meta:
            lines.append(f"- **{skill['name']}**: {skill['description']}")
            lines.append(f"  -> Read `{skill['path']}` for full instructions")
        return "\n".join(lines)

    def _build_skills_section(self, skills_meta: list[dict[str, str]]) -> str:
        """构建 skills 提示段"""
        skills_locations = self._format_skills_locations(self.skills_sources_for_prompt)
        skills_list = self._format_skills_list(skills_meta)
        return SKILLS_SYSTEM_PROMPT.format(
            skills_locations=skills_locations,
            skills_load_warnings="",
            skills_list=skills_list,
        )
