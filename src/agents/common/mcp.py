"""MCP Client setup and management for LangGraph ReAct Agent."""

import traceback
from collections.abc import Callable
from typing import Any, cast

from langchain_mcp_adapters.client import MultiServerMCPClient

from src.utils import logger

# Global MCP tools cache
_mcp_tools_cache: dict[str, list[Callable[..., Any]]] = {}

# MCP Server configurations（运行时缓存，从数据库加载）
MCP_SERVERS: dict[str, dict[str, Any]] = {}

# 默认 MCP 服务器配置（首次启动时导入数据库）
_DEFAULT_MCP_SERVERS = {
    "sequentialthinking": {
        "url": "https://remote.mcpservers.org/sequentialthinking/mcp",
        "transport": "streamable_http",
        "description": "顺序思考工具，帮助 AI 将复杂问题分解为多个步骤",
        "icon": "🧠",
        "tags": ["工具", "AI"],
    },
}


async def load_mcp_servers_from_db() -> None:
    """从数据库加载所有启用的 MCP 服务器配置到 MCP_SERVERS 缓存"""
    global MCP_SERVERS

    # 延迟导入以避免循环引用
    from sqlalchemy import select

    from src.storage.db.manager import db_manager
    from src.storage.db.models import MCPServer

    try:
        async with db_manager.get_async_session_context() as session:
            result = await session.execute(select(MCPServer).filter(MCPServer.enabled == 1))
            servers = result.scalars().all()
            MCP_SERVERS.clear()
            for server in servers:
                MCP_SERVERS[server.name] = server.to_mcp_config()
            logger.info(f"Loaded {len(MCP_SERVERS)} MCP servers from database: {list(MCP_SERVERS.keys())}")
    except Exception as e:
        logger.error(f"Failed to load MCP servers from database: {e}")


def sync_mcp_server_to_cache(name: str, config: dict[str, Any] | None) -> None:
    """同步单个 MCP 服务器配置到缓存

    Args:
        name: 服务器名称
        config: 服务器配置，如果为 None 则从缓存中删除
    """
    global MCP_SERVERS

    if config is None:
        MCP_SERVERS.pop(name, None)
        logger.info(f"Removed MCP server '{name}' from cache")
    else:
        MCP_SERVERS[name] = config
        logger.info(f"Synced MCP server '{name}' to cache")

    # 清除该服务器的工具缓存
    _mcp_tools_cache.pop(name, None)


async def init_mcp_servers() -> None:
    """初始化 MCP 服务器配置

    首次启动时，如果数据库为空，将默认配置导入数据库
    然后从数据库加载配置到 MCP_SERVERS 缓存
    """
    # 延迟导入以避免循环引用
    from sqlalchemy import func, select

    from src.storage.db.manager import db_manager
    from src.storage.db.models import MCPServer

    try:
        async with db_manager.get_async_session_context() as session:
            # 检查数据库是否有 MCP 配置
            result = await session.execute(select(func.count(MCPServer.name)))
            count = result.scalar()

            if count == 0:
                # 数据库为空，导入默认配置
                logger.info("No MCP servers in database, importing default configurations...")
                for name, config in _DEFAULT_MCP_SERVERS.items():
                    server = MCPServer(
                        name=name,
                        description=config.get("description"),
                        transport=config["transport"],
                        url=config["url"],
                        headers=config.get("headers"),
                        timeout=config.get("timeout"),
                        sse_read_timeout=config.get("sse_read_timeout"),
                        tags=config.get("tags"),
                        icon=config.get("icon"),
                        enabled=1,
                        created_by="system",
                        updated_by="system",
                    )
                    session.add(server)
                await session.commit()
                logger.info(f"Imported {len(_DEFAULT_MCP_SERVERS)} default MCP servers to database")

        # 从数据库加载配置到缓存
        await load_mcp_servers_from_db()

    except Exception as e:
        logger.error(f"Failed to initialize MCP servers: {e}, traceback: {traceback.format_exc()}")


async def get_mcp_client(
    server_configs: dict[str, Any] | None = None,
) -> MultiServerMCPClient | None:
    """Initializes an MCP client with the given server configurations."""
    try:
        client = MultiServerMCPClient(server_configs)  # pyright: ignore[reportArgumentType]
        logger.info(f"Initialized MCP client with servers: {list(server_configs.keys())}")
        return client
    except Exception as e:
        logger.error("Failed to initialize MCP client: {}", e)
        return None


def to_camel_case(s: str) -> str:
    """将字符串转换为小驼峰格式"""
    import re

    # 处理 - 和 _
    s = re.sub(r"[-_]+(.)", lambda m: m.group(1).upper(), s)
    # 首字母小写
    if len(s) > 0:
        s = s[0].lower() + s[1:]
    return s


async def get_mcp_tools(server_name: str, additional_servers: dict[str, dict] = None) -> list[Callable[..., Any]]:
    """Get MCP tools for a specific server, initializing client if needed and rendering unique IDs."""
    global _mcp_tools_cache

    # Return cached tools if available
    if server_name in _mcp_tools_cache:
        return _mcp_tools_cache[server_name]

    mcp_servers = MCP_SERVERS | (additional_servers or {})

    try:
        assert server_name in mcp_servers, f"Server {server_name} not found in ({list(mcp_servers.keys())})"
        client = await get_mcp_client({server_name: mcp_servers[server_name]})
        if client is None:
            return []

        # Get all tools
        all_tools = await client.get_tools()
        raw_tools = cast(list[Any], all_tools)

        # 渲染 ID 规则: mcp__[camelCaseServer]__[camelCaseTool]
        server_cc = to_camel_case(server_name)
        processed_tools = []

        for tool in raw_tools:
            # 渲染唯一 ID 规则: mcp__[camelCaseServer]__[camelCaseTool]
            original_name = tool.name
            tool_cc = to_camel_case(original_name)
            unique_id = f"mcp__{server_cc}__{tool_cc}"

            # 使用 metadata 存储，这是 LangChain 工具扩展属性的标准做法
            if tool.metadata is None:
                tool.metadata = {}
            tool.metadata["id"] = unique_id

            processed_tools.append(tool)

        _mcp_tools_cache[server_name] = processed_tools
        logger.info(f"Loaded {len(processed_tools)} tools from MCP server '{server_name}' with extra tool IDs")
        return processed_tools
    except AssertionError as e:
        logger.warning(f"[assert] Failed to load tools from MCP server '{server_name}': {e}")
        return []
    except Exception as e:
        logger.error(f"Failed to load tools from MCP server '{server_name}': {e}, traceback: {traceback.format_exc()}")
        return []


async def get_all_mcp_tools() -> list[Callable[..., Any]]:
    """Get all tools from all configured MCP servers."""
    all_tools = []
    for server_name in MCP_SERVERS.keys():
        tools = await get_mcp_tools(server_name)
        all_tools.extend(tools)
    return all_tools


def add_mcp_server(name: str, config: dict[str, Any]) -> None:
    """Add a new MCP server configuration."""
    MCP_SERVERS[name] = config
    # Clear client to force reinitialization with new config
    clear_mcp_cache()


def clear_mcp_cache() -> None:
    """Clear the MCP tools cache (useful for testing)."""
    global _mcp_tools_cache
    _mcp_tools_cache = {}


def clear_mcp_server_tools_cache(server_name: str) -> None:
    """Clear the tools cache for a specific MCP server."""
    global _mcp_tools_cache
    _mcp_tools_cache.pop(server_name, None)
    logger.info(f"Cleared tools cache for MCP server '{server_name}'")
