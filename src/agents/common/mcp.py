"""MCP Client setup and management for LangGraph ReAct Agent."""

import traceback
from collections.abc import Callable
from typing import Any, cast

from langchain_mcp_adapters.client import MultiServerMCPClient

from src.utils import logger

# Global MCP tools cache
_mcp_tools_cache: dict[str, list[Callable[..., Any]]] = {}

# MCP Server configurations
MCP_SERVERS = {
    "sequentialthinking": {
        "url": "https://remote.mcpservers.org/sequentialthinking/mcp",
        "transport": "streamable_http",
    },
    # "zhipu-web-search-sse": {
    #     "url": f"https://open.bigmodel.cn/api/mcp/web_search/sse?Authorization={os.getenv('ZHIPUAI_API_KEY')}",
    #     "transport": "streamable_http",
    # },
    # 这些 stdio 的 MCP server 需要在本地启动，启动的时候需要安装对应的包，需要时间
    # "time": {
    #     "command": "uvx",
    #     "args": ["mcp-server-time"],
    #     "transport": "stdio",
    # },
    # "mcp_server_chart": {
    #     "command": "npx",
    #     "args": ["-y", "@antv/mcp-server-chart"],
    #     "transport": "stdio"
    # },
    # 更多用法参考：https://xerrors.github.io/Yuxi-Know/latest/advanced/agents-config.html#内置工具与-mcp-集成
}


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


async def get_mcp_tools(server_name: str, additional_servers: dict[str, dict] = None) -> list[Callable[..., Any]]:
    """Get MCP tools for a specific server, initializing client if needed."""
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

        # Get all tools and filter by server (if tools have server metadata)
        all_tools = await client.get_tools()
        tools = cast(list[Callable[..., Any]], all_tools)

        _mcp_tools_cache[server_name] = tools
        logger.info(f"Loaded {len(tools)} tools from MCP server '{server_name}'")
        return tools
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
