"""真实 Redis 与 MCP 传输故障不能变成用户配置错误或空成功。"""

import json
import os
import socket
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from redis import Redis

from test.integration.support.module_audit import isolated_audit_store
import yuxi.modules.models.providers.cache as cache_module
import yuxi.modules.models.chat as chat_module
from yuxi.modules.extensions.mcp.models import MCPServer
from yuxi.modules.identity.models import User
from yuxi.modules.extensions.mcp.service import inspect_mcp_server_tools
from yuxi.modules.extensions.tools.runtime import resolve_configured_runtime_tools
from yuxi.modules.models.providers.cache import ModelCache, ModelInfo

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


async def test_redis_wire_failure_remains_infrastructure_error_and_recovers(monkeypatch):
    """真实连接拒绝保留故障归因，恢复读取后仍能解析原模型。"""
    key = f"pytest:model_cache:{uuid4().hex}"
    redis = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    cache = ModelCache()
    info = ModelInfo("fixture", "chat", "chat", "fixture", "", "https://example.com/v1", "openai")

    @contextmanager
    def connected():
        """借用本用例的真实 Redis 连接。"""
        yield redis

    monkeypatch.setattr(cache_module, "REDIS_CACHE_KEY", key)
    monkeypatch.setattr(cache_module, "sync_redis_client", connected)
    monkeypatch.setattr(chat_module, "model_cache", cache)
    try:
        redis.set(key, json.dumps({info.spec: info.to_dict()}))
        assert chat_module._require_chat_model_info(info.spec).model_id == "chat"
        cache._invalidate_local()
        with socket.socket() as unavailable:
            unavailable.bind(("127.0.0.1", 0))
            refused = Redis(host="127.0.0.1", port=unavailable.getsockname()[1], socket_connect_timeout=0.2, socket_timeout=0.2)

            @contextmanager
            def disconnected():
                """借用连接到拒绝端口的真实 Redis 客户端。"""
                yield refused

            with monkeypatch.context() as patch:
                patch.setattr(cache_module, "sync_redis_client", disconnected)
                with pytest.raises(RuntimeError, match="模型缓存不可用"):
                    chat_module._require_chat_model_info(info.spec)
            refused.close()
        assert chat_module._require_chat_model_info(info.spec).model_id == "chat"
        cache._invalidate_local()
        redis.set(key, "{}")
        with pytest.raises(ValueError, match="未找到模型"):
            chat_module._require_chat_model_info(info.spec)
    finally:
        redis.delete(key)
        redis.close()


@pytest.mark.parametrize("transport", ["sse", "streamable_http"])
async def test_mcp_wire_failure_reaches_agent_and_management(monkeypatch, transport):
    """同一真实故障服务在工具装配和管理检查都显式失败。"""
    async with isolated_audit_store(monkeypatch) as (_, sessions):
        with socket.socket() as unavailable:
            unavailable.bind(("127.0.0.1", 0))
            server = MCPServer(
                slug="failed-remote",
                name="failed-remote",
                transport=transport,
                url=f"http://127.0.0.1:{unavailable.getsockname()[1]}/mcp",
                enabled=1,
                timeout=1,
                sse_read_timeout=1,
                created_by="fixture",
                updated_by="fixture",
            )
            async with sessions.begin() as db:
                db.add_all([server, User(uid="fixture", username="fixture", password_hash="unused", role="user")])
            context = SimpleNamespace(uid="fixture", tools=[], mcps=[server.slug])
            with pytest.raises(RuntimeError, match="MCP.*failed-remote.*失败"):
                await resolve_configured_runtime_tools(context)
            assert context.mcp_tool_servers == {}
            with pytest.raises(ExceptionGroup):
                await inspect_mcp_server_tools(server)
