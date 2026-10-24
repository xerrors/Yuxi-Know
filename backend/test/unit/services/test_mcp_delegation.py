"""内部 MCP 认证复用 SDK 与通用出站策略。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from yuxi.modules.knowledge.mcp import client
from yuxi.modules.extensions.mcp import runtime

pytestmark = pytest.mark.asyncio


async def test_auth_checks_policy_before_issuing_credentials(monkeypatch):
    """拒绝发生在签发和网络副作用之前。"""
    issue = Mock(return_value="token")
    monkeypatch.setattr(client, "create_knowledge_token", issue)
    check = AsyncMock(side_effect=ValueError("revoked"))
    auth = client.KnowledgeMCPAuth("u", [], check)
    with pytest.raises(ValueError, match="revoked"):
        await auth.async_auth_flow(httpx.Request("POST", "http://api/mcp")).__anext__()
    issue.assert_not_called()


async def test_auth_signs_every_request_and_preserves_empty_scope(monkeypatch):
    """短期凭据每次请求重新签发，空范围不扩权。"""
    issue = Mock(side_effect=["one", "two"])
    monkeypatch.setattr(client, "create_knowledge_token", issue)
    check = AsyncMock()
    auth = client.KnowledgeMCPAuth("u", [], check)
    for expected in ["one", "two"]:
        request = httpx.Request("POST", "http://api/mcp")
        await auth.async_auth_flow(request).__anext__()
        assert request.headers["Authorization"] == f"Bearer {expected}"
    assert check.await_count == 2
    assert issue.call_count == 2
    issue.assert_called_with(uid="u", selection=[])


async def test_common_loader_preserves_sdk_auth_and_metadata(monkeypatch):
    """内部服务只提供认证；目录加载、过滤和工具身份仍由普通 loader 负责。"""
    auth = client.KnowledgeMCPAuth("u", [])
    tools = [SimpleNamespace(name="query_kb", metadata=None), SimpleNamespace(name="disabled", metadata=None)]
    capture = {}

    async def get_client(configs):
        capture.update(configs)
        return SimpleNamespace(get_tools=AsyncMock(return_value=tools))

    monkeypatch.setattr(runtime, "get_mcp_client", get_client)
    result = await runtime.get_mcp_tools("knowledge", {"transport": "streamable_http", "url": "http://api/mcp", "auth": auth}, ["disabled"])
    assert result == [tools[0]]
    assert result[0].metadata["id"] == "mcp__knowledge__queryKb"
    assert capture["knowledge"]["auth"] is auth
