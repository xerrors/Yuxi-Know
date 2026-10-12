"""在隔离 PostgreSQL schema 中验证 OIDC 登录的原子身份事实。"""

from __future__ import annotations

import asyncio
import hashlib
import os
import socket
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
import uvicorn
from fastapi import FastAPI
from yuxi.api.errors import domain_error_handler
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.bootstrap.models import load_models
from yuxi.infrastructure.postgres.base import BusinessBase
from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.modules.identity import oidc
from yuxi.modules.identity.models import Department, User
from yuxi.modules.identity.services.oidc import build_oidc_login_response
from yuxi.shared.errors import DomainError, OperationFailedError, StateConflictError

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


@pytest_asyncio.fixture
async def identity_db(monkeypatch):
    """所有生产 repository 都限制在本测试独占的 schema。"""
    load_models()
    schema = f"pytest_oidc_{uuid4().hex}"
    admin = create_async_engine(os.environ["POSTGRES_URL"])
    engine = create_async_engine(os.environ["POSTGRES_URL"], connect_args={"server_settings": {"search_path": schema}})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        async with engine.begin() as conn:
            await conn.run_sync(BusinessBase.metadata.create_all)

        @asynccontextmanager
        async def isolated_session():
            """让负控中的旧独立事务也只访问隔离数据。"""
            async with factory() as db:
                async with db.begin():
                    yield db

        monkeypatch.setattr(pg_manager, "get_async_session_context", isolated_session)
        monkeypatch.setattr(oidc.oidc_config, "auto_create_user", True)
        monkeypatch.setattr(oidc.oidc_config, "default_department", "oidc-test-department")
        monkeypatch.setattr(oidc.oidc_config, "default_role", "user")
        monkeypatch.setattr(oidc.AuthUtils, "create_access_token", lambda data: f"fixture-user-{data['sub']}")
        yield factory
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


@pytest.mark.parametrize("raw_username", [False, True])
async def test_failed_login_rolls_back_department_user_and_binding(identity_db, monkeypatch, raw_username):
    """响应装配失败时，独立事务不能读到半套开户数据。"""
    monkeypatch.setattr(oidc.oidc_config, "use_raw_username", raw_username)

    def fail_token(_data):
        """在所有身份写入之后制造确定性失败。"""
        raise RuntimeError("injected token failure")

    monkeypatch.setattr(oidc.AuthUtils, "create_access_token", fail_token)
    async with identity_db() as db:
        with pytest.raises(RuntimeError, match="injected token failure"):
            await build_oidc_login_response(db, {"sub": "tenant:test", "name": "reader", "username": "reader"})
        async with identity_db() as observer:
            assert await observer.scalar(select(func.count()).select_from(Department)) == 0
            assert await observer.scalar(select(func.count()).select_from(User)) == 0


@pytest.mark.parametrize("raw_username", [False, True])
async def test_concurrent_oidc_login_commits_one_complete_identity(identity_db, monkeypatch, raw_username):
    """同一身份并发登录最终只保存一个部门、用户和所需绑定。"""
    monkeypatch.setattr(oidc.oidc_config, "use_raw_username", raw_username)

    async def login():
        """使用独立请求事务执行真实开户用例。"""
        async with identity_db() as db:
            return await build_oidc_login_response(db, {"sub": "tenant:test", "name": "reader", "username": "reader"})

    responses = await asyncio.gather(login(), login())
    assert all(error is None for _, error in responses)
    assert responses[0][0]["user_id"] == responses[1][0]["user_id"]
    async with identity_db() as observer:
        assert await observer.scalar(select(func.count()).select_from(Department)) == 1
        users = (await observer.scalars(select(User))).all()
        assert len(users) == (2 if raw_username else 1)
        active = [user for user in users if not user.is_deleted]
        assert len(active) == 1
        assert active[0].department_id is not None
        if raw_username:
            assert next(user for user in users if user.is_deleted).uid == f"oidc:tenant:test:{active[0].id}"


async def test_binding_collision_does_not_commit_unbound_account(identity_db, monkeypatch):
    """无关的绑定用户名冲突不能伪装绑定成功或留下新账号。"""
    monkeypatch.setattr(oidc.oidc_config, "use_raw_username", True)
    username = "oidc-binding-" + hashlib.sha256(b"tenant:test").hexdigest()[:8]
    async with identity_db() as db:
        db.add(User(username=username, uid="unrelated", password_hash="disabled", role="user"))
        await db.commit()
    async with identity_db() as db:
        with pytest.raises(DomainError) as exc:
            await build_oidc_login_response(db, {"sub": "tenant:test", "name": "reader", "username": "reader"})
        assert isinstance(exc.value, OperationFailedError)
    async with identity_db() as observer:
        assert list(await observer.scalars(select(User.uid))) == ["unrelated"]
        assert await observer.scalar(select(func.count()).select_from(Department)) == 0


