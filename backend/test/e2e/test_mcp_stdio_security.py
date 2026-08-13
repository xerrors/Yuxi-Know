from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from yuxi.agents.mcp.service import ensure_builtin_mcp_servers_in_db, get_mcp_tools
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import MCPServer

pytestmark = pytest.mark.e2e


async def test_stdio_mcp_payload_is_rejected_without_side_effects(e2e_client, e2e_headers):
    """恶意 stdio 请求应在持久化和进程启动前被拒绝。"""
    unique_id = uuid.uuid4().hex[:8]
    slug = f"pytest-unsafe-mcp-{unique_id}"
    marker = Path(f"/app/saves/{slug}.marker")

    try:
        response = await e2e_client.post(
            "/api/system/mcp-servers",
            headers=e2e_headers,
            json={
                "slug": slug,
                "name": "pytest unsafe MCP",
                "transport": "stdio",
                "command": "sh",
                "args": ["-c", f"touch {marker}"],
            },
        )

        # 如果创建边界回归，继续触发连接测试，以验证本地进程副作用仍会被测试捕获。
        if response.is_success:
            await e2e_client.post(f"/api/system/mcp-servers/{slug}/test", headers=e2e_headers)

        assert response.status_code == 422, response.text

        list_response = await e2e_client.get("/api/system/mcp-servers", headers=e2e_headers)
        assert list_response.status_code == 200, list_response.text
        assert slug not in {server["slug"] for server in list_response.json()["data"]}
        assert not marker.exists(), "stdio MCP payload created a file in the API container"
    finally:
        try:
            cleanup_response = await e2e_client.delete(f"/api/system/mcp-servers/{slug}", headers=e2e_headers)
            assert cleanup_response.status_code in (200, 404), cleanup_response.text
        finally:
            marker.unlink(missing_ok=True)


async def test_legacy_stdio_mcp_is_disabled_without_starting_process(e2e_client, e2e_headers):
    """历史 stdio 记录应被迁移逻辑和运行时加载双重拦截。"""
    unique_id = uuid.uuid4().hex[:8]
    slug = f"pytest-legacy-stdio-{unique_id}"
    marker = Path(f"/app/saves/{slug}.marker")

    pg_manager.initialize()
    try:
        async with pg_manager.get_async_session_context() as db:
            db.add(
                MCPServer(
                    slug=slug,
                    name="pytest legacy stdio MCP",
                    transport="stdio",
                    command="sh",
                    args=["-c", f"touch {marker}"],
                    enabled=1,
                    created_by="admin",
                    updated_by="admin",
                )
            )
            await db.commit()

        await ensure_builtin_mcp_servers_in_db()
        assert await get_mcp_tools(slug, cache=False, force_refresh=True) == []

        async with pg_manager.get_async_session_context() as db:
            server = await db.scalar(select(MCPServer).where(MCPServer.slug == slug))
            assert server is not None
            assert server.enabled == 0

        test_response = await e2e_client.post(f"/api/system/mcp-servers/{slug}/test", headers=e2e_headers)
        assert test_response.status_code == 400, test_response.text
        assert not marker.exists(), "legacy stdio MCP created a file in the API container"
    finally:
        async with pg_manager.get_async_session_context() as db:
            await db.execute(delete(MCPServer).where(MCPServer.slug == slug))
            await db.commit()
        marker.unlink(missing_ok=True)
