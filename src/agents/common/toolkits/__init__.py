# toolkits 包
from .registry import (
    ToolExtraMetadata,
    get_all_extra_metadata,
    get_all_tool_instances,
    get_extra_metadata,
    register_tool,
    tool,
)

# 工具获取函数
from .buildin import get_buildin_tools
from .kbs import get_kb_based_tools
from src.services.mcp_service import get_enabled_mcp_tools


async def get_tools_from_context(context, extra_tools=None):
    """从上下文配置中获取工具列表"""
    # 1. 基础工具 (从 context.tools 中筛选)
    all_basic_tools = get_buildin_tools() + (extra_tools or [])
    selected_tools = []

    if context.tools:
        # 创建工具映射表
        tools_map = {t.name: t for t in all_basic_tools}
        for tool_name in context.tools:
            if tool_name in tools_map:
                selected_tools.append(tools_map[tool_name])

    # 2. 知识库工具
    if context.knowledges:
        kb_tools = get_kb_based_tools(db_names=context.knowledges)
        selected_tools.extend(kb_tools)

    # 3. MCP 工具（使用统一入口，自动过滤 disabled_tools）
    if context.mcps:
        for server_name in context.mcps:
            mcp_tools = await get_enabled_mcp_tools(server_name)
            selected_tools.extend(mcp_tools)

    return selected_tools


__all__ = [
    "register_tool",
    "get_extra_metadata",
    "get_all_extra_metadata",
    "get_all_tool_instances",
    "ToolExtraMetadata",
    "tool",
    "get_buildin_tools",
    "get_kb_based_tools",
    "get_tools_from_context",
]
