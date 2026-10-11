"""通过真实 HTTP 与 PostgreSQL 验证 provider UID 请求头配置。"""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.api.main import app
import yuxi.api.routers.models as model_provider_router
from yuxi.api.dependencies.auth import get_superadmin_user, get_db
from yuxi.infrastructure.postgres.manager import PostgresManager
from yuxi.migrations.schema import create_business_tables
from yuxi.modules.models.tables import ModelProvider

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


async def test_provider_uid_header_http_round_trip_and_rejections(monkeypatch):
    """真实管理路由往返持久化开关，并拒绝无效类型、Gemini 与缺失密钥。"""
    schema = f"pytest_provider_uid_{uuid.uuid4().hex[:16]}"
    admin_engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    async with admin_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped_engine = create_async_engine(
        os.environ["POSTGRES_URL"],
        pool_pre_ping=True,
        connect_args={"server_settings": {"search_path": schema}},
    )
    manager = object.__new__(PostgresManager)
    PostgresManager.__init__(manager)
    manager.async_engine = scoped_engine
    manager._initialized = True
    session_factory = async_sessionmaker(scoped_engine, expire_on_commit=False)

    async def provide_db():
        async with session_factory() as session:
            yield session

    async def provide_admin():
        return SimpleNamespace(username="integration-test")

    async def no_cache_refresh():
        return None

    await create_business_tables(manager)
    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = provide_db
    app.dependency_overrides[get_superadmin_user] = provide_admin
    monkeypatch.setattr(model_provider_router, "_refresh_model_cache", no_cache_refresh)
    uid = uuid.uuid4().hex
    path = "/api/system/model-providers"
    provider = {
        "provider_id": f"pytest-uid-{uid}",
        "display_name": "Pytest UID provider",
        "provider_type": "openai",
        "base_url": "https://example.com/v1",
        "include_user_uid": False,
        "headers_json": {"Cookie": "session=private-cookie-fixture", "X-Public": "public"},
        "extra_json": {
            "nested": {"secret": "private-nested-fixture", "label": "kept"},
            "entries": [{"api_key": "private-list-fixture", "name": "entry"}],
        },
    }

    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            monkeypatch.delenv("YUXI_UID_SIGNATURE_SECRET", raising=False)
            missing_secret = await client.post(path, json={**provider, "include_user_uid": True})
            assert missing_secret.status_code == 400
            assert "YUXI_UID_SIGNATURE_SECRET" in missing_secret.json()["detail"]

            monkeypatch.setenv("YUXI_UID_SIGNATURE_SECRET", "integration-test-signing-secret")
            invalid_type = await client.post(path, json={**provider, "provider_id": f"pytest-invalid-{uid}", "include_user_uid": "true"})
            assert invalid_type.status_code == 422

            gemini = await client.post(
                path,
                json={
                    **provider,
                    "provider_id": f"pytest-gemini-{uid}",
                    "provider_type": "gemini",
                    "include_user_uid": True,
                },
            )
            assert gemini.status_code == 400
            assert "Gemini" in gemini.json()["detail"]

            created = await client.post(path, json=provider)
            assert created.status_code == 200, created.text
            assert created.json()["data"]["include_user_uid"] is False

            updated = await client.put(f"{path}/{provider['provider_id']}", json={"include_user_uid": True})
            assert updated.status_code == 200, updated.text
            assert updated.json()["data"]["include_user_uid"] is True

            reread = await client.get(f"{path}/{provider['provider_id']}")
            assert reread.status_code == 200, reread.text
            assert reread.json()["data"]["include_user_uid"] is True
            listing = await client.get(path)
            assert listing.status_code == 200
            for response in (created, updated, reread, listing):
                assert "private-cookie-fixture" not in response.text
                assert "private-nested-fixture" not in response.text
                assert "private-list-fixture" not in response.text
            redacted = reread.json()["data"]
            assert redacted["headers_json"]["Cookie"] == "[REDACTED]"
            saved = await client.put(
                f"{path}/{provider['provider_id']}",
                json={
                    "display_name": "renamed",
                    "headers_json": redacted["headers_json"],
                    "extra_json": redacted["extra_json"],
                },
            )
            assert saved.status_code == 200, saved.text
            rejected = await client.put(
                f"{path}/{provider['provider_id']}",
                json={"extra_json": {"new_secret": "[REDACTED]"}},
            )
            assert rejected.status_code == 400
            assert "没有可保留的原值" in rejected.json()["detail"]
            async with session_factory() as session:
                persisted = await session.scalar(select(ModelProvider).where(ModelProvider.provider_id == provider["provider_id"]))
                assert persisted.headers_json == provider["headers_json"]
                assert persisted.extra_json == provider["extra_json"]
                assert persisted.display_name == "renamed"

            disabled = await client.put(f"{path}/{provider['provider_id']}", json={"include_user_uid": False})
            assert disabled.status_code == 200, disabled.text
            assert disabled.json()["data"]["include_user_uid"] is False

            deleted = await client.delete(f"{path}/{provider['provider_id']}")
            assert deleted.status_code == 200, deleted.text
            assert (await client.get(f"{path}/{provider['provider_id']}")).status_code == 404
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        await scoped_engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin_engine.dispose()
