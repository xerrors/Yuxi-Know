from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test.support.sqlite import create_utc_sqlite_engine
from yuxi.modules.extensions.mcp import service as mcp_service
from yuxi.modules.extensions.mcp import runtime as mcp_runtime
import yuxi.infrastructure.postgres.manager as postgres_manager
from yuxi.modules.extensions.mcp.models import MCPServer


class _AsyncSessionContext:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_args):
        return False


class _FailingSessionContext:
    async def __aenter__(self):
        raise RuntimeError("database-secret-must-not-be-swallowed")

    async def __aexit__(self, *_args):
        return False


@pytest_asyncio.fixture
async def mcp_session():
    engine = create_utc_sqlite_engine()
    async with engine.begin() as conn:
        await conn.run_sync(MCPServer.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


class _FakeClient:
    def __init__(self, tools):
        self._tools = tools

    async def get_tools(self):
        return self._tools


async def test_ensure_builtin_mcp_servers_preserves_other_system_server(monkeypatch, mcp_session):
    retired_server = MCPServer(
        slug="sequentialthinking",
        name="sequentialthinking",
        description="old builtin",
        transport="streamable_http",
        url="https://remote.mcpservers.org/sequentialthinking/mcp",
        enabled=1,
        created_by="system",
        updated_by="system",
    )
    mcp_session.add(retired_server)
    await mcp_session.commit()

    monkeypatch.setattr(
        postgres_manager.pg_manager,
        "get_async_session_context",
        lambda: _AsyncSessionContext(mcp_session),
    )

    await mcp_service.ensure_builtin_mcp_servers_in_db()

    retired = await mcp_session.scalar(select(MCPServer).where(MCPServer.slug == "sequentialthinking"))
    deepwiki = await mcp_session.scalar(select(MCPServer).where(MCPServer.slug == "deepwiki-official"))
    assert retired is not None
    assert deepwiki is not None


@pytest.mark.parametrize("slug", ["sequentialthinking", "deepwiki"])
async def test_ensure_builtin_mcp_servers_preserves_user_slug(monkeypatch, mcp_session, slug):
    user_server = MCPServer(
        slug=slug,
        name="用户自定义 MCP",
        description="user managed",
        transport="streamable_http",
        url="https://example.com/mcp",
        enabled=1,
        created_by="admin",
        updated_by="admin",
    )
    mcp_session.add(user_server)
    await mcp_session.commit()

    monkeypatch.setattr(
        postgres_manager.pg_manager,
        "get_async_session_context",
        lambda: _AsyncSessionContext(mcp_session),
    )

    await mcp_service.ensure_builtin_mcp_servers_in_db()

    server = await mcp_session.scalar(select(MCPServer).where(MCPServer.slug == slug))
    assert server is not None
    assert server.created_by == "admin"
    assert server.url == "https://example.com/mcp"
    assert server.enabled == 1
    assert not mcp_service.is_builtin_mcp_server(server)
    configs = await mcp_service._load_enabled_mcp_server_configs(db=mcp_session)
    assert configs[slug]["url"] == "https://example.com/mcp"


async def test_ensure_builtin_mcp_servers_does_not_migrate_unsupported_transport(monkeypatch, mcp_session):
    legacy_server = MCPServer(
        slug="legacy-stdio",
        name="历史 stdio",
        transport="websocket",
        enabled=1,
        created_by="system",
        updated_by="system",
    )
    mcp_session.add(legacy_server)
    await mcp_session.commit()

    monkeypatch.setattr(
        postgres_manager.pg_manager,
        "get_async_session_context",
        lambda: _AsyncSessionContext(mcp_session),
    )

    await mcp_service.ensure_builtin_mcp_servers_in_db()

    await mcp_session.refresh(legacy_server)
    assert legacy_server.enabled == 1


async def test_builtin_mcp_initialization_propagates_failure_to_entrypoint(monkeypatch):
    monkeypatch.setattr(
        postgres_manager.pg_manager,
        "get_async_session_context",
        lambda: _FailingSessionContext(),
    )

    with pytest.raises(RuntimeError, match="must-not-be-swallowed"):
        await mcp_service.ensure_builtin_mcp_servers_in_db()


async def test_runtime_configs_exclude_unsupported_transports(mcp_session):
    mcp_session.add_all(
        [
            MCPServer(
                slug="mcp-server-chart",
                name="不支持的传输",
                transport="websocket",
                enabled=1,
                created_by="system",
                updated_by="system",
            ),
            MCPServer(
                slug="user-websocket",
                name="用户 WebSocket",
                transport="websocket",
                enabled=1,
                created_by="admin",
                updated_by="admin",
            ),
            MCPServer(
                slug="forged-system-websocket",
                name="伪造系统 WebSocket",
                transport="websocket",
                enabled=1,
                created_by="system",
                updated_by="system",
            ),
            MCPServer(
                slug="remote-http",
                name="远程 HTTP",
                transport="streamable_http",
                url="https://example.com/mcp",
                enabled=1,
                created_by="admin",
                updated_by="admin",
            ),
        ]
    )
    await mcp_session.commit()

    configs = await mcp_service._load_enabled_mcp_server_configs(db=mcp_session)
    slugs = await mcp_service.get_enabled_mcp_server_slugs(db=mcp_session)

    assert set(configs) == {"remote-http"}
    assert set(slugs) == {"remote-http"}
    assert "command" not in configs["remote-http"]
    assert "args" not in configs["remote-http"]


async def test_create_mcp_server_rejects_builtin_slug(mcp_session):
    with pytest.raises(ValueError, match="slug"):
        await mcp_service.create_mcp_server(
            mcp_session,
            slug="deepwiki-official",
            name="伪造内置 MCP",
            transport="streamable_http",
            url="https://example.com/mcp",
            created_by="admin",
        )


async def test_delete_builtin_mcp_server_rejects_service_call(mcp_session):
    server = MCPServer(
        slug="deepwiki-official",
        name="内置 MCP",
        transport="streamable_http",
        url="https://trusted.example/mcp",
        enabled=1,
        created_by="system",
        updated_by="system",
    )
    mcp_session.add(server)
    await mcp_session.commit()

    with pytest.raises(PermissionError, match="系统内置"):
        await mcp_service.delete_mcp_server(mcp_session, "deepwiki-official")

    assert await mcp_session.scalar(select(MCPServer).where(MCPServer.slug == "deepwiki-official")) is not None


async def test_update_builtin_mcp_server_rejects_connection_changes(mcp_session):
    server = MCPServer(
        slug="deepwiki-official",
        name="DeepWiki",
        transport="streamable_http",
        url="https://trusted.example/mcp",
        enabled=1,
        created_by="system",
        updated_by="system",
    )
    mcp_session.add(server)
    await mcp_session.commit()

    with pytest.raises(PermissionError, match="系统内置"):
        await mcp_service.update_mcp_server(
            mcp_session,
            slug="deepwiki-official",
            transport="streamable_http",
            url="https://example.com/mcp",
            updated_by="admin",
        )

    await mcp_session.refresh(server)
    assert server.transport == "streamable_http"
    assert server.url == "https://trusted.example/mcp"


async def test_update_unsupported_transport_requires_remote_url(mcp_session):
    legacy_server = MCPServer(
        slug="legacy-stdio",
        name="历史 stdio",
        transport="websocket",
        enabled=0,
        created_by="admin",
        updated_by="admin",
    )
    mcp_session.add(legacy_server)
    await mcp_session.commit()

    with pytest.raises(ValueError, match="url"):
        await mcp_service.update_mcp_server(
            mcp_session,
            slug="legacy-stdio",
            transport="streamable_http",
            updated_by="admin",
        )

    await mcp_session.refresh(legacy_server)
    assert legacy_server.transport == "websocket"


async def test_get_enabled_mcp_tools_loads_latest_config_from_db(monkeypatch):
    captured: list[dict] = []

    async def fake_get_enabled_mcp_server_config(server_name: str, db=None):
        del db
        assert server_name == "demo"
        return {"transport": "streamable_http", "url": "demo", "disabled_tools": ["tool_b"]}

    async def fake_get_mcp_tools(server_name: str, additional_servers=None, disabled_tools=None, **kwargs):
        del kwargs
        captured.append(
            {
                "server_name": server_name,
                "additional_servers": additional_servers,
                "disabled_tools": list(disabled_tools or []),
            }
        )
        return ["tool-a"]

    monkeypatch.setattr(mcp_service, "get_enabled_mcp_server_config", fake_get_enabled_mcp_server_config)
    monkeypatch.setattr(mcp_service, "get_mcp_tools", fake_get_mcp_tools)

    tools = await mcp_service.get_enabled_mcp_tools("demo")

    assert tools == ["tool-a"]
    assert captured == [
        {
            "server_name": "demo",
            "additional_servers": {"demo": {"transport": "streamable_http", "url": "demo", "disabled_tools": ["tool_b"]}},
            "disabled_tools": ["tool_b"],
        }
    ]


async def test_get_mcp_tools_rebuilds_cache_when_config_hash_changes(monkeypatch):
    mcp_runtime.clear_mcp_cache()

    configs = [
        {"transport": "streamable_http", "url": "demo-v1", "disabled_tools": []},
        {"transport": "streamable_http", "url": "demo-v2", "disabled_tools": []},
    ]
    build_calls: list[str] = []

    async def fake_get_enabled_mcp_server_config(server_name: str, db=None):
        del db
        assert server_name == "demo"
        return configs[0]

    async def fake_get_mcp_client(server_configs):
        config = server_configs["demo"]
        build_calls.append(config["url"])
        tool = SimpleNamespace(name=f"tool_for_{config['url']}", metadata={})
        return _FakeClient([tool])

    monkeypatch.setattr(mcp_service, "get_enabled_mcp_server_config", fake_get_enabled_mcp_server_config)
    monkeypatch.setattr(mcp_runtime, "get_mcp_client", fake_get_mcp_client)

    tools_v1_first = await mcp_service.get_mcp_tools("demo")
    tools_v1_second = await mcp_service.get_mcp_tools("demo")

    configs[0] = configs[1]
    tools_v2 = await mcp_service.get_mcp_tools("demo")

    assert [tool.name for tool in tools_v1_first] == ["tool_for_demo-v1"]
    assert [tool.name for tool in tools_v1_second] == ["tool_for_demo-v1"]
    assert [tool.name for tool in tools_v2] == ["tool_for_demo-v2"]
    assert build_calls == ["demo-v1", "demo-v2"]

    mcp_runtime.clear_mcp_cache()


async def test_get_mcp_tools_sets_handle_tool_error(monkeypatch):
    mcp_runtime.clear_mcp_cache()

    config = {"transport": "streamable_http", "url": "demo-tool", "disabled_tools": []}

    async def fake_get_enabled_mcp_server_config(server_name: str, db=None):
        del db
        return config

    async def fake_get_mcp_client(server_configs):
        tool = SimpleNamespace(name="demo_tool", metadata={})
        return _FakeClient([tool])

    monkeypatch.setattr(mcp_service, "get_enabled_mcp_server_config", fake_get_enabled_mcp_server_config)
    monkeypatch.setattr(mcp_runtime, "get_mcp_client", fake_get_mcp_client)

    tools = await mcp_service.get_mcp_tools("demo")
    assert len(tools) == 1
    assert tools[0].handle_tool_error is True

    mcp_runtime.clear_mcp_cache()


@pytest.mark.parametrize("transport", ["stdio", "websocket", None])
async def test_client_rejects_unsupported_transport_before_adapter(monkeypatch, transport):
    """直接客户端入口不能绕过远程传输限制。"""

    def forbidden_client(*_args, **_kwargs):
        pytest.fail("unsupported transport reached MCP adapter")

    monkeypatch.setattr(mcp_runtime, "MultiServerMCPClient", forbidden_client)
    with pytest.raises(ValueError, match="仅支持 sse 或 streamable_http"):
        await mcp_runtime.get_mcp_client({"deepwiki-official": {"transport": transport}})


async def test_additional_unsupported_config_cannot_reuse_cached_tools():
    """缓存命中前仍拒绝不支持的远程传输。"""
    import hashlib
    import json

    config = {"transport": "websocket"}
    digest = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
    key = f"deepwiki-official:{digest}"
    mcp_runtime._mcp_tools_cache[key] = [SimpleNamespace(name="unsafe_cached_tool")]
    try:
        with pytest.raises(ValueError, match="仅支持 sse 或 streamable_http"):
            await mcp_service.get_mcp_tools("deepwiki-official", additional_servers={"deepwiki-official": config})
    finally:
        mcp_runtime.clear_mcp_cache()


def test_model_cannot_serialize_stdio_for_execution():
    """持久化模型不再生成本地进程配置。"""
    server = MCPServer(slug="unsupported", transport="stdio")
    with pytest.raises(ValueError, match="仅支持 sse 或 streamable_http"):
        server.to_mcp_config()


async def test_sync_deepwiki_idempotently_preserves_other_servers(monkeypatch, mcp_session):
    """同步仅收敛当前内置定义，保留其他服务器与管理员启停。"""
    mcp_session.add_all(
        [
            MCPServer(
                slug="mcp-server-chart",
                name="Chart",
                transport="streamable_http",
                url="https://retired.example/mcp",
                enabled=1,
                created_by="system",
                updated_by="system",
            ),
            MCPServer(
                slug="deepwiki-official",
                name="DeepWiki",
                transport="streamable_http",
                url="https://tampered.example/mcp",
                enabled=0,
                created_by="system",
                updated_by="system",
            ),
        ]
    )
    await mcp_session.commit()
    monkeypatch.setattr(postgres_manager.pg_manager, "get_async_session_context", lambda: _AsyncSessionContext(mcp_session))
    await mcp_service.ensure_builtin_mcp_servers_in_db()
    await mcp_service.ensure_builtin_mcp_servers_in_db()
    assert await mcp_session.scalar(select(MCPServer).where(MCPServer.slug == "mcp-server-chart")) is not None
    server = await mcp_session.scalar(select(MCPServer).where(MCPServer.slug == "deepwiki-official"))
    assert server.transport == "streamable_http"
    assert server.url == "https://mcp.deepwiki.com/mcp"
    assert server.enabled == 0
    server.url = "https://tampered.example/mcp"
    assert mcp_service._to_runtime_mcp_config(server) == {
        "transport": "streamable_http",
        "url": "https://mcp.deepwiki.com/mcp",
    }


async def test_inspection_rejects_unsupported_transport_even_for_builtin_slug():
    """内置标识不再提供 stdio 豁免。"""
    server = MCPServer(slug="unsupported", transport="websocket")
    with pytest.raises(ValueError, match="仅支持 sse 或 streamable_http"):
        await mcp_service.inspect_mcp_server_tools(server)


@pytest.mark.parametrize("outcome", ["empty", "tool", "error"])
async def test_inspection_connects_disabled_server_without_mutating_runtime(monkeypatch, outcome):
    """管理检查不继承运行时停用与降级语义。"""
    server = MCPServer(
        slug="fixture-inspect",
        name="fixture",
        transport="streamable_http",
        url="http://127.0.0.1:12345/mcp",
        enabled=0,
        disabled_tools=["fixture_tool"],
        headers={"Authorization": "Bearer fixture"},
        timeout=1,
        sse_read_timeout=1,
    )
    tool = SimpleNamespace(name="fixture_tool", metadata={"retained": "value"})
    get_tools = AsyncMock(return_value=[] if outcome == "empty" else [tool])
    if outcome == "error":
        get_tools.side_effect = RuntimeError("fixture-credential-must-not-be-swallowed")
    configs = []

    def client(config):
        configs.append(config)
        return SimpleNamespace(get_tools=get_tools)

    monkeypatch.setattr(mcp_service, "MultiServerMCPClient", client)
    cache, stats = dict(mcp_runtime._mcp_tools_cache), dict(mcp_runtime._mcp_tools_stats)
    if outcome == "error":
        with pytest.raises(RuntimeError, match="fixture-credential"):
            await mcp_service.inspect_mcp_server_tools(server)
    else:
        tools = await mcp_service.inspect_mcp_server_tools(server)
        assert len(tools) == (0 if outcome == "empty" else 1)
        if tools:
            assert tool.metadata == {"retained": "value", "id": "mcp__fixtureInspect__fixtureTool"}
    get_tools.assert_awaited_once_with()
    assert configs[0][server.slug]["url"] == server.url
    assert configs[0][server.slug]["headers"] == server.headers
    assert "disabled_tools" not in configs[0][server.slug]
    assert server.enabled == 0 and server.disabled_tools == ["fixture_tool"]
    assert mcp_runtime._mcp_tools_cache == cache
    assert mcp_runtime._mcp_tools_stats == stats


async def test_inspection_rejects_unmigrated_stdio_before_connecting(monkeypatch):
    """自定义旧 stdio 不应启动子进程。"""

    def client(_):
        pytest.fail("自定义旧 stdio 不应启动子进程")

    monkeypatch.setattr(mcp_service, "MultiServerMCPClient", client)
    with pytest.raises(ValueError, match="stdio"):
        await mcp_service.inspect_mcp_server_tools(MCPServer(slug="fixture-stdio", transport="stdio", enabled=0))


@pytest.mark.parametrize("phase", ["client", "tools", "group"])
async def test_runtime_connection_failure_is_explicit_and_not_cached(monkeypatch, phase):
    """配置的 MCP 建连或工具加载失败不能被当作合法空列表。"""
    mcp_runtime.clear_mcp_cache()
    failure = RuntimeError("remote unavailable")
    if phase == "group":
        failure = ExceptionGroup("remote unavailable", [failure])

    def client(_configs):
        """分别在建连或工具读取阶段注入远程故障。"""
        if phase == "client":
            raise failure
        return SimpleNamespace(get_tools=AsyncMock(side_effect=failure))

    monkeypatch.setattr(mcp_runtime, "MultiServerMCPClient", client)
    with pytest.raises(RuntimeError, match="MCP.*demo.*失败") as caught:
        await mcp_runtime.get_mcp_tools("demo", {"transport": "streamable_http", "url": "https://example.com/mcp"})
    assert caught.value.__cause__ is failure
    assert mcp_runtime._mcp_tools_cache == {}
    assert mcp_runtime.get_mcp_tools_stats("demo") is None
    monkeypatch.setattr(mcp_runtime, "MultiServerMCPClient", lambda _: _FakeClient([]))
    assert await mcp_runtime.get_mcp_tools("demo", {"transport": "streamable_http", "url": "https://example.com/mcp"}) == []
    mcp_runtime.clear_mcp_cache()