async def test_concurrent_sub_cannot_bind_two_raw_usernames(identity_db, monkeypatch):
    """初次读取都未绑定时，失败方不能获得另一 raw username 的令牌。"""
    monkeypatch.setattr(oidc.oidc_config, "use_raw_username", True)
    lookup = oidc.find_user_by_oidc_sub
    both_read = asyncio.Event()
    reads = 0

    async def synchronize_first_lookup(db, sub):
        """让两个请求都在开户前观察到未绑定身份。"""
        nonlocal reads
        result = await lookup(db, sub)
        reads += 1
        if reads <= 2:
            if reads == 2:
                both_read.set()
            await asyncio.wait_for(both_read.wait(), 5)
        return result

    monkeypatch.setattr(oidc, "find_user_by_oidc_sub", synchronize_first_lookup)

    async def login(username):
        """保留返回或异常，随后独立核对唯一获胜身份。"""
        async with identity_db() as db:
            try:
                return await build_oidc_login_response(
                    db, {"sub": "tenant:test", "name": username, "username": username, "department_name": username}
                )
            except DomainError as exc:
                return exc

    results = await asyncio.gather(login("reader-a"), login("reader-b"))
    successes = [result[0]["user_id"] for result in results if isinstance(result, tuple) and result[1] is None]
    assert len(successes) == 1
    failure = next(result for result in results if isinstance(result, DomainError))
    assert isinstance(failure, StateConflictError)
    async with identity_db() as observer:
        users = list(await observer.scalars(select(User)))
        assert len(users) == 2
        active = next(user for user in users if not user.is_deleted)
        assert active.id == successes[0]
        assert next(user for user in users if user.is_deleted).uid == f"oidc:tenant:test:{active.id}"
        assert list(await observer.scalars(select(Department.name))) == [active.uid]


@pytest_asyncio.fixture
async def oidc_http(identity_db, monkeypatch):
    """通过真实 TCP 运行生产认证路由，身份数据使用隔离 PG。"""
    from yuxi.api.dependencies.auth import get_db
    from yuxi.api.routers.identity.auth import auth

    async def request_db():
        """给请求提供隔离事务；service 负责提交。"""
        async with identity_db() as db:
            yield db

    async def exchange(_code):
        """固定外部 provider 的成功身份输入。"""
        return {"access_token": "fixture-provider-token"}

    async def userinfo(_token):
        """返回不依赖外部账号的测试身份。"""
        return {"sub": "tenant:test", "preferred_username": "reader"}

    monkeypatch.setattr(oidc.oidc_config, "use_raw_username", True)
    monkeypatch.setattr(oidc.oidc_config, "enabled", True)
    monkeypatch.setattr(oidc.oidc_config, "client_id", "fixture-client")
    monkeypatch.setattr(oidc.oidc_config, "client_secret", "fixture-secret")
    monkeypatch.setattr(oidc.oidc_config, "token_endpoint", "https://example.test/token")
    monkeypatch.setattr(oidc.OIDCUtils, "exchange_code_for_token", exchange)
    monkeypatch.setattr(oidc.OIDCUtils, "get_userinfo", userinfo)
    monkeypatch.setattr(oidc.OIDCUtils, "_state_store", {})
    monkeypatch.setattr(oidc.OIDCUtils, "_login_code_store", {})
    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error_handler)
    app.include_router(auth, prefix="/api")
    app.dependency_overrides[get_db] = request_db
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", lifespan="off"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(5):
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError("OIDC test server did not start")
                await asyncio.sleep(0.01)
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
            yield client
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        sock.close()


@pytest.mark.parametrize("fail_commit", [False, True])
async def test_http_callback_publishes_code_only_after_commit(oidc_http, identity_db, monkeypatch, fail_commit):
    """提交失败返回错误且无身份残留；成功 code 对应独立回读的身份。"""
    if fail_commit:

        async def reject_commit(_self):
            """在事务最终提交边界注入失败。"""
            raise RuntimeError("injected commit failure")

        monkeypatch.setattr(identity_db.class_, "commit", reject_commit)
    state = oidc.OIDCUtils.generate_state()
    response = await oidc_http.get("/api/auth/oidc/callback", params={"code": "fixture", "state": state})
    async with identity_db() as observer:
        users = list(await observer.scalars(select(User)))
        departments = list(await observer.scalars(select(Department)))
    if fail_commit:
        assert response.status_code == 500
        assert users == []
        assert departments == []
        assert oidc.OIDCUtils._login_code_store == {}
        return
    assert response.status_code == 302
    code = parse_qs(urlparse(response.headers["location"]).query)["code"][0]
    exchanged = await oidc_http.post("/api/auth/oidc/exchange-code", json={"code": code})
    assert exchanged.status_code == 200
    active = next(user for user in users if not user.is_deleted)
    assert exchanged.json()["user_id"] == active.id
    assert len(departments) == 1
    assert active.department_id == departments[0].id
    replay = await oidc_http.post("/api/auth/oidc/exchange-code", json={"code": code})
    assert replay.status_code == 400
