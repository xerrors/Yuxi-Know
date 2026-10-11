"""迁移后的职责模块。"""

from typing import Any

from yuxi.infrastructure.observability.logging import logger
from yuxi.modules.extensions.tools.catalog import get_tool_instances_by_category


async def resolve_configured_runtime_tools(context) -> list[Any]:
    from yuxi.modules.extensions.mcp.service import get_enabled_mcp_tools

    context._mcp_tool_servers = {}
    context._registered_builtin_tool_names = set()
    selected_tools = []
    selected_tool_names: set[str] = set()
    selected_tool_sources: dict[str, str] = {}
    builtin_tools = {tool.name: tool for tool in get_tool_instances_by_category("builtin")}

    if getattr(context, "run_id", None):
        from yuxi.modules.extensions.tools.builtin.mark_for_improvement import mark_for_improvement

        selected_tools.append(mark_for_improvement)
        selected_tool_names.add(mark_for_improvement.name)
        selected_tool_sources[mark_for_improvement.name] = "local"
        context._registered_builtin_tool_names.add(mark_for_improvement.name)

    for tool_name in getattr(context, "tools", None) or []:
        if not isinstance(tool_name, str) or tool_name in selected_tool_names:
            continue
        tool = builtin_tools.get(tool_name)
        if tool is None:
            logger.warning(f"Configured builtin tool not found, skip: {tool_name}")
            continue
        selected_tools.append(tool)
        selected_tool_names.add(tool_name)
        selected_tool_sources[tool_name] = "local"
        context._registered_builtin_tool_names.add(tool_name)

    # 去重后的 MCP server 列表(保持配置顺序)
    selected_mcp_servers: set[str] = set()
    server_names: list[str] = []
    for server_name in getattr(context, "mcps", None) or []:
        if not isinstance(server_name, str) or server_name in selected_mcp_servers:
            continue
        selected_mcp_servers.add(server_name)
        server_names.append(server_name)

    # 并发加载各 MCP server 的工具(单 server 33-300ms,串行 6 个累加 1-2s;
    # 官方 deepagents-code 同款优化: asyncio.gather 并发,取 max 而非 sum)。
    import asyncio

    async def _load_one(name: str):
        try:
            return name, await get_enabled_mcp_tools(name)
        except Exception as e:
            logger.warning(f"Failed to load configured MCP tools '{name}': {e}")
            return name, None

    loaded = await asyncio.gather(*(_load_one(n) for n in server_names))

    for server_name, mcp_tools in loaded:
        if not mcp_tools:
            logger.warning(f"Configured MCP unavailable, skip: {server_name}")
            continue
        for tool in mcp_tools:
            if tool.name in selected_tool_names:
                raise RuntimeError(f"工具名冲突：MCP '{server_name}' 的 '{tool.name}' 与 {selected_tool_sources[tool.name]} 工具同名")
            selected_tools.append(tool)
            selected_tool_names.add(tool.name)
            selected_tool_sources[tool.name] = f"MCP '{server_name}'"
            context._mcp_tool_servers[tool.name] = server_name

    # Skill 依赖的本地工具：必须随基础工具一起注册进 create_agent 的 ToolNode 才可执行，
    # 否则 Skill 激活后模型虽能发起调用，执行器仍报 "not a valid tool"。
    # 默认绑定给模型的可见性由 SkillsMiddleware 按 Skill 激活状态门控（保持按需加载）。
    from yuxi.modules.extensions.skills.runtime import resolve_skill_gated_tools

    for tool in resolve_skill_gated_tools(context):
        if tool.name in selected_tool_names:
            if selected_tool_sources[tool.name] != "local":
                source = selected_tool_sources[tool.name]
                raise RuntimeError(f"工具名冲突：Skill 本地工具 '{tool.name}' 与 {source} 同名")
            continue
        selected_tools.append(tool)
        selected_tool_names.add(tool.name)
        selected_tool_sources[tool.name] = "local"
        context._registered_builtin_tool_names.add(tool.name)

    return selected_tools
