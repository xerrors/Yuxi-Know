"""MCP 客户端、工具缓存与远端传输校验。"""

import asyncio
import hashlib
import json
import re
from collections.abc import Callable
from typing import Any, cast

from langchain_mcp_adapters.client import MultiServerMCPClient

from yuxi.infrastructure.observability.logging import logger

_mcp_lock = asyncio.Lock()


_mcp_tools_cache: dict[str, list[Callable[..., Any]]] = {}


_mcp_tools_stats: dict[str, dict[str, int]] = {}


SUPPORTED_TRANSPORTS = ("sse", "streamable_http")


def validate_remote_transport(config: dict[str, Any]) -> None:
    """在客户端与工具缓存边界拒绝非远程连接。"""
    if config.get("transport") not in SUPPORTED_TRANSPORTS:
        raise ValueError("MCP 仅支持 sse 或 streamable_http，不支持 stdio 等其他 transport")
    if set(config) & {"command", "args", "env"}:
        raise ValueError("远程 MCP 不支持 command、args 或 env 进程字段")


async def get_mcp_client(
    server_configs: dict[str, Any] | None = None,
) -> MultiServerMCPClient:
    """校验远程配置并创建客户端，初始化失败交由调用方处理。"""
    for config in (server_configs or {}).values():
        validate_remote_transport(config)
    client = MultiServerMCPClient(server_configs or {})  # pyright: ignore[reportArgumentType]
    logger.info(f"Initialized MCP client with servers: {list((server_configs or {}).keys())}")
    return client


def to_camel_case(s: str) -> str:
    """Convert string to lowerCamelCase."""

    # Handle - and _
    s = re.sub(r"[-_]+(.)", lambda m: m.group(1).upper(), s)
    # Lowercase first letter
    if len(s) > 0:
        s = s[0].lower() + s[1:]
    return s


async def get_mcp_tools(
    server_slug: str,
    server_config: dict[str, Any] | None,
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
        server_slug: Server slug
        additional_servers: Additional server configurations
        disabled_tools: List of tool names to filter out from the RETURN value (does not affect cache)
        cache: Whether to use/update the cache (default: True)
        force_refresh: Whether to force a refresh from the server (default: False)
    """
    if server_config is None:
        logger.warning(f"MCP server '{server_slug}' not found in database or disabled")
        return []

    validate_remote_transport(server_config)

    # 配置 hash 直接基于完整配置生成。只要数据库中的配置发生变化，
    # 本地工具缓存 key 就会变化，从而自然触发重建。
    config_payload = json.dumps(server_config, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    config_hash = hashlib.sha256(config_payload.encode("utf-8")).hexdigest()[:16]
    cache_key = f"{server_slug}:{config_hash}"

    all_processed_tools: list[Callable[..., Any]] = []

    async with _mcp_lock:
        if not force_refresh and cache and cache_key in _mcp_tools_cache:
            all_processed_tools = _mcp_tools_cache[cache_key]

    if not all_processed_tools:
        try:
            # disabled_tools 只影响返回值过滤，不参与 MCP client 建连参数。
            client_config = {k: v for k, v in server_config.items() if k not in ("disabled_tools",)}

            client = await get_mcp_client({server_slug: client_config})
            raw_tools = cast(list[Any], await client.get_tools())

            server_cc = to_camel_case(server_slug)
            for tool in raw_tools:
                original_name = tool.name
                tool_cc = to_camel_case(original_name)
                unique_id = f"mcp__{server_cc}__{tool_cc}"

                if tool.metadata is None:
                    tool.metadata = {}
                tool.metadata["id"] = unique_id
                # 开启错误处理，防止工具调用抛出 ToolException 时击穿服务
                tool.handle_tool_error = True
                all_processed_tools.append(tool)

            if cache:
                async with _mcp_lock:
                    stale_keys = [key for key in _mcp_tools_cache if key.startswith(f"{server_slug}:") and key != cache_key]
                    for stale_key in stale_keys:
                        _mcp_tools_cache.pop(stale_key, None)
                    _mcp_tools_cache[cache_key] = all_processed_tools

                global_config_disabled = server_config.get("disabled_tools") or []
                enabled_count = len([t for t in all_processed_tools if t.name not in global_config_disabled])
                _mcp_tools_stats[server_slug] = {
                    "total": len(all_processed_tools),
                    "enabled": enabled_count,
                    "disabled": len(all_processed_tools) - enabled_count,
                }

                logger.info(
                    f"Refreshed MCP tools cache for '{server_slug}' with key '{cache_key}': {len(all_processed_tools)} tools loaded."
                )

        except Exception as e:
            logger.bind(component="mcp", server_slug=server_slug, error_type=type(e).__name__, available=False).error(
                "component=mcp server_slug={} error_type={} available=false MCP 工具加载失败", server_slug, type(e).__name__
            )
            raise RuntimeError(f"MCP 服务 '{server_slug}' 工具加载失败") from e

    # 3. Filtering (Apply to Return Value Only)
    if disabled_tools:
        filtered_tools = [t for t in all_processed_tools if t.name not in disabled_tools]
        logger.debug(
            f"Returning {len(filtered_tools)}/{len(all_processed_tools)} tools for '{server_slug}' "
            f"(filtered {len(disabled_tools)} by argument)"
        )
        return filtered_tools

    return all_processed_tools


def clear_mcp_cache() -> None:
    """Clear the MCP tools cache (useful for testing)."""
    global _mcp_tools_cache, _mcp_tools_stats
    _mcp_tools_cache = {}
    _mcp_tools_stats = {}


def clear_mcp_server_tools_cache(server_slug: str) -> None:
    """Clear the tools cache for a specific MCP server."""
    global _mcp_tools_cache, _mcp_tools_stats
    server_prefix = f"{server_slug}:"
    stale_keys = [key for key in _mcp_tools_cache if key.startswith(server_prefix)]
    for stale_key in stale_keys:
        _mcp_tools_cache.pop(stale_key, None)
    _mcp_tools_stats.pop(server_slug, None)
    logger.info(f"Cleared tools cache for MCP server '{server_slug}'")


def get_mcp_tools_stats(server_slug: str) -> dict[str, int] | None:
    """Get tools statistics for a MCP server.

    Returns:
        dict with 'total', 'enabled', 'disabled' counts, or None if not available
    """
    return _mcp_tools_stats.get(server_slug)
