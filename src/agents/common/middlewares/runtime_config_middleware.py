from __future__ import annotations

from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Annotated, Any, NotRequired

from deepagents.middleware.skills import SKILLS_SYSTEM_PROMPT
from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.types import Command

from src.agents.common import load_chat_model
from src.agents.common.toolkits.buildin import get_buildin_tools
from src.agents.common.toolkits.kbs import get_kb_based_tools
from src.services.mcp_service import get_enabled_mcp_tools
from src.services.skill_resolver import (
    SkillSessionSnapshot,
    build_dependency_bundle,
    collect_prompt_metadata,
    normalize_selected_skills,
    resolve_session_snapshot,
)
from src.services.skill_service import is_valid_skill_slug
from src.utils.datetime_utils import shanghai_now
from src.utils.logging_config import logger


def _activated_skills_reducer(left: list[str] | None, right: list[str] | None) -> list[str]:
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


class RuntimeConfigState(AgentState):
    activated_skills: NotRequired[Annotated[list[str], _activated_skills_reducer]]
    skill_session_snapshot: NotRequired[SkillSessionSnapshot]


class RuntimeConfigMiddleware(AgentMiddleware):
    """运行时配置中间件 - 应用模型/工具/知识库/MCP/提示词配置

    注意：所有可能用到的知识库工具必须在初始化时预加载并注册到 self.tools
    运行时根据配置从 self.tools 中筛选工具，不能动态添加新工具

    支持自定义上下文字段名称，以便在不同场景（如主智能体/子智能体）使用不同的配置字段
    """
    state_schema = RuntimeConfigState

    def __init__(
        self,
        *,
        extra_tools: list[Any] | None = None,
        model_context_name: str = "model",
        system_prompt_context_name: str = "system_prompt",
        tools_context_name: str = "tools",
        knowledges_context_name: str = "knowledges",
        mcps_context_name: str = "mcps",
        skills_context_name: str = "skills",
        enable_model_override: bool = True,
        enable_system_prompt_override: bool = True,
        enable_tools_override: bool = True,
        enable_skills_prompt_override: bool = True,
        skills_sources_for_prompt: list[str] | None = None,
    ):
        """初始化中间件

        Args:
            extra_tools: 额外工具列表（从 create_agent 的 tools 参数传入）
            model_context_name: 上下文中的模型字段名称（默认 "model"）
            system_prompt_context_name: 上下文中的系统提示词字段名称（默认 "system_prompt"）
            tools_context_name: 上下文中的工具列表字段名称（默认 "tools"）
            knowledges_context_name: 上下文中的知识库列表字段名称（默认 "knowledges"）
            mcps_context_name: 上下文中的 MCP 服务器列表字段名称（默认 "mcps"）
            skills_context_name: 上下文中的 skills 列表字段名称（默认 "skills"）
            enable_model_override: 是否允许覆盖模型配置（默认 True）
            enable_system_prompt_override: 是否允许覆盖系统提示词（默认 True）
            enable_tools_override: 是否允许覆盖工具列表（默认 True）
            enable_skills_prompt_override: 是否启用 skills 提示段注入（默认 True）
            skills_sources_for_prompt: skills 来源路径（用于提示词展示，默认 ["/skills/"]）
        """
        super().__init__()
        # 存储自定义字段名称
        self.model_context_name = model_context_name
        self.system_prompt_context_name = system_prompt_context_name
        self.tools_context_name = tools_context_name
        self.knowledges_context_name = knowledges_context_name
        self.mcps_context_name = mcps_context_name
        self.skills_context_name = skills_context_name
        # 存储覆盖配置
        self.enable_model_override = enable_model_override
        self.enable_system_prompt_override = enable_system_prompt_override
        self.enable_tools_override = enable_tools_override
        self.enable_skills_prompt_override = enable_skills_prompt_override
        self.skills_sources_for_prompt = skills_sources_for_prompt or ["/skills/"]

        self.tools: list[Any] = []
        # 预加载工具列表（仅当启用工具覆盖时）
        if self.enable_tools_override:
            self.kb_tools = get_kb_based_tools()
            self.buildin_tools = get_buildin_tools()
            self.tools = self.kb_tools + self.buildin_tools + (extra_tools or [])
        elif extra_tools:
            logger.warning(
                "RuntimeConfigMiddleware: extra_tools 参数已提供，但 enable_tools_override=False，"
                "将忽略 extra_tools 并不会应用任何工具覆盖。"
            )

        logger.debug(
            f"Initialized RuntimeConfigMiddleware with custom field names: model={model_context_name}, "
            f"system_prompt={system_prompt_context_name}, tools={tools_context_name}, "
            f"knowledges={knowledges_context_name}, mcps={mcps_context_name}, "
            f"skills={skills_context_name}"
        )

    async def abefore_agent(self, state: RuntimeConfigState, runtime) -> dict[str, Any] | None:
        runtime_context = runtime.context
        configured_skills = getattr(runtime_context, self.skills_context_name, None) or []
        selected_skills = normalize_selected_skills(configured_skills)

        try:
            snapshot = await resolve_session_snapshot(selected_skills)
        except Exception as e:
            logger.warning(f"RuntimeConfigMiddleware: failed to resolve skill snapshot in abefore_agent: {e}")
            snapshot = {
                "selected_skills": selected_skills,
                "visible_skills": [],
                "prompt_metadata": {},
                "dependency_map": {},
            }

        setattr(runtime_context, "skill_session_snapshot", snapshot)

        if not self.enable_system_prompt_override or not self.enable_skills_prompt_override:
            return None
        if getattr(runtime_context, "_skills_prompt_injected", False):
            return None
        if not snapshot.get("visible_skills"):
            return None

        skills_meta = collect_prompt_metadata(snapshot, snapshot.get("visible_skills") or [])
        skills_section = self._build_skills_section(skills_meta)
        base_prompt = getattr(runtime_context, self.system_prompt_context_name, "") or ""
        merged_prompt = f"{base_prompt}\n\n{skills_section}" if base_prompt else skills_section
        setattr(runtime_context, self.system_prompt_context_name, merged_prompt)
        setattr(runtime_context, "_skills_prompt_injected", True)
        return None

    async def awrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        runtime_context = request.runtime.context
        snapshot = self._get_skill_snapshot_from_context(runtime_context)
        overrides: dict[str, Any] = {}

        # 1. 模型覆盖（可选）
        if self.enable_model_override:
            model = load_chat_model(getattr(runtime_context, self.model_context_name, None))
            overrides["model"] = model

        # 2. 工具覆盖（可选）
        if self.enable_tools_override:
            state = request.state if isinstance(request.state, dict) else {}
            activated_skills = state.get("activated_skills", [])
            if not isinstance(activated_skills, list):
                activated_skills = []
            deps_bundle = build_dependency_bundle(snapshot, activated_skills)
            enabled_tools = await self.get_tools_from_context(
                runtime_context,
                extra_tool_names=deps_bundle["tools"],
                extra_mcps=deps_bundle["mcps"],
            )
            existing_tools = list(request.tools or [])
            enabled_tool_names = {t.name for t in enabled_tools}
            managed_tool_names = {t.name for t in self.tools}
            merged_tools = []
            for t_bind in existing_tools:
                # (1) 已启用的工具保留
                # (2) 非本中间件管理的工具保留
                if t_bind.name in enabled_tool_names or t_bind.name not in managed_tool_names:
                    merged_tools.append(t_bind)
            overrides["tools"] = merged_tools
            logger.debug(f"RuntimeConfigMiddleware selected tools: {[t.name for t in merged_tools]}")

        # 3. 系统提示词覆盖（可选）
        if self.enable_system_prompt_override:
            cur_datetime = f"当前时间：{shanghai_now().strftime('%Y-%m-%d %H:%M:%S')} UTC"
            system_prompt = getattr(runtime_context, self.system_prompt_context_name, "") or ""
            merged_system_prompt = f"{cur_datetime}\n\n{system_prompt}"

            content_blocks = list(request.system_message.content_blocks) if request.system_message else []
            new_content = content_blocks + [{"type": "text", "text": merged_system_prompt}]
            new_system_message = SystemMessage(content=new_content)
            overrides["system_message"] = new_system_message

        if overrides:
            request = request.override(**overrides)

        return await handler(request)

    async def get_tools_from_context(
        self,
        context,
        *,
        extra_tool_names: list[str] | None = None,
        extra_mcps: list[str] | None = None,
    ) -> list:
        """从上下文配置中获取工具列表"""
        selected_tools = []
        selected_tool_names: set[str] = set()

        # 1. 基础工具 (从 context.tools 中筛选)
        tools = getattr(context, self.tools_context_name, None) or []
        all_tool_names = []
        for tool_name in tools:
            if isinstance(tool_name, str):
                all_tool_names.append(tool_name)
        for tool_name in extra_tool_names or []:
            if isinstance(tool_name, str):
                all_tool_names.append(tool_name)

        tools_map = {t.name: t for t in self.tools}
        for tool_name in all_tool_names:
            if tool_name in selected_tool_names:
                continue
            if tool_name in tools_map:
                selected_tools.append(tools_map[tool_name])
                selected_tool_names.add(tool_name)
                continue
            logger.warning(f"RuntimeConfigMiddleware: tool dependency not found, skip: {tool_name}")

        # 2. 知识库工具
        knowledges = getattr(context, self.knowledges_context_name, None)
        if knowledges:
            kb_tools = get_kb_based_tools(db_names=knowledges)
            selected_tools.extend(kb_tools)

        # 3. MCP 工具（使用统一入口，自动过滤 disabled_tools）
        mcps = getattr(context, self.mcps_context_name, None) or []
        all_mcp_names: list[str] = []
        for server_name in mcps:
            if isinstance(server_name, str):
                all_mcp_names.append(server_name)
        for server_name in extra_mcps or []:
            if isinstance(server_name, str):
                all_mcp_names.append(server_name)

        selected_mcp_servers: set[str] = set()
        for server_name in all_mcp_names:
            if server_name in selected_mcp_servers:
                continue
            selected_mcp_servers.add(server_name)
            try:
                mcp_tools = await get_enabled_mcp_tools(server_name)
                if not mcp_tools:
                    logger.warning(f"RuntimeConfigMiddleware: mcp dependency unavailable, skip: {server_name}")
                selected_tools.extend(mcp_tools)
            except Exception as e:
                logger.warning(f"RuntimeConfigMiddleware: failed to load mcp dependency '{server_name}': {e}")

        return selected_tools

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ):
        result = await handler(request)
        if request.tool_call.get("name") != "read_file":
            return result

        args = request.tool_call.get("args") or {}
        file_path = args.get("file_path") if isinstance(args, dict) else None
        slug = self._extract_skill_slug_from_skill_md_path(file_path)
        if not slug:
            return result
        if not self._is_visible_skill_slug(request, slug):
            logger.warning(f"RuntimeConfigMiddleware: deny skill activation for invisible slug: {slug}")
            return result
        logger.debug(f"RuntimeConfigMiddleware: activated skill by read_file: {slug}")
        return self._merge_activated_skill_update(result, slug)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ):
        result = handler(request)
        if request.tool_call.get("name") != "read_file":
            return result

        args = request.tool_call.get("args") or {}
        file_path = args.get("file_path") if isinstance(args, dict) else None
        slug = self._extract_skill_slug_from_skill_md_path(file_path)
        if not slug:
            return result
        if not self._is_visible_skill_slug(request, slug):
            logger.warning(f"RuntimeConfigMiddleware: deny skill activation for invisible slug: {slug}")
            return result
        logger.debug(f"RuntimeConfigMiddleware: activated skill by read_file: {slug}")
        return self._merge_activated_skill_update(result, slug)

    def _extract_skill_slug_from_skill_md_path(self, file_path: Any) -> str | None:
        if not isinstance(file_path, str):
            return None
        raw = file_path.strip()
        if not raw:
            return None
        pure = PurePosixPath(raw if raw.startswith("/") else f"/{raw}")
        parts = [p for p in pure.parts if p not in ("/", "")]
        if len(parts) != 3:
            return None
        if parts[0] != "skills" or parts[2] != "SKILL.md":
            return None
        slug = parts[1]
        if not is_valid_skill_slug(slug):
            return None
        return slug

    def _merge_activated_skill_update(self, result: Any, slug: str):
        if isinstance(result, Command):
            update = dict(result.update or {})
            current = update.get("activated_skills") or []
            update["activated_skills"] = _activated_skills_reducer(current, [slug])
            return Command(graph=result.graph, update=update, resume=result.resume, goto=result.goto)

        if isinstance(result, ToolMessage):
            return Command(update={"messages": [result], "activated_skills": [slug]})

        return result

    def _is_visible_skill_slug(self, request: ToolCallRequest, slug: str) -> bool:
        snapshot = self._get_skill_snapshot_from_context(request.runtime.context)
        if snapshot:
            visible_skills = snapshot.get("visible_skills")
            if isinstance(visible_skills, list):
                return slug in visible_skills

        configured_skills = getattr(request.runtime.context, self.skills_context_name, None) or []
        normalized = normalize_selected_skills(configured_skills)
        return slug in normalized

    def _get_skill_snapshot_from_context(self, context: Any) -> SkillSessionSnapshot | None:
        snapshot = getattr(context, "skill_session_snapshot", None)
        if not isinstance(snapshot, dict):
            return None
        visible_skills = snapshot.get("visible_skills")
        selected_skills = snapshot.get("selected_skills")
        if not isinstance(visible_skills, list) or not isinstance(selected_skills, list):
            return None
        return snapshot

    def _format_skills_locations(self, sources: list[str]) -> str:
        locations = []
        for i, source_path in enumerate(sources):
            name = PurePosixPath(source_path.rstrip("/")).name.capitalize()
            suffix = " (higher priority)" if i == len(sources) - 1 else ""
            locations.append(f"**{name} Skills**: `{source_path}`{suffix}")
        return "\n".join(locations)

    def _format_skills_list(self, skills_meta: list[dict[str, str]]) -> str:
        if not skills_meta:
            return f"(No skills available yet. You can create skills in {' or '.join(self.skills_sources_for_prompt)})"

        lines = []
        for skill in skills_meta:
            lines.append(f"- **{skill['name']}**: {skill['description']}")
            lines.append(f"  -> Read `{skill['path']}` for full instructions")
        return "\n".join(lines)

    def _build_skills_section(self, skills_meta: list[dict[str, str]]) -> str:
        skills_locations = self._format_skills_locations(self.skills_sources_for_prompt)
        skills_list = self._format_skills_list(skills_meta)
        return SKILLS_SYSTEM_PROMPT.format(
            skills_locations=skills_locations,
            skills_list=skills_list,
        )
