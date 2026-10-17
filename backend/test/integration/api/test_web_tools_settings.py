"""真实 HTTP 与 PostgreSQL 验证网页工具配置。"""

import json
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select

from test.integration.support.module_audit import isolated_audit_store, serve_http
from yuxi.api.dependencies.auth import get_db, get_required_user
from yuxi.api.errors import domain_error_handler
from yuxi.api.routers.extensions.web import web_tools
from yuxi.api.routers.system import system
from yuxi.bootstrap.options import ensure_options_in_db
from yuxi.modules.extensions.web.services import get_web_configuration
from yuxi.modules.system.models import ConfigOption
from yuxi.shared.errors import DomainError

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.self_managed_resources,
    pytest.mark.httpx_mock(should_mock=lambda request: request.url.scheme == "https"),
]


@pytest_asyncio.fixture
async def settings_http(monkeypatch):
    """使用真实路由、依赖鉴权和独立数据库 Schema。"""
    for name in ("WEB_SEARCH_PROVIDER", "TAVILY_API_KEY", "DEEPSEEK_API_KEY", "DOUBAO_SEARCH_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    async with isolated_audit_store(monkeypatch) as (_, sessions):
        async with sessions() as db:
            await ensure_options_in_db(db)
            await db.commit()
        app = FastAPI()
        app.include_router(system, prefix="/api")
        app.include_router(web_tools, prefix="/api")
        app.add_exception_handler(DomainError, domain_error_handler)
        user = SimpleNamespace(role="superadmin", username="web-tools-test")

        async def database():
            """请求持有独立真实数据库 session。"""
            async with sessions() as db:
                yield db

        app.dependency_overrides[get_db] = database
        app.dependency_overrides[get_required_user] = lambda: user
        async with serve_http(app) as client:
            yield client, sessions, user


async def test_credentials_persist_separately_and_clear_restores_environment(settings_http, monkeypatch):
    """回读不同 session 的持久值，验证运行配置与脱敏响应一致。"""
    client, sessions, _ = settings_http
    monkeypatch.setenv("TAVILY_API_KEY", "environment-key")
    for provider in ("tavily", "deepseek", "doubao"):
        response = await client.put(
            f"/api/system/config/options/{provider}_search_opts", json={"value": {"api_key": f"{provider}-database-key"}}
        )
        assert response.status_code == 200, response.text
        assert f"{provider}-database-key" not in response.text
        assert response.json()["option"]["sensitive_state"]["api_key"]["source"] == "database"
    for operation, provider in (("search", "doubao"), ("fetch", "deepseek")):
        saved = await client.post("/api/system/config/update", json={f"web_{operation}_provider": provider})
        assert saved.status_code == 200, saved.text
    async with sessions() as db:
        config = await get_web_configuration(db)
        records = list((await db.scalars(select(ConfigOption))).all())
    assert config["search"] == "doubao"
    assert config["fetch"] == "deepseek"
    assert config["keys"]["tavily"] == "tavily-database-key"
    assert {record.key: record.value for record in records}["deepseek_search_opts"] == {"api_key": "deepseek-database-key"}
    cleared = await client.put("/api/system/config/options/tavily_search_opts", json={"value": {"api_key": ""}})
    assert cleared.json()["option"]["sensitive_state"]["api_key"] == {"source": "environment", "configured": True, "preview": None}
    async with sessions() as db:
        assert (await get_web_configuration(db))["keys"]["tavily"] == "environment-key"
    reread = await client.get("/api/system/config/options")
    assert "database-key" not in reread.text
    assert "environment-key" not in reread.text


async def test_invalid_defaults_and_non_superadmin_requests_are_rejected(settings_http):
    """拒绝无凭据、未知供应商及豆包 Fetch，普通用户不能触发外部测试。"""
    client, sessions, user = settings_http
    for payload in ({"web_search_provider": "unknown"}, {"web_fetch_provider": "doubao"}, {"web_search_provider": "tavily"}):
        response = await client.post("/api/system/config/update", json=payload)
        assert response.status_code == 400, response.text
    async with sessions() as db:
        config = await get_web_configuration(db)
    assert config["search"] is None
    user.role = "admin"
    for method, url, body in (
        ("GET", "/api/system/config/options", None),
        ("PUT", "/api/system/config/options/tavily_search_opts", {"value": {"api_key": "key"}}),
        ("POST", "/api/system/web-tools/search/test", {"provider": "tavily", "query": "q", "api_key": "key"}),
        ("POST", "/api/system/web-tools/fetch/test", {"provider": "deepseek", "url": "https://example.com", "api_key": "key"}),
    ):
        rejected = await client.request(method, url, json=body)
        assert rejected.status_code == 403, rejected.text


async def test_draft_search_and_fetch_use_real_service_without_persistence(settings_http, httpx_mock):
    """只重放供应商协议，保留真实 TCP 路由、业务服务与数据库。"""
    client, sessions, _ = settings_http
    async with sessions() as db:
        before = {record.key: record.value for record in await db.scalars(select(ConfigOption))}
    httpx_mock.add_response(
        url="https://api.tavily.com/search",
        json={"results": [{"title": "Title", "url": "https://example.com", "content": "Relevant", "score": 0.9}]},
    )
    searched = await client.post(
        "/api/system/web-tools/search/test", json={"provider": "tavily", "query": "q", "api_key": "draft-only-key"}
    )
    assert searched.status_code == 200, searched.text
    assert searched.json()["results"][0]["relevant_content"] == "Relevant"
    httpx_mock.add_response(url="https://api.deepseek.com/v1/tools/fetch", json={"title": "Title", "content": "# Body"})
    fetched = await client.post(
        "/api/system/web-tools/fetch/test", json={"provider": "deepseek", "url": "https://example.com", "api_key": "draft-only-key"}
    )
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["content"] == "# Body"
    assert all(request.headers["authorization"] == "Bearer draft-only-key" for request in httpx_mock.get_requests())
    async with sessions() as db:
        assert {record.key: record.value for record in await db.scalars(select(ConfigOption))} == before
    assert "draft-only-key" not in searched.text + fetched.text + json.dumps(before)


@pytest.mark.parametrize("operation,fields", [("search", {"query": "q"}), ("fetch", {"url": "https://example.com"})])
async def test_invalid_draft_key_type_is_never_reflected_in_validation_error(settings_http, operation, fields):
    """非法类型的敏感输入也不能从 FastAPI 默认 422 响应泄露。"""
    client, _, _ = settings_http
    response = await client.post(
        f"/api/system/web-tools/{operation}/test",
        json={
            "provider": "tavily",
            "api_key": ["invalid-draft-secret"],
            **fields,
        },
    )
    assert response.status_code == 422
    assert "invalid-draft-secret" not in response.text
    assert response.json()["detail"][0]["loc"] == ["body", "api_key"]
    assert "input" not in response.json()["detail"][0]
