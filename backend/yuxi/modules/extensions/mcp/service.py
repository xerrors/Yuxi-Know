"""MCP Service - Unified business logic and state management for MCP.

Responsibilities:
- Server configuration CRUD operations
- Built-in configuration synchronization (Code <-> Database)
- Unified entry point for Agent tool retrieval (auto-filtering disabled_tools)
- MCP Client and Tools management (formerly in agents/common/mcp.py)
"""

from collections.abc import Callable
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.infrastructure.observability.logging import logger
from yuxi.modules.extensions.mcp.builtin import BUILTIN_MCP_MANIFEST
from yuxi.modules.extensions.mcp.config import RemoteMCPConfig, normalize_mcp_manifest_entry
from yuxi.modules.extensions.mcp.models import MCPServer
from yuxi.modules.extensions.mcp.repository import (
    delete_mcp_server_row,
    get_mcp_server,
    save_mcp_server,
)
from yuxi.modules.extensions.mcp.runtime import (
    SUPPORTED_TRANSPORTS,
    clear_mcp_server_tools_cache,
    to_camel_case,
    validate_remote_transport,
)
from yuxi.modules.extensions.mcp.runtime import (
    get_mcp_tools as load_mcp_tools,
)

BUILTIN_MCP_SERVERS = BUILTIN_MCP_MANIFEST["mcpServers"]

_SYNCED_MCP_FIELDS = (
    "name",
    "description",
    "transport",
    "url",
    "headers",
    "timeout",
    "sse_read_timeout",
    "tags",
    "icon",
)


class MCPServerNotFoundError(ValueError):
    """表示指定的 MCP 服务器不存在。"""


def is_builtin_mcp_server(server: MCPServer) -> bool:
    """判断 MCP 是否由代码中的内置定义管理。"""
    return server.slug in BUILTIN_MCP_SERVERS


# =============================================================================
# === Core Logic (Moved from agents/common/mcp.py) ===
# =============================================================================


async def ensure_builtin_mcp_servers_in_db() -> None:
    """Ensure built-in MCP server definitions exist in the database."""
    from yuxi.infrastructure.postgres.manager import pg_manager

    async with pg_manager.get_async_session_context() as session:
        any_changed = False

        for slug, entry in BUILTIN_MCP_SERVERS.items():
            config = normalize_mcp_manifest_entry(slug, entry)
            result = await session.execute(select(MCPServer).filter(MCPServer.slug == slug))
            existing = result.scalar_one_or_none()
            if not existing:
                session.add(
                    MCPServer(
                        slug=slug,
                        name=config.get("name", slug),
                        description=config.get("description"),
                        transport=config["transport"],
                        url=config.get("url"),
                        headers=config.get("headers"),
                        timeout=config.get("timeout"),
                        sse_read_timeout=config.get("sse_read_timeout"),
                        tags=config.get("tags"),
                        icon=config.get("icon"),
                        enabled=0,
                        created_by="system",
                        updated_by="system",
                    )
                )
                any_changed = True
                logger.info(f"Added built-in MCP server '{slug}' to database")
                continue

            server_changed = False
            for field in _SYNCED_MCP_FIELDS:
                next_value = config.get(field)
                if getattr(existing, field) != next_value:
                    setattr(existing, field, next_value)
                    server_changed = True
            if existing.created_by != "system":
                existing.created_by = "system"
                server_changed = True
            if server_changed:
                existing.updated_by = "system"
                any_changed = True

        if any_changed:
            await session.commit()


async def _load_enabled_mcp_server_configs(
    *,
    names: list[str] | None = None,
    db: AsyncSession | None = None,
) -> dict[str, dict[str, Any]]:
    """Load enabled MCP server configs directly from the database."""
    if db is not None:
        stmt = select(MCPServer).where(
            MCPServer.enabled == 1,
            MCPServer.transport.in_(SUPPORTED_TRANSPORTS),
        )
        if names:
            stmt = stmt.where(MCPServer.slug.in_(names))
        result = await db.execute(stmt)
        servers = result.scalars().all()
        return {server.slug: _to_runtime_mcp_config(server) for server in servers}

    from yuxi.infrastructure.postgres.manager import pg_manager

    async with pg_manager.get_async_session_context() as session:
        return await _load_enabled_mcp_server_configs(names=names, db=session)


