"""MCP Service - Unified business logic and state management for MCP.

Responsibilities:
- Server configuration CRUD operations
- Configuration synchronization (Database <-> Cache)
- Unified entry point for Agent tool retrieval (auto-filtering disabled_tools)
- MCP Client and Tools management (formerly in agents/common/mcp.py)
"""

import asyncio
import re
import traceback
from collections.abc import Callable
from typing import Any, cast

from langchain_mcp_adapters.client import MultiServerMCPClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.postgres.models_business import MCPServer
from src.utils import logger

# =============================================================================
# === Global Cache & State ===
# =============================================================================

# Global Lock for MCP state
_mcp_lock = asyncio.Lock()

# Global MCP tools cache
_mcp_tools_cache: dict[str, list[Callable[..., Any]]] = {}

# MCP tools statistics (for reporting enabled/disabled counts)
_mcp_tools_stats: dict[str, dict[str, int]] = {}

# MCP Server configurations (Runtime cache, loaded from DB)
MCP_SERVERS: dict[str, dict[str, Any]] = {}

# Default MCP Server configurations (Imported to DB on first run)
_DEFAULT_MCP_SERVERS = {
    "sequentialthinking": {
        "url": "https://remote.mcpservers.org/sequentialthinking/mcp",
        "transport": "streamable_http",
        "description": "顺序思考工具，帮助 AI 将复杂问题分解为多个步骤",
        "icon": "🧠",
        "tags": ["内置", "AI"],
    },
    "mcp-server-chart": {
        "command": "npx",
        "args": ["-y", "@antv/mcp-server-chart"],
        "transport": "stdio",
        "description": "图表生成工具，支持生成各类图表（柱状图、折线图、饼图等）",
        "icon": "📊",
        "tags": ["内置", "图表"],
    },
}

# =============================================================================
# === Core Logic (Moved from agents/common/mcp.py) ===
# =============================================================================


async def load_mcp_servers_from_db() -> None:
    """Load all enabled MCP server configurations from database to MCP_SERVERS cache."""
    global MCP_SERVERS

    # Delayed import to avoid circular references
    from src.storage.postgres.manager import pg_manager

    try:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(MCPServer).filter(MCPServer.enabled == 1))
            servers = result.scalars().all()

            async with _mcp_lock:
                MCP_SERVERS.clear()
                for server in servers:
                    MCP_SERVERS[server.name] = server.to_mcp_config()

            logger.info(f"Loaded {len(MCP_SERVERS)} MCP servers from database: {list(MCP_SERVERS.keys())}")
    except Exception as e:
        logger.error(f"Failed to load MCP servers from database: {e}")


async def sync_mcp_server_to_cache(name: str, config: dict[str, Any] | None) -> None:
    """Sync a single MCP server configuration to cache.

    Args:
        name: Server name
        config: Server configuration, or None to remove from cache
    """
    global MCP_SERVERS

    async with _mcp_lock:
        if config is None:
            MCP_SERVERS.pop(name, None)
            logger.info(f"Removed MCP server '{name}' from cache")
        else:
            MCP_SERVERS[name] = config
            logger.info(f"Synced MCP server '{name}' to cache")

        # Clear tools cache for this server
        _mcp_tools_cache.pop(name, None)


