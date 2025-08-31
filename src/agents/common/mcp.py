"""MCP Client setup and management for LangGraph ReAct Agent."""

import traceback
from typing import Any, cast
from collections.abc import Callable

from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_mcp_adapters.client import (  # type: ignore[import-untyped]
    MultiServerMCPClient,
)

from src.utils import logger

# Global MCP client and tools cache
_mcp_client: MultiServerMCPClient | None = None
_mcp_tools_cache: dict[str, list[Callable[..., Any]]] = {}

# MCP Server configurations
MCP_SERVERS = {
    "deepwiki": {
        "url": "https://mcp.deepwiki.com/mcp",
        "transport": "streamable_http",
    },
    # Add more MCP servers here as needed
    "sequentialthinking": {
        "url": "https://remote.mcpservers.org/sequentialthinking/mcp",
        "transport": "streamable_http",
    },
    "time": {
        "command": "uvx",
        "args": ["mcp-server-time"],
        "transport": "stdio",
    }
}


async def get_mcp_client(
    server_configs: dict[str, Any] | None = None,
) -> MultiServerMCPClient | None:
    """Get or initialize the global MCP client with given server configurations."""
    global _mcp_client

    if _mcp_client is None:
        configs = server_configs or MCP_SERVERS
        try:
            _mcp_client = MultiServerMCPClient(configs)  # pyright: ignore[reportArgumentType]
            logger.info(f"Initialized MCP client with servers: {list(configs.keys())}")
        except Exception as e:
            logger.error("Failed to initialize MCP client: %s", e)
            return None
    return _mcp_client


async def get_mcp_tools(server_name: str) -> list[Callable[..., Any]]:
    """Get MCP tools for a specific server, initializing client if needed."""
    global _mcp_tools_cache

    # Return cached tools if available
    if server_name in _mcp_tools_cache:
        return _mcp_tools_cache[server_name]

    try:
        client = await get_mcp_client({server_name: MCP_SERVERS[server_name]})
        if client is None:
            _mcp_tools_cache[server_name] = []
            return []

        # Get all tools and filter by server (if tools have server metadata)
        all_tools = await client.get_tools()
        tools = cast(list[Callable[..., Any]], all_tools)

        _mcp_tools_cache[server_name] = tools
        logger.info(f"Loaded {len(tools)} tools from MCP server '{server_name}'")
        return tools
    except Exception as e:
        logger.warning(f"Failed to load tools from MCP server '{server_name}': %s\n{traceback.format_exc()}", e)
        _mcp_tools_cache[server_name] = []
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
    """Clear the MCP client and tools cache (useful for testing)."""
    global _mcp_client, _mcp_tools_cache
    _mcp_client = None
    _mcp_tools_cache = {}