async def get_enabled_mcp_server_config(server_slug: str, *, db: AsyncSession | None = None) -> dict[str, Any] | None:
    """Get the latest enabled MCP server config from the database."""
    configs = await _load_enabled_mcp_server_configs(names=[server_slug], db=db)
    return configs.get(server_slug)


async def get_enabled_mcp_server_slugs(*, db: AsyncSession | None = None) -> list[str]:
    """Get enabled MCP server slugs from the database."""
    if db is not None:
        result = await db.execute(
            select(MCPServer.slug).where(
                MCPServer.enabled == 1,
                MCPServer.transport.in_(SUPPORTED_TRANSPORTS),
            )
        )
        return [name for name in result.scalars().all() if isinstance(name, str)]

    from yuxi.infrastructure.postgres.manager import pg_manager

    async with pg_manager.get_async_session_context() as session:
        return await get_enabled_mcp_server_slugs(db=session)


async def get_mcp_tools(
    server_slug: str,
    additional_servers: dict[str, dict[str, Any]] | None = None,
    disabled_tools: list[str] | None = None,
    cache: bool = True,
    force_refresh: bool = False,
) -> list[Callable[..., Any]]:
    """读取已启用配置，再交由运行适配器加载并过滤工具。"""
    config = (
        additional_servers.get(server_slug)
        if additional_servers and server_slug in additional_servers
        else await get_enabled_mcp_server_config(server_slug)
    )
    return await load_mcp_tools(server_slug, config, disabled_tools=disabled_tools, cache=cache, force_refresh=force_refresh)


# =============================================================================
# === Server Config CRUD ===
# =============================================================================


async def create_mcp_server(
    db: AsyncSession,
    slug: str,
    name: str,
    transport: str,
    url: str = None,
    description: str = None,
    headers: dict = None,
    timeout: int = None,
    sse_read_timeout: int = None,
    tags: list = None,
    icon: str = None,
    created_by: str = None,
) -> MCPServer:
    """创建并独立发布远程 MCP 配置。"""
    if slug in BUILTIN_MCP_SERVERS:
        raise ValueError("系统内置 MCP 的 slug 由代码保留，无法通过接口创建")
    config = RemoteMCPConfig.model_validate(
        dict(
            slug=slug,
            name=name,
            transport=transport,
            url=url,
            description=description,
            headers=headers,
            timeout=timeout,
            sse_read_timeout=sse_read_timeout,
            tags=tags,
            icon=icon,
        )
    ).model_dump()

    existing = await get_mcp_server(db, slug)
    if existing:
        raise ValueError(f"Server slug '{slug}' already exists")

    server = MCPServer(
        **config,
        enabled=1,
        created_by=created_by,
        updated_by=created_by,
    )
    await save_mcp_server(db, server, new=True)
    await db.commit()
    await db.refresh(server)
    clear_mcp_server_tools_cache(slug)
    logger.info(f"Created MCP server '{slug}'")
    return server


async def update_mcp_server(
    db: AsyncSession,
    slug: str,
    name: str = None,
    description: str = None,
    transport: str = None,
    url: str = None,
    headers: dict = None,
    timeout: int = None,
    sse_read_timeout: int = None,
    tags: list = None,
    icon: str = None,
    updated_by: str = None,
) -> MCPServer:
    """Update server configuration."""
    server = await get_mcp_server(db, slug)
    if not server:
        raise MCPServerNotFoundError(f"Server '{slug}' does not exist")
    if is_builtin_mcp_server(server):
        raise PermissionError("系统内置 MCP 的连接配置由代码管理，无法通过接口修改")

    updates = dict(
        name=name,
        description=description,
        transport=transport,
        url=url,
        headers=headers,
        timeout=timeout,
        sse_read_timeout=sse_read_timeout,
        tags=tags,
        icon=icon,
    )
    current = {field: getattr(server, field) for field in RemoteMCPConfig.model_fields}
    RemoteMCPConfig.model_validate({**current, **{key: value for key, value in updates.items() if value is not None}})

    for field, value in updates.items():
        if value is not None:
            setattr(server, field, value)
    if updated_by is not None:
        server.updated_by = updated_by

    await db.commit()
    await db.refresh(server)

    clear_mcp_server_tools_cache(slug)

    logger.info(f"Updated MCP server '{slug}'")
    return server