async def init_mcp_servers() -> None:
    """Initialize MCP server configurations.

    On first run, if database is empty, import default configurations.
    Then load configurations from database to MCP_SERVERS cache.
    Also ensures all built-in MCP servers are present in the database.
    """
    # Delayed import to avoid circular references
    from src.storage.postgres.manager import pg_manager

    try:
        async with pg_manager.get_async_session_context() as session:
            # Check if database has MCP configurations
            result = await session.execute(select(func.count(MCPServer.name)))
            count = result.scalar()

            if count == 0:
                # Database is empty, import default configurations
                logger.info("No MCP servers in database, importing default configurations...")
                for name, config in _DEFAULT_MCP_SERVERS.items():
                    server = MCPServer(
                        name=name,
                        description=config.get("description"),
                        transport=config["transport"],
                        url=config.get("url"),
                        command=config.get("command"),
                        args=config.get("args"),
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
            else:
                # Ensure all built-in MCP servers exist in database
                for name, config in _DEFAULT_MCP_SERVERS.items():
                    result = await session.execute(select(MCPServer).filter(MCPServer.name == name))
                    existing = result.scalar_one_or_none()
                    if not existing:
                        server = MCPServer(
                            name=name,
                            description=config.get("description"),
                            transport=config["transport"],
                            url=config.get("url"),
                            command=config.get("command"),
                            args=config.get("args"),
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
                        logger.info(f"Added built-in MCP server '{name}' to database")
                # Commit if any new servers were added (check session state)
                if session.new:
                    await session.commit()

        # Load configurations from database to cache
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
    """Convert string to lowerCamelCase."""

    # Handle - and _
    s = re.sub(r"[-_]+(.)", lambda m: m.group(1).upper(), s)
    # Lowercase first letter
    if len(s) > 0:
        s = s[0].lower() + s[1:]
    return s


async def get_mcp_tools(
    server_name: str,
    additional_servers: dict[str, dict] = None,
    disabled_tools: list[str] = None,
    cache: bool = True,
    force_refresh: bool = False,
) -> list[Callable[..., Any]]:
    """Get MCP tools for a specific server.

    Architecture:
    1. Fetching: Connects to MCP server to get ALL tools.
    2. Caching: Stores the FULL, UNFILTERED list of tools in `_mcp_tools_cache`.
    3. Filtering: Filters the return value based on `disabled_tools` argument.

    Args:
        server_name: Server name
        additional_servers: Additional server configurations
        disabled_tools: List of tool names to filter out from the RETURN value (does not affect cache)
        cache: Whether to use/update the cache (default: True)
        force_refresh: Whether to force a refresh from the server (default: False)
    """
    global _mcp_tools_cache

    # 1. Prepare Server Config
    async with _mcp_lock:
        mcp_servers = MCP_SERVERS | (additional_servers or {})

    all_processed_tools = []

    # 2. Check Cache / Fetch Strategy
    # If we have it in cache and don't need to force refresh, use cache.
    if not force_refresh and cache and server_name in _mcp_tools_cache:
        all_processed_tools = _mcp_tools_cache[server_name]
    else:
        # Need to fetch from server
        try:
            assert server_name in mcp_servers, f"Server {server_name} not found in ({list(mcp_servers.keys())})"

            # Extract connection config
            server_config = mcp_servers[server_name]
            client_config = {k: v for k, v in server_config.items() if k not in ("disabled_tools",)}

            client = await get_mcp_client({server_name: client_config})
            if client is None:
                return []

            # Get ALL tools (Raw)
            raw_tools = cast(list[Any], await client.get_tools())

            # Render IDs for ALL tools
            server_cc = to_camel_case(server_name)
            for tool in raw_tools:
                # Render unique ID rule: mcp__[camelCaseServer]__[camelCaseTool]
                original_name = tool.name
                tool_cc = to_camel_case(original_name)
                unique_id = f"mcp__{server_cc}__{tool_cc}"

                # Use metadata to store
                if tool.metadata is None:
                    tool.metadata = {}
                tool.metadata["id"] = unique_id

                all_processed_tools.append(tool)

            # Update Cache (Store the FULL list)
            if cache:
                _mcp_tools_cache[server_name] = all_processed_tools

                # Update Stats
                # Stats should reflect the GLOBAL configuration state
                # (How many are disabled in the stored config, not the transient arg)
                global_config_disabled = mcp_servers.get(server_name, {}).get("disabled_tools") or []
                enabled_count = len([t for t in all_processed_tools if t.name not in global_config_disabled])

                _mcp_tools_stats[server_name] = {
                    "total": len(all_processed_tools),
                    "enabled": enabled_count,
                    "disabled": len(all_processed_tools) - enabled_count,
                }

                logger.info(f"Refreshed MCP tools cache for '{server_name}': {len(all_processed_tools)} tools loaded.")

        except AssertionError as e:
            logger.warning(f"[assert] Failed to load tools from MCP server '{server_name}': {e}")
            return []
        except Exception as e:
            logger.error(
                f"Failed to load tools from MCP server '{server_name}': {e}, traceback: {traceback.format_exc()}"
            )
            return []

    # 3. Filtering (Apply to Return Value Only)
    if disabled_tools:
        filtered_tools = [t for t in all_processed_tools if t.name not in disabled_tools]
        logger.debug(
            f"Returning {len(filtered_tools)}/{len(all_processed_tools)} tools for '{server_name}' "
            f"(filtered {len(disabled_tools)} by argument)"
        )
        return filtered_tools

    return all_processed_tools


async def get_tools_from_all_servers() -> list[Callable[..., Any]]:
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
    global _mcp_tools_cache, _mcp_tools_stats
    _mcp_tools_cache = {}
    _mcp_tools_stats = {}


def clear_mcp_server_tools_cache(server_name: str) -> None:
    """Clear the tools cache for a specific MCP server."""
    global _mcp_tools_cache, _mcp_tools_stats
    _mcp_tools_cache.pop(server_name, None)
    _mcp_tools_stats.pop(server_name, None)
    logger.info(f"Cleared tools cache for MCP server '{server_name}'")


def get_mcp_tools_stats(server_name: str) -> dict[str, int] | None:
    """Get tools statistics for a MCP server.

    Returns:
        dict with 'total', 'enabled', 'disabled' counts, or None if not available
    """
    return _mcp_tools_stats.get(server_name)


# =============================================================================
# === Server Config CRUD (Existing in mcp_service.py) ===
# =============================================================================


async def get_mcp_server(db: AsyncSession, name: str) -> MCPServer | None:
    """Get single server configuration."""
    result = await db.execute(select(MCPServer).filter(MCPServer.name == name))
    return result.scalar_one_or_none()


async def get_all_mcp_servers(db: AsyncSession) -> list[MCPServer]:
    """Get all server configurations."""
    result = await db.execute(select(MCPServer))
    return list(result.scalars().all())


async def create_mcp_server(
    db: AsyncSession,
    name: str,
    transport: str,
    url: str = None,
    command: str = None,
    args: list = None,
    description: str = None,
    headers: dict = None,
    timeout: int = None,
    sse_read_timeout: int = None,
    tags: list = None,
    icon: str = None,
    created_by: str = None,
) -> MCPServer:
    """Create server."""
    # Check if name exists
    existing = await get_mcp_server(db, name)
    if existing:
        raise ValueError(f"Server name '{name}' already exists")

    server = MCPServer(
        name=name,
        description=description,
        transport=transport,
        url=url,
        command=command,
        args=args,
        headers=headers,
        timeout=timeout,
        sse_read_timeout=sse_read_timeout,
        tags=tags,
        icon=icon,
        enabled=1,
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(server)
    await db.commit()
    await db.refresh(server)

    # Sync to cache
    await sync_mcp_server_to_cache(name, server.to_mcp_config())

    logger.info(f"Created MCP server '{name}'")
    return server


async def update_mcp_server(
    db: AsyncSession,
    name: str,
    description: str = None,
    transport: str = None,
    url: str = None,
    command: str = None,
    args: list = None,
    headers: dict = None,
    timeout: int = None,
    sse_read_timeout: int = None,
    tags: list = None,
    icon: str = None,
    updated_by: str = None,
) -> MCPServer:
    """Update server configuration."""
    server = await get_mcp_server(db, name)
    if not server:
        raise ValueError(f"Server '{name}' does not exist")

    if description is not None:
        server.description = description
    if transport is not None:
        server.transport = transport
    if url is not None:
        server.url = url
    if command is not None:
        server.command = command
    if args is not None:
        server.args = args
    if headers is not None:
        server.headers = headers
    if timeout is not None:
        server.timeout = timeout
    if sse_read_timeout is not None:
        server.sse_read_timeout = sse_read_timeout
    if tags is not None:
        server.tags = tags
    if icon is not None:
        server.icon = icon
    if updated_by is not None:
        server.updated_by = updated_by

    await db.commit()
    await db.refresh(server)

    # Sync to cache (if enabled)
    if server.enabled:
        await sync_mcp_server_to_cache(name, server.to_mcp_config())

    logger.info(f"Updated MCP server '{name}'")
    return server


async def delete_mcp_server(db: AsyncSession, name: str) -> bool:
    """Delete server."""
    server = await get_mcp_server(db, name)
    if not server:
        return False

    await db.delete(server)
    await db.commit()

    # Remove from cache
    await sync_mcp_server_to_cache(name, None)

    logger.info(f"Deleted MCP server '{name}'")
    return True


# =============================================================================
# === Tool Management ===
# =============================================================================


async def toggle_server_enabled(db: AsyncSession, name: str, updated_by: str = None) -> tuple[bool, MCPServer]:
    """Toggle server enabled status."""
    server = await get_mcp_server(db, name)
    if not server:
        raise ValueError(f"Server '{name}' does not exist")

    server.enabled = 0 if server.enabled else 1
    if updated_by is not None:
        server.updated_by = updated_by
    await db.commit()

    # Sync to cache
    is_enabled = bool(server.enabled)
    server_config = server.to_mcp_config() if is_enabled else None
    await sync_mcp_server_to_cache(name, server_config)

    logger.info(f"Toggled MCP server '{name}' enabled={is_enabled}")
    return is_enabled, server


async def toggle_tool_enabled(
    db: AsyncSession,
    server_name: str,
    tool_name: str,
    updated_by: str = None,
) -> tuple[bool, MCPServer]:
    """Toggle single tool enabled status.

    Args:
        db: Database session
        server_name: Server name
        tool_name: Tool name
        updated_by: Updater

    Returns:
        (enabled, server): Tool enabled status and updated server object
    """
    server = await get_mcp_server(db, server_name)
    if not server:
        raise ValueError(f"Server '{server_name}' does not exist")

    disabled_tools = list(server.disabled_tools or [])

    if tool_name in disabled_tools:
        disabled_tools.remove(tool_name)
        enabled = True
    else:
        disabled_tools.append(tool_name)
        enabled = False

    server.disabled_tools = disabled_tools
    if updated_by is not None:
        server.updated_by = updated_by
    await db.commit()

    # Clear tool cache (re-filtered on next fetch)
    clear_mcp_server_tools_cache(server_name)

    logger.info(f"Toggled tool '{tool_name}' for server '{server_name}' enabled={enabled}")
    return enabled, server


# =============================================================================
# === Unified Entry Points (Wrappers) ===
# =============================================================================


def get_mcp_server_names() -> list[str]:
    """Get list of loaded MCP server names.

    Returns a copy of keys to avoid runtime modification issues during iteration.
    """
    return list(MCP_SERVERS.keys())


async def get_enabled_mcp_tools(server_name: str) -> list:
    """Get MCP server tools (auto-filtering disabled_tools).

    Unified entry point for Agents, automatically:
    1. Gets server config from cache
    2. Gets all tools
    3. Filters out disabled_tools

    Args:
        server_name: Server name

    Returns:
        List of enabled tools
    """
    config = MCP_SERVERS.get(server_name)
    if not config:
        logger.warning(f"MCP server '{server_name}' not found in cache")
        return []

    disabled_tools = config.get("disabled_tools") or []
    return await get_mcp_tools(server_name, disabled_tools=disabled_tools)


async def get_servers_config(names: list[str]) -> dict[str, dict[str, Any]]:
    """Batch get server configurations.

    Args:
        names: List of server names

    Returns:
        {name: config} dictionary, containing only found servers
    """
    return {name: MCP_SERVERS[name] for name in names if name in MCP_SERVERS}


async def get_all_mcp_tools(server_name: str) -> list:
    """Get all tools of an MCP server (no filtering).

    For management UI to display tool list, supports viewing all tools and their enabled status.
    Does NOT update the global tools cache to avoid polluting agent's filtered view.

    Args:
        server_name: Server name

    Returns:
        List of all tools (unfiltered)
    """
    config = MCP_SERVERS.get(server_name)
    if not config:
        logger.warning(f"MCP server '{server_name}' not found in cache")
        return []

    # Get all tools (no filtering, force refresh, no cache update)
    return await get_mcp_tools(server_name, disabled_tools=[], cache=False, force_refresh=True)
