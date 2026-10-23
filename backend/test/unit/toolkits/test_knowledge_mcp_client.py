"""MCP 协议结果不能把工具失败误投影成成功正文。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from mcp import types

from yuxi.modules.extensions.tools.knowledge import client

pytestmark = pytest.mark.asyncio


@pytest.fixture
def result_transport(monkeypatch):
    """隔离 wire 结果解码，真实 HTTP 链路由 integration/E2E 覆盖。"""
    state = SimpleNamespace(result=None)

    @asynccontextmanager
    async def transport(*args, **kwargs):
        """提供会话的受控传输。"""
        yield None, None, None

    class Session:
        """消费与真实 SDK 相同的 CallToolResult。"""

        def __init__(self, *args, **kwargs):
            """不建立外部连接。"""

        async def __aenter__(self):
            """进入受控会话。"""
            return self

        async def __aexit__(self, *args):
            """释放会话。"""

        async def initialize(self):
            """完成协议握手。"""

        async def call_tool(self, name, arguments):
            """读取预设协议结果而非调用生产业务。"""
            return state.result

    monkeypatch.setattr(client, "streamable_http_client", transport)
    monkeypatch.setattr(client, "ClientSession", Session)
    return state


async def test_mcp_iserror_is_a_tool_failure_and_not_service_disconnect(result_transport):
    """参数/权限拒绝仍允许之后的正确调用恢复。"""
    result_transport.result = types.CallToolResult(isError=True, content=[types.TextContent(type="text", text="资源不可见")])
    with pytest.raises(client.KnowledgeMCPError, match="资源不可见") as error:
        await client.call_knowledge_mcp("query_kb", {}, uid="u", selection=[])
    assert not isinstance(error.value, client.KnowledgeMCPUnavailable)
    result_transport.result = types.CallToolResult(content=[], structuredContent={"knowledge_bases": []})
    assert await client.call_knowledge_mcp("list_kbs", {}, uid="u", selection=[]) == []


async def test_malformed_wire_result_cannot_masquerade_as_empty_success(result_transport):
    """缺少结构化结果时显式失败。"""
    result_transport.result = types.CallToolResult(content=[types.TextContent(type="text", text="not structured")])
    with pytest.raises(client.KnowledgeMCPError, match="无效结果"):
        await client.call_knowledge_mcp("list_kbs", {}, uid="u", selection="all")
