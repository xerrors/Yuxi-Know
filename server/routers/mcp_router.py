"""MCP 服务器管理路由"""

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.common.mcp import (
    clear_mcp_server_tools_cache,
    get_mcp_tools,
    sync_mcp_server_to_cache,
)
from src.storage.db.models import MCPServer, User
from src.utils import logger
from server.utils.auth_middleware import get_admin_user, get_db

mcp = APIRouter(prefix="/system/mcp-servers", tags=["mcp"])


# =============================================================================
# === MCP 服务器 CRUD ===
# =============================================================================


@mcp.get("")
async def get_mcp_servers(
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """获取所有 MCP 服务器配置"""
    try:
        result = await db.execute(select(MCPServer))
        servers = result.scalars().all()
        return {"success": True, "data": [s.to_dict() for s in servers]}
    except Exception as e:
        logger.error(f"Failed to get MCP servers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@mcp.post("")
async def create_mcp_server(
    name: str = Body(..., description="服务器名称"),
    transport: str = Body(..., description="传输类型：sse/streamable_http"),
    url: str = Body(..., description="服务器 URL"),
    description: str = Body(None, description="描述"),
    headers: dict = Body(None, description="HTTP 请求头"),
    timeout: int = Body(None, description="HTTP 超时时间（秒）"),
    sse_read_timeout: int = Body(None, description="SSE 读取超时（秒）"),
    tags: list = Body(None, description="标签数组"),
    icon: str = Body(None, description="图标（emoji）"),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """创建新的 MCP 服务器"""
    # 校验传输类型
    if transport not in ("sse", "streamable_http"):
        raise HTTPException(status_code=400, detail="传输类型必须是 sse 或 streamable_http")

    try:
        # 检查名称是否已存在
        result = await db.execute(select(MCPServer).filter(MCPServer.name == name))
        existing = result.scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail=f"服务器名称 '{name}' 已存在")

        server = MCPServer(
            name=name,
            description=description,
            transport=transport,
            url=url,
            headers=headers,
            timeout=timeout,
            sse_read_timeout=sse_read_timeout,
            tags=tags,
            icon=icon,
            enabled=1,
            created_by=current_user.username,
            updated_by=current_user.username,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)

        # 同步到缓存
        sync_mcp_server_to_cache(name, server.to_mcp_config())

        return {"success": True, "data": server.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create MCP server: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@mcp.get("/{name}")
async def get_mcp_server(
    name: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """获取单个 MCP 服务器配置"""
    try:
        result = await db.execute(select(MCPServer).filter(MCPServer.name == name))
        server = result.scalar_one_or_none()
        if not server:
            raise HTTPException(status_code=404, detail=f"服务器 '{name}' 不存在")
        return {"success": True, "data": server.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get MCP server: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@mcp.put("/{name}")
async def update_mcp_server(
    name: str,
    description: str = Body(None, description="描述"),
    transport: str = Body(None, description="传输类型"),
    url: str = Body(None, description="服务器 URL"),
    headers: dict = Body(None, description="HTTP 请求头"),
    timeout: int = Body(None, description="HTTP 超时时间（秒）"),
    sse_read_timeout: int = Body(None, description="SSE 读取超时（秒）"),
    tags: list = Body(None, description="标签数组"),
    icon: str = Body(None, description="图标（emoji）"),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """更新 MCP 服务器配置"""
    # 校验传输类型
    if transport is not None and transport not in ("sse", "streamable_http"):
        raise HTTPException(status_code=400, detail="传输类型必须是 sse 或 streamable_http")

    try:
        result = await db.execute(select(MCPServer).filter(MCPServer.name == name))
        server = result.scalar_one_or_none()
        if not server:
            raise HTTPException(status_code=404, detail=f"服务器 '{name}' 不存在")

        # 更新字段
        if description is not None:
            server.description = description
        if transport is not None:
            server.transport = transport
        if url is not None:
            server.url = url
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

        server.updated_by = current_user.username
        await db.commit()
        await db.refresh(server)

        # 同步到缓存（如果启用）
        if server.enabled:
            sync_mcp_server_to_cache(name, server.to_mcp_config())

        return {"success": True, "data": server.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update MCP server: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@mcp.delete("/{name}")
async def delete_mcp_server(
    name: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """删除 MCP 服务器"""
    try:
        result = await db.execute(select(MCPServer).filter(MCPServer.name == name))
        server = result.scalar_one_or_none()
        if not server:
            raise HTTPException(status_code=404, detail=f"服务器 '{name}' 不存在")

        await db.delete(server)
        await db.commit()

        # 从缓存中删除
        sync_mcp_server_to_cache(name, None)

        return {"success": True, "message": f"服务器 '{name}' 已删除"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete MCP server: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# === MCP 服务器操作 ===
# =============================================================================


@mcp.post("/{name}/test")
async def test_mcp_server(
    name: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """测试 MCP 服务器连接"""
    try:
        result = await db.execute(select(MCPServer).filter(MCPServer.name == name))
        server = result.scalar_one_or_none()
        if not server:
            raise HTTPException(status_code=404, detail=f"服务器 '{name}' 不存在")

        # 获取配置用于测试
        config = server.to_mcp_config()

        try:
            tools = await get_mcp_tools(name, {name: config})
            return {
                "success": True,
                "message": f"连接成功，共发现 {len(tools)} 个工具",
                "tool_count": len(tools),
            }
        except Exception as test_error:
            return {
                "success": False,
                "message": f"连接失败: {str(test_error)}",
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test MCP server: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@mcp.put("/{name}/toggle")
async def toggle_mcp_server(
    name: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """切换 MCP 服务器启用状态"""
    try:
        result = await db.execute(select(MCPServer).filter(MCPServer.name == name))
        server = result.scalar_one_or_none()
        if not server:
            raise HTTPException(status_code=404, detail=f"服务器 '{name}' 不存在")

        # 切换状态
        server.enabled = 0 if server.enabled else 1
        server.updated_by = current_user.username
        await db.commit()

        # 获取更新后的状态
        is_enabled = bool(server.enabled)
        server_config = server.to_mcp_config() if is_enabled else None

        # 同步到缓存
        sync_mcp_server_to_cache(name, server_config)

        return {
            "success": True,
            "enabled": is_enabled,
            "message": f"服务器 '{name}' 已{'启用' if is_enabled else '禁用'}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to toggle MCP server: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# === MCP 工具管理 ===
# =============================================================================


@mcp.get("/{name}/tools")
async def get_mcp_server_tools(
    name: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """获取 MCP 服务器的工具列表"""
    try:
        result = await db.execute(select(MCPServer).filter(MCPServer.name == name))
        server = result.scalar_one_or_none()
        if not server:
            raise HTTPException(status_code=404, detail=f"服务器 '{name}' 不存在")

        # 获取配置
        config = server.to_mcp_config()
        disabled_tools = server.disabled_tools or []

        try:
            tools = await get_mcp_tools(name, {name: config})
            tool_list = []

            for tool in tools:
                original_name = tool.name
                unique_id = tool.metadata.get("id") if tool.metadata else original_name

                tool_info = {
                    "name": original_name,
                    "id": unique_id,
                    "description": getattr(tool, "description", ""),
                    "enabled": original_name not in disabled_tools,
                }
                # 提取参数信息
                if hasattr(tool, "args_schema") and tool.args_schema:
                    schema = tool.args_schema.schema() if hasattr(tool.args_schema, "schema") else {}
                    tool_info["parameters"] = schema.get("properties", {})
                    tool_info["required"] = schema.get("required", [])
                else:
                    tool_info["parameters"] = {}
                    tool_info["required"] = []
                tool_list.append(tool_info)

            return {
                "success": True,
                "data": tool_list,
                "total": len(tool_list),
            }
        except Exception as tool_error:
            logger.error(f"Failed to get tools from MCP server '{name}': {tool_error}")
            return {
                "success": False,
                "message": f"获取工具失败: {str(tool_error)}",
                "data": [],
                "total": 0,
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get MCP server tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@mcp.post("/{name}/tools/refresh")
async def refresh_mcp_server_tools(
    name: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """刷新 MCP 服务器的工具列表（清除缓存重新获取）"""
    try:
        result = await db.execute(select(MCPServer).filter(MCPServer.name == name))
        server = result.scalar_one_or_none()
        if not server:
            raise HTTPException(status_code=404, detail=f"服务器 '{name}' 不存在")

        # 清除该服务器的工具缓存
        clear_mcp_server_tools_cache(name)

        # 获取配置
        config = server.to_mcp_config()

        try:
            tools = await get_mcp_tools(name, {name: config})
            return {
                "success": True,
                "message": f"工具列表已刷新，共发现 {len(tools)} 个工具",
                "tool_count": len(tools),
            }
        except Exception as tool_error:
            return {
                "success": False,
                "message": f"刷新失败: {str(tool_error)}",
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to refresh MCP server tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@mcp.put("/{name}/tools/{tool_name}/toggle")
async def toggle_mcp_server_tool(
    name: str,
    tool_name: str,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """切换单个工具的启用状态"""
    try:
        result = await db.execute(select(MCPServer).filter(MCPServer.name == name))
        server = result.scalar_one_or_none()
        if not server:
            raise HTTPException(status_code=404, detail=f"服务器 '{name}' 不存在")

        disabled_tools = list(server.disabled_tools or [])

        if tool_name in disabled_tools:
            # 当前禁用，改为启用
            disabled_tools.remove(tool_name)
            enabled = True
        else:
            # 当前启用，改为禁用
            disabled_tools.append(tool_name)
            enabled = False

        server.disabled_tools = disabled_tools
        server.updated_by = current_user.username
        await db.commit()

        return {
            "success": True,
            "tool_name": tool_name,
            "enabled": enabled,
            "message": f"工具 '{tool_name}' 已{'启用' if enabled else '禁用'}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to toggle MCP server tool: {e}")
        raise HTTPException(status_code=500, detail=str(e))
