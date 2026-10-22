"""真实 HTTP/PG 验证密码登录用例与协议契约。"""

import asyncio
import os
import socket
from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
import uvicorn
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from yuxi.api.routers.identity import auth as router
from yuxi.infrastructure.postgres.models import load_models
from yuxi.infrastructure.postgres.base import BusinessBase
from yuxi.modules.identity.models import Department, User
from yuxi.modules.identity.security import AuthUtils
from yuxi.modules.identity.services import password_login
from yuxi.shared.datetime import utc_now

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest_asyncio.fixture
async def login_boundary(monkeypatch):
    """使用独占 schema 和真实路由，固定 Redis 限速以避免共享环境干扰。"""
    load_models()
    schema = f"pytest_password_{uuid4().hex}"
    admin = create_async_engine(os.environ["POSTGRES_URL"])
    engine = create_async_engine(os.environ["POSTGRES_URL"], connect_args={"server_settings": {"search_path": schema}})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    sock = socket.socket()
    server = task = None
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        async with engine.begin() as conn:
            await conn.run_sync(BusinessBase.metadata.create_all)
        async with factory() as db, db.begin():
            dept = Department(name="Fixture department")
            db.add(dept)
            await db.flush()
            db.add(
                User(
                    username="Fixture",
                    uid="fixture",
                    password_hash=AuthUtils.hash_password("fixture-password"),
                    role="user",
                    department_id=dept.id,
                )
            )

        async def request_db():
            """模拟生产请求事务边界，业务显式提交仍由 service 执行。"""
            async with factory() as db, db.begin():
                yield db

        monkeypatch.setattr(password_login, "check_login_rate_limit", AsyncMock(return_value=(True, 0)))
        monkeypatch.setattr(password_login, "record_login_failure", AsyncMock())
        monkeypatch.setattr(password_login, "clear_login_failures", AsyncMock())
        app = FastAPI()
        app.include_router(router.auth, prefix="/api")
        app.dependency_overrides[router.get_db] = request_db
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="critical", lifespan="off"))
        task = asyncio.create_task(server.serve(sockets=[sock]))
        async with asyncio.timeout(5):
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError("Password login test server did not start")
                await asyncio.sleep(0.01)
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
            yield client, factory
    finally:
        if server is not None:
            server.should_exit = True
        if task is not None:
            await asyncio.wait_for(task, 5)
        sock.close()
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()


async def test_password_failures_persist_and_lock_account(login_boundary):
    """失败响应之前提交计数，第五次失败锁定且正确密码也不能绕过。"""
    client, factory = login_boundary
    for attempt in range(1, 6):
        response = await client.post("/api/auth/token", data={"username": "fixture", "password": "wrong"})
        assert response.status_code == (423 if attempt == 5 else 401), response.text
        assert response.headers["WWW-Authenticate"] == "Bearer"
        async with factory() as observer:
            user = await observer.scalar(select(User).where(User.uid == "fixture"))
            assert user.login_failed_count == attempt
            assert user.last_login is None
    assert int(response.headers["X-Lock-Remaining"]) > 0
    response = await client.post("/api/auth/token", data={"username": "fixture", "password": "fixture-password"})
    assert response.status_code == 423
    assert "登录被锁定" in response.json()["detail"]


async def test_success_resets_failure_state_and_returns_identity(login_boundary):
    """真实验密和签发成功后，独立读取登录时间与计数。"""
    client, factory = login_boundary
    async with factory() as db, db.begin():
        user = await db.scalar(select(User).where(User.uid == "fixture"))
        user.login_failed_count = 3
        user.last_failed_login = utc_now()
    response = await client.post("/api/auth/token", data={"username": "fixture", "password": "fixture-password"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["uid"] == "fixture"
    assert payload["department_name"] == "Fixture department"
    assert payload["token_type"] == "bearer"
    assert AuthUtils.decode_token(payload["access_token"])["sub"] == str(payload["user_id"])
    async with factory() as observer:
        user = await observer.scalar(select(User).where(User.uid == "fixture"))
        assert user.login_failed_count == 0
        assert user.last_failed_login is None
        assert user.last_login is not None


async def test_expired_lock_starts_new_failure_count(login_boundary):
    """过期锁定后的第一次失败计数从一开始。"""
    client, factory = login_boundary
    async with factory() as db, db.begin():
        user = await db.scalar(select(User).where(User.uid == "fixture"))
        user.login_failed_count = 5
        user.login_locked_until = utc_now() - timedelta(seconds=1)
    response = await client.post("/api/auth/token", data={"username": "fixture", "password": "wrong"})
    assert response.status_code == 401, response.text
    async with factory() as observer:
        user = await observer.scalar(select(User).where(User.uid == "fixture"))
        assert user.login_failed_count == 1
        assert user.login_locked_until is None


@pytest.mark.parametrize(("state", "expected"), [("unknown", 401), ("end_user", 401), ("deleted", 403), ("rate_limited", 429)])
async def test_rejected_identity_never_records_success(login_boundary, monkeypatch, state, expected):
    """拒绝原因映射保留状态与header，拒绝不会产生成功登录状态。"""
    client, factory = login_boundary
    identifier = "missing" if state == "unknown" else "fixture"
    async with factory() as db, db.begin():
        user = await db.scalar(select(User).where(User.uid == "fixture"))
        if state == "end_user":
            owner = User(username="Owner", uid="owner", password_hash="disabled", role="admin")
            db.add(owner)
            await db.flush()
            user.user_kind = "end_user"
            user.owner_user_id = owner.id
            user.app_id = "fixture-app"
            user.end_user_id = "fixture-end-user"
        elif state == "deleted":
            user.is_deleted = 1
    if state == "rate_limited":
        monkeypatch.setattr(password_login, "check_login_rate_limit", AsyncMock(return_value=(False, 17)))
    response = await client.post("/api/auth/token", data={"username": identifier, "password": "fixture-password"})
    assert response.status_code == expected, response.text
    if state == "rate_limited":
        assert response.headers["Retry-After"] == "17"
    else:
        assert response.headers["WWW-Authenticate"] == "Bearer"
    async with factory() as observer:
        user = await observer.scalar(select(User).where(User.uid == "fixture"))
        assert user.last_login is None
        assert user.login_failed_count == 0


async def test_failed_commit_does_not_return_token_or_login_state(login_boundary, monkeypatch):
    """提交失败不会发布成功响应，未提交的身份状态回滚。"""
    client, factory = login_boundary

    async def fail_commit(self):
        """在提交点注入故障。"""
        raise RuntimeError("injected commit failure")

    monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    response = await client.post("/api/auth/token", data={"username": "fixture", "password": "fixture-password"})
    assert response.status_code == 500
    assert "access_token" not in response.text
    async with factory() as observer:
        user = await observer.scalar(select(User).where(User.uid == "fixture"))
        assert user.last_login is None