async def delete_mcp_server(db: AsyncSession, slug: str) -> bool:
    """删除 MCP 服务器，内置服务器由代码管理。"""
    server = await get_mcp_server(db, slug)
    if not server:
        return False
    if is_builtin_mcp_server(server):
        raise PermissionError("系统内置 MCP 的连接配置由代码管理，无法删除")

    await delete_mcp_server_row(db, server)
    await db.commit()

    clear_mcp_server_tools_cache(slug)

    logger.info(f"Deleted MCP server '{slug}'")
    return True


# =============================================================================
# === Tool Management ===
# =============================================================================


async def set_server_enabled(db: AsyncSession, slug: str, enabled: bool, updated_by: str = None) -> tuple[bool, MCPServer]:
    """Set server enabled status."""
    server = await get_mcp_server(db, slug)
    if not server:
        raise MCPServerNotFoundError(f"Server '{slug}' does not exist")
    server.enabled = 1 if enabled else 0
    if updated_by is not None:
        server.updated_by = updated_by
    await db.commit()

    is_enabled = bool(server.enabled)
    clear_mcp_server_tools_cache(slug)

    logger.info(f"Set MCP server '{slug}' enabled={is_enabled}")
    return is_enabled, server


async def toggle_tool_enabled(
    db: AsyncSession,
    server_slug: str,
    tool_name: str,
    updated_by: str = None,
) -> tuple[bool, MCPServer]:
    """Toggle single tool enabled status.

    Args:
        db: Database session
        server_slug: Server slug
        tool_name: Tool name
        updated_by: Updater

    Returns:
        (enabled, server): Tool enabled status and updated server object
    """
    server = await get_mcp_server(db, server_slug)
    if not server:
        raise MCPServerNotFoundError(f"Server '{server_slug}' does not exist")

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
    clear_mcp_server_tools_cache(server_slug)

    logger.info(f"Toggled tool '{tool_name}' for server '{server_slug}' enabled={enabled}")
    return enabled, server


# =============================================================================
# === Unified Entry Points (Wrappers) ===
# =============================================================================


async def get_enabled_mcp_tools(server_slug: str) -> list:
    """Get MCP server tools (auto-filtering disabled_tools).

    Unified entry point for Agents, automatically:
    1. Gets the latest server config from database
    2. Gets all tools
    3. Filters out disabled_tools

    Args:
        server_slug: Server slug

    Returns:
        List of enabled tools
    """
    config = await get_enabled_mcp_server_config(server_slug)
    disabled_tools = (config or {}).get("disabled_tools") or []
    return await get_mcp_tools(server_slug, additional_servers={server_slug: config}, disabled_tools=disabled_tools)


async def get_all_mcp_tools(server_slug: str) -> list:
    """Get all tools of an MCP server (no filtering).

    For management UI to display tool list, supports viewing all tools and their enabled status.
    Does NOT update the global tools cache to avoid polluting agent's filtered view.

    Args:
        server_slug: Server slug

    Returns:
        List of all tools (unfiltered)
    """
    config = await get_enabled_mcp_server_config(server_slug)
    # Get all tools (no filtering, force refresh, no cache update)
    return await get_mcp_tools(
        server_slug,
        additional_servers={server_slug: config},
        disabled_tools=[],
        cache=False,
        force_refresh=True,
    )


async def inspect_mcp_server_tools(server: MCPServer) -> list:
    """管理端严格建连，包括停用服务；不吞异常、不修改状态或运行缓存。"""
    config = {key: value for key, value in _to_runtime_mcp_config(server).items() if key != "disabled_tools"}
    validate_remote_transport(config)
    client = MultiServerMCPClient({server.slug: config})
    tools = await client.get_tools()
    for tool in tools:
        if tool.metadata is None:
            tool.metadata = {}
        tool.metadata["id"] = f"mcp__{to_camel_case(server.slug)}__{to_camel_case(tool.name)}"
    return tools


def _to_runtime_mcp_config(server: MCPServer) -> dict[str, Any]:
    """生成运行时 MCP 配置，内置连接字段始终以代码定义为准。"""
    if not is_builtin_mcp_server(server):
        return server.to_mcp_config()

    builtin = normalize_mcp_manifest_entry(server.slug, BUILTIN_MCP_SERVERS[server.slug])
    config = {key: builtin[key] for key in ("transport", "url", "headers", "timeout", "sse_read_timeout") if builtin.get(key) is not None}
    if server.disabled_tools:
        config["disabled_tools"] = server.disabled_tools
    return config
