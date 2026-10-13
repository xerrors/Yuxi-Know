"""真实 PostgreSQL、Redis、TCP provider 与 API 验证 OIDC 安全边界。"""

import asyncio
import base64
import hashlib
import os
import secrets
import socket
import time
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import jwt
import pytest
import pytest_asyncio
import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request
from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.api.dependencies.auth import get_db
from yuxi.api.errors import domain_error_handler
from yuxi.api.routers.identity.auth import auth
from yuxi.infrastructure.oidc.client import LOGOUT_EVENT, OIDCClient
from yuxi.modules.identity import oidc
from yuxi.modules.identity.models import Department, OIDCIdentity, OIDCLogout, OIDCSession, RevokedAccessToken, User
from yuxi.modules.identity.security import AuthUtils
from yuxi.modules.identity.services import oidc as service
from yuxi.shared.datetime import utc_now
from yuxi.shared.errors import DomainError

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


@pytest_asyncio.fixture
async def scenario(monkeypatch):
    """独立 schema 和真实 Redis，provider 使用测试 RSA 密钥并验证 PKCE。"""
    schema = "pytest_oidc_" + uuid4().hex
    admin = create_async_engine(os.environ["POSTGRES_URL"])
    engine = create_async_engine(os.environ["POSTGRES_URL"], connect_args={"server_settings": {"search_path": schema}})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    redis = Redis.from_url(os.environ["REDIS_URL"])
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    import json

    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())) | {"kid": "fixture-key", "use": "sig", "alg": "RS256"}
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    origin = f"http://127.0.0.1:{sock.getsockname()[1]}"
    config = oidc.OIDCConfig(
        enabled=True,
        issuer_url=origin + "/issuer",
        client_id="fixture-client",
        client_secret="fixture-secret",
        redirect_uri=origin + "/api/auth/oidc/callback",
    )
    monkeypatch.setattr(oidc, "oidc_config", config)
    monkeypatch.setattr(service, "client", OIDCClient())

    async def get_redis():
        """测试消费真实共享暂态存储。"""
        return redis

    monkeypatch.setattr(service, "get_async_redis_client", get_redis)
    current = {"subject": "fixture-sub", "sid": "fixture-sid", "claims": {}, "userinfo": {}, "keys": [jwk], "calls": 0}
    codes = {}
    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error_handler)
    app.include_router(auth, prefix="/api")

    async def request_db():
        """每个请求独立事务，只触碰测试 schema。"""
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = request_db

    @app.get("/issuer2/.well-known/openid-configuration")
    @app.get("/issuer/.well-known/openid-configuration")
    async def discovery():
        """固定公开协议，不从实现生成预期 claims。"""
        return {
            "issuer": current.get("discovery_issuer", config.issuer_url),
            "authorization_endpoint": origin + "/authorize",
            "token_endpoint": origin + "/token",
            "userinfo_endpoint": origin + "/userinfo",
            "jwks_uri": origin + "/jwks",
            "end_session_endpoint": origin + "/logout",
            "id_token_signing_alg_values_supported": ["RS256"],
        }

    @app.get("/jwks")
    async def jwks():
        """仅发布测试公钥。"""
        current["jwks_calls"] = current.get("jwks_calls", 0) + 1
        return {"keys": current["keys"]}

    @app.post("/token")
    async def token(request: Request):
        """真实 HTTP token 端点校验 client、回调及授权时固定的 PKCE。"""
        form = await request.form()
        code = form["code"]
        expected = codes.pop(code)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest()).rstrip(b"=").decode()
        assert challenge == expected["challenge"]
        assert form["redirect_uri"] == config.redirect_uri and form["client_secret"] == "fixture-secret"
        current["calls"] += 1
        now = int(time.time())
        claims = {
            "iss": config.issuer_url,
            "aud": "fixture-client",
            "sub": current["subject"],
            "sid": current["sid"],
            "iat": now,
            "exp": now + 120,
            "nonce": expected["nonce"],
        } | current["claims"]
        for name in current.get("omit", []):
            claims.pop(name, None)
        signed = jwt.encode(claims, current.get("signing_key", key), algorithm="RS256", headers={"kid": current.get("kid", "fixture-key")})
        return {"access_token": "fixture-access-token", "token_type": "Bearer", "id_token": signed}

    @app.get("/userinfo")
    async def userinfo(request: Request):
        """UserInfo 的独立 sub 不能替换已验证的 ID token。"""
        assert request.headers["authorization"] == "Bearer fixture-access-token"
        return {"sub": current["subject"], "preferred_username": "alice", "name": "Fixture user"} | current["userinfo"]

    server = uvicorn.Server(uvicorn.Config(app, lifespan="off", log_level="critical", access_log=False))
    task = None
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        async with engine.begin() as conn:
            for model in (Department, User, OIDCIdentity, OIDCSession, OIDCLogout, RevokedAccessToken):
                await conn.run_sync(lambda sync, model=model: model.__table__.create(sync))
        task = asyncio.create_task(server.serve(sockets=[sock]))
        async with asyncio.timeout(10):
            while not server.started:
                await asyncio.sleep(0.01)
        async with httpx.AsyncClient(base_url=origin, trust_env=False, follow_redirects=False) as http:
            yield {
                "http": http,
                "db": factory,
                "config": config,
                "current": current,
                "codes": codes,
                "key": key,
                "redis": redis,
                "jwk": jwk,
            }
    finally:
        if task:
            server.should_exit = True
            await asyncio.wait_for(task, 10)
        sock.close()
        await redis.aclose()
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()


async def begin(scenario):
    """实际授权入口产生可供固定 provider 校验的 code。"""
    response = await scenario["http"].get("/api/auth/oidc/login-url")
    assert response.status_code == 200, response.text
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=lax" in response.headers["set-cookie"].lower()
    params = parse_qs(urlsplit(response.json()["login_url"]).query)
    assert params["code_challenge_method"] == ["S256"] and len(params["nonce"][0]) >= 32
    code = secrets.token_urlsafe(20)
    scenario["codes"][code] = {"challenge": params["code_challenge"][0], "nonce": params["nonce"][0]}
    return {"code": code, "state": params["state"][0]}


async def callback(scenario, params):
    """callback 只传递短期结果，不暴露 JWT。"""
    response = await scenario["http"].get("/api/auth/oidc/callback", params=params)
    assert response.status_code == 302
    assert response.headers["cache-control"] == "no-store"
    return parse_qs(urlsplit(response.headers["location"]).query)


async def login(scenario):
    """浏览器完成完整认证后获取本地会话。"""
    query = await callback(scenario, await begin(scenario))
    assert set(query) == {"code"}, query
    response = await scenario["http"].post("/api/auth/oidc/exchange-code", json={"code": query["code"][0]})
    assert response.status_code == 200, response.text
    return response.json(), query["code"][0]


async def logout_token(scenario, **overrides):
    """独立生成符合规范的远端注销通知。"""
    now = int(time.time())
    claims = {
        "iss": scenario["config"].issuer_url,
        "aud": "fixture-client",
        "iat": now,
        "exp": now + 120,
        "jti": uuid4().hex,
        "events": {LOGOUT_EVENT: {}},
        "sid": "fixture-sid",
    } | overrides
    claims = {key: value for key, value in claims.items() if value is not None}
    token = jwt.encode(claims, scenario["key"], algorithm="RS256", headers={"kid": "fixture-key"})
    return await scenario["http"].post("/api/auth/oidc/backchannel-logout", data={"logout_token": token})


async def test_concurrent_login_commits_one_identity_and_retries_same_result(scenario):
    """并发登录仅创建一个普通账号，结果重试不另发会话。"""
    await begin(scenario)
    # 建立浏览器 cookie 后并发创建两份独立事务。
    left, right = await asyncio.gather(begin(scenario), begin(scenario))
    results = await asyncio.gather(callback(scenario, left), callback(scenario, right))
    responses = []
    for result in results:
        code = result["code"][0]
        first, retry = await asyncio.gather(*[scenario["http"].post("/api/auth/oidc/exchange-code", json={"code": code}) for _ in range(2)])
        assert first.status_code == retry.status_code == 200 and first.json() == retry.json()
        responses.append(first.json())
    assert responses[0]["user_id"] == responses[1]["user_id"] and responses[0]["role"] == "user"
    async with scenario["db"]() as db:
        assert await db.scalar(select(func.count()).select_from(User)) == 1
        assert await db.scalar(select(func.count()).select_from(OIDCIdentity)) == 1
        assert await db.scalar(select(func.count()).select_from(OIDCSession)) == 2


@pytest.mark.parametrize(
    "claims,omit",
    [
        ({"iss": "https://other.example"}, []),
        ({"aud": "other-client"}, []),
        ({"aud": ["fixture-client", "untrusted"]}, []),
        ({"azp": "other-client"}, []),
        ({"nonce": "wrong"}, []),
        ({"exp": 1}, []),
        ({"iat": 1}, []),
        ({"iat": True}, []),
        ({"sub": ""}, []),
        ({"at_hash": "wrong"}, []),
        ({}, ["nonce"]),
        ({}, ["sub"]),
        ({}, ["exp"]),
    ],
)
async def test_invalid_signed_claims_never_create_account(scenario, claims, omit):
    """有效签名不能替代绑定、受众和有效期校验，失败不留开户数据。"""
    scenario["current"].update(claims=claims, omit=omit)
    result = await callback(scenario, await begin(scenario))
    assert "oidc_error" in result
    async with scenario["db"]() as db:
        assert await db.scalar(select(func.count()).select_from(User)) == 0
        assert await db.scalar(select(func.count()).select_from(OIDCSession)) == 0


async def test_wrong_signature_and_userinfo_subject_are_rejected(scenario):
    """第三方私钥或另一个 UserInfo 身份不能登录。"""
    scenario["current"]["signing_key"] = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert "oidc_error" in await callback(scenario, await begin(scenario))
    del scenario["current"]["signing_key"]
    scenario["current"]["userinfo"] = {"sub": "someone-else"}
    assert "oidc_error" in await callback(scenario, await begin(scenario))
    async with scenario["db"]() as db:
        assert await db.scalar(select(func.count()).select_from(User)) == 0


async def test_wrong_browser_cannot_consume_state_or_result_and_replay_fails(scenario):
    """错误浏览器不消耗合法事务，正确 state 仅可消费一次。"""
    pending = await begin(scenario)
    cookie = scenario["http"].cookies.get(oidc.COOKIE_NAME)
    scenario["http"].cookies.clear()
    assert "oidc_error" in await callback(scenario, pending)
    assert scenario["current"]["calls"] == 0
    scenario["http"].cookies.set(oidc.COOKIE_NAME, cookie)
    result = await callback(scenario, pending)
    assert "code" in result
    assert "oidc_error" in await callback(scenario, pending)
    assert scenario["current"]["calls"] == 1
    scenario["http"].cookies.clear()
    assert (await scenario["http"].post("/api/auth/oidc/exchange-code", json={"code": result["code"][0]})).status_code == 409
    scenario["http"].cookies.set(oidc.COOKIE_NAME, cookie)
    assert (await scenario["http"].post("/api/auth/oidc/exchange-code", json={"code": result["code"][0]})).status_code == 200


async def test_state_and_result_survive_service_restart_and_expire(scenario, monkeypatch):
    """替换无状态 service/client 实例，结果仍由 Redis 与 PG 共同决定。"""
    pending = await begin(scenario)
    monkeypatch.setattr(service, "client", OIDCClient())
    result = await callback(scenario, pending)
    assert "code" in result
    key = service.OIDCService().prefix + "result:" + result["code"][0]
    await scenario["redis"].expire(key, 0)
    assert (await scenario["http"].post("/api/auth/oidc/exchange-code", json={"code": result["code"][0]})).status_code == 409
    pending = await begin(scenario)
    await scenario["redis"].expire(service.OIDCService().prefix + "state:" + pending["state"], 0)
    assert "oidc_error" in await callback(scenario, pending)


async def test_same_display_name_never_binds_local_account_and_deleted_account_never_restores(scenario):
    """同名本地管理员不被自动合并，注销身份仍保持拒绝。"""
    async with scenario["db"]() as db:
        db.add(User(uid="alice", username="Fixture user", password_hash="!fixture", role="superadmin"))
        await db.commit()
    response, code = await login(scenario)
    assert response["uid"] != "alice" and response["role"] == "user"
    async with scenario["db"]() as db:
        user = await db.get(User, response["user_id"])
        user.is_deleted = 1
        await db.commit()
    assert "oidc_error" in await callback(scenario, await begin(scenario))
    assert (await scenario["http"].post("/api/auth/oidc/exchange-code", json={"code": code})).status_code == 403
    async with scenario["db"]() as db:
        assert (await db.get(User, response["user_id"])).is_deleted == 1
        assert await db.scalar(select(func.count()).select_from(User)) == 2


async def test_local_logout_revokes_jwt_and_exchange_without_affecting_other_sessions(scenario):
    """本地退出和响应重放不会复活 JWT，其他浏览器继续有效。"""
    first, code = await login(scenario)
    second, _ = await login(scenario)
    headers = {"Authorization": "Bearer " + first["access_token"]}
    result = await scenario["http"].post("/api/auth/oidc/logout", headers=headers)
    assert result.status_code == 200 and result.json() == {"logout_url": None}
    assert (await scenario["http"].get("/api/auth/me", headers=headers)).status_code == 401
    assert (await scenario["http"].post("/api/auth/oidc/exchange-code", json={"code": code})).status_code == 403
    assert (await scenario["http"].get("/api/auth/me", headers={"Authorization": "Bearer " + second["access_token"]})).status_code == 200


async def test_backchannel_logout_is_atomic_idempotent_and_blocks_late_authentication(scenario):
    """登出撤销真实会话，并阻止已发起的同一远端会话晚回调。"""
    response, code = await login(scenario)
    pending = await begin(scenario)
    jti = uuid4().hex
    assert (await logout_token(scenario, jti=jti)).status_code == 200
    assert (await logout_token(scenario, jti=jti)).status_code == 200
    assert (await scenario["http"].get("/api/auth/me", headers={"Authorization": "Bearer " + response["access_token"]})).status_code == 401
    assert (await scenario["http"].post("/api/auth/oidc/exchange-code", json={"code": code})).status_code == 403
    assert "oidc_error" in await callback(scenario, pending)
    async with scenario["db"]() as db:
        assert await db.scalar(select(func.count()).select_from(OIDCLogout)) == 1
        assert (await db.scalar(select(OIDCSession))).revoked_at is not None


async def test_unknown_sid_does_not_revoke_other_sessions_and_bad_notification_fails(scenario):
    """sid 与 sub 同时出现必须都匹配，坏通知不写事件或撤销。"""
    response, _ = await login(scenario)
    for values in [{"nonce": "forbidden"}, {"events": {}}, {"exp": 1}, {"aud": "wrong"}]:
        assert (await logout_token(scenario, **values)).status_code == 400
    async with scenario["db"]() as db:
        assert await db.scalar(select(func.count()).select_from(OIDCLogout)) == 0
    assert (await logout_token(scenario, sid="unknown", sub="fixture-sub")).status_code == 200
    assert (await scenario["http"].get("/api/auth/me", headers={"Authorization": "Bearer " + response["access_token"]})).status_code == 200


async def test_discovery_issuer_mismatch_fails_before_authorization(scenario):
    """发现文档不能替换部署时固定的身份提供商。"""
    scenario["current"]["discovery_issuer"] = "https://other.example"
    assert (await scenario["http"].get("/api/auth/oidc/login-url")).status_code == 502


async def test_failed_session_signing_rolls_back_all_identity_data(scenario, monkeypatch):
    """身份持久化后 token 签发失败不能留下半套开户结果。"""

    def fail(*args, **kwargs):
        """确定性注入最后提交之前的故障。"""
        raise RuntimeError("fixture signing failure")

    monkeypatch.setattr(AuthUtils, "create_access_token", fail)
    response = await scenario["http"].get("/api/auth/oidc/callback", params=await begin(scenario))
    assert response.status_code == 500
    async with scenario["db"]() as db:
        assert await db.scalar(select(func.count()).select_from(User)) == 0
        assert await db.scalar(select(func.count()).select_from(Department)) == 0
        assert await db.scalar(select(func.count()).select_from(OIDCSession)) == 0


async def test_old_raw_binding_jwt_is_rejected_but_fresh_password_login_remains(scenario):
    """旧同名绑定 JWT 不可逃逸会话控制，重新验证密码后可独立登录。"""
    response, _ = await login(scenario)
    async with scenario["db"]() as db:
        user = await db.get(User, response["user_id"])
        user.uid = "legacy-alice"
        user.password_hash = AuthUtils.hash_password("fixture-correct-password")
        db.add(User(uid="local-only", username="local-only", password_hash="!fixture", role="user", department_id=user.department_id))
        await db.commit()
        local_id = await db.scalar(select(User.id).where(User.uid == "local-only"))
    scenario["config"].enabled = False
    old = AuthUtils.create_access_token({"sub": str(response["user_id"])})
    assert (await scenario["http"].get("/api/auth/me", headers={"Authorization": "Bearer " + old})).status_code == 401
    pure_local = AuthUtils.create_access_token({"sub": str(local_id)})
    assert (await scenario["http"].get("/api/auth/me", headers={"Authorization": "Bearer " + pure_local})).status_code == 200
    password = await scenario["http"].post("/api/auth/token", data={"username": "legacy-alice", "password": "fixture-correct-password"})
    assert password.status_code == 200, password.text
    token = password.json()["access_token"]
    assert AuthUtils.verify_access_token(token)["auth_method"] == "password"
    assert (await scenario["http"].get("/api/auth/me", headers={"Authorization": "Bearer " + token})).status_code == 200
    assert (await scenario["http"].get("/api/auth/me", headers={"Authorization": "Bearer " + response["access_token"]})).status_code == 401


async def test_local_logout_never_contacts_provider(scenario, monkeypatch):
    """本地退出不得读取认证中心元数据或发起共享 SSO 退出。"""

    response, _ = await login(scenario)

    async def unavailable(_config):
        """明确模拟元数据服务不可达。"""
        raise AssertionError("local logout must not contact provider")

    monkeypatch.setattr(service.client, "metadata", unavailable)
    headers = {"Authorization": "Bearer " + response["access_token"]}
    result = await scenario["http"].post("/api/auth/oidc/logout", headers=headers)
    assert result.status_code == 200 and result.json() == {"logout_url": None}
    assert (await scenario["http"].get("/api/auth/me", headers=headers)).status_code == 401


async def test_unknown_key_refresh_is_bounded_and_rotated_key_is_accepted(scenario):
    """攻击者未知 kid 不可触发逐请求取钥，冷却后合法轮换可以登录。"""
    import json

    await login(scenario)
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    new_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(new_key.public_key())) | {"kid": "rotated", "alg": "RS256", "use": "sig"}
    scenario["current"].update(signing_key=new_key, kid="rotated", keys=[new_jwk])
    for _ in range(2):
        assert "oidc_error" in await callback(scenario, await begin(scenario))
    assert scenario["current"]["jwks_calls"] == 1
    metadata = await service.client.metadata(scenario["config"])
    metadata["keys_checked"] -= 31
    response, _ = await login(scenario)
    assert response["role"] == "user" and scenario["current"]["jwks_calls"] == 2


async def test_failed_backchannel_transaction_can_retry_same_notification(scenario, monkeypatch):
    """撤销失败不得单独记为已消费，重试同一个 jti 后真正失效。"""
    from yuxi.modules.identity.repositories.oidc import OIDCRepository

    response, _ = await login(scenario)
    original = OIDCRepository.backchannel_logout

    async def fail(self, config, claims):
        """写入真实撤销后在提交前注入失败。"""
        await original(self, config, claims)
        await self.db.flush()
        raise RuntimeError("fixture commit failure")

    jti = uuid4().hex
    with monkeypatch.context() as patch:
        patch.setattr(OIDCRepository, "backchannel_logout", fail)
        assert (await logout_token(scenario, jti=jti)).status_code == 500
    async with scenario["db"]() as db:
        assert await db.scalar(select(func.count()).select_from(OIDCLogout)) == 0
        assert (await db.scalar(select(OIDCSession))).revoked_at is None
    assert (await logout_token(scenario, jti=jti)).status_code == 200
    assert (await scenario["http"].get("/api/auth/me", headers={"Authorization": "Bearer " + response["access_token"]})).status_code == 401


@pytest.mark.parametrize("state", ["locked", "end_user", "expired"])
async def test_changed_account_or_expired_session_cannot_exchange_or_authenticate(scenario, state):
    """新结果和旧 JWT 都重新读取账号与会话当前状态。"""
    response, code = await login(scenario)
    async with scenario["db"]() as db:
        user = await db.get(User, response["user_id"])
        if state == "locked":
            user.login_locked_until = utc_now() + timedelta(minutes=5)
        elif state == "end_user":
            owner = User(uid="fixture-owner", username="fixture-owner", password_hash="!fixture", role="user")
            db.add(owner)
            await db.flush()
            user.user_kind = "end_user"
            user.owner_user_id = owner.id
            user.app_id = "fixture-app"
            user.end_user_id = "fixture-external"
            user.department_id = None
        else:
            (await db.scalar(select(OIDCSession))).expires_at = utc_now() - timedelta(seconds=1)
        await db.commit()
    assert (await scenario["http"].post("/api/auth/oidc/exchange-code", json={"code": code})).status_code == 403
    assert (await scenario["http"].get("/api/auth/me", headers={"Authorization": "Bearer " + response["access_token"]})).status_code in {
        401,
        403,
        423,
    }
    if state != "expired":
        assert "oidc_error" in await callback(scenario, await begin(scenario))


async def test_sid_logout_revokes_same_session_despite_token_issuance_race(scenario):
    """同一 sid 的通知不受并发签发时间先后影响，晚签发也不可恢复。"""
    response, _ = await login(scenario)
    pending = await begin(scenario)
    assert (await logout_token(scenario, iat=int(time.time()) - 1)).status_code == 200
    assert (await scenario["http"].get("/api/auth/me", headers={"Authorization": "Bearer " + response["access_token"]})).status_code == 401
    assert "oidc_error" in await callback(scenario, pending)
    scenario["current"]["sid"] = "new-provider-session"
    assert (await login(scenario))[0]["user_id"] == response["user_id"]


async def test_same_subject_at_different_issuer_is_a_separate_identity(scenario):
    """相同 sub 不能跨认证中心复用本地身份。"""
    first, _ = await login(scenario)
    scenario["config"].issuer_url += "2"
    second, _ = await login(scenario)
    assert first["user_id"] != second["user_id"]
    async with scenario["db"]() as db:
        assert await db.scalar(select(func.count()).select_from(OIDCIdentity)) == 2


async def test_subject_logout_revokes_prior_sessions_but_allows_new_authentication(scenario):
    """仅 sub 通知撤销该人的旧会话，保留其他人和通知之后的新认证。"""
    first, _ = await login(scenario)
    scenario["current"].update(sid="second-session")
    second, _ = await login(scenario)
    scenario["current"].update(subject="another-person", sid="another-session")
    other, _ = await login(scenario)
    issued = int(time.time())
    assert (await logout_token(scenario, sid=None, sub="fixture-sub", iat=issued)).status_code == 200
    for response in [first, second]:
        assert (
            await scenario["http"].get("/api/auth/me", headers={"Authorization": "Bearer " + response["access_token"]})
        ).status_code == 401
    assert (await scenario["http"].get("/api/auth/me", headers={"Authorization": "Bearer " + other["access_token"]})).status_code == 200
    scenario["current"].update(subject="fixture-sub", sid="new-session", claims={"iat": issued + 1})
    assert (await login(scenario))[0]["user_id"] == first["user_id"]


async def test_two_http_api_instances_share_browser_transaction_and_result(scenario, monkeypatch):
    """另一真实 HTTP 实例可接管回调和重试，事务不依赖原进程内存。"""
    pending = await begin(scenario)
    replica = FastAPI()
    replica.add_exception_handler(DomainError, domain_error_handler)
    replica.include_router(auth, prefix="/api")

    async def replica_db():
        """副本通过独立数据库会话读取相同持久事实。"""
        async with scenario["db"]() as db:
            yield db

    replica.dependency_overrides[get_db] = replica_db
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(replica, lifespan="off", log_level="critical", access_log=False))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                await asyncio.sleep(0.01)
        monkeypatch.setattr(service, "client", OIDCClient())
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{sock.getsockname()[1]}", cookies=scenario["http"].cookies, trust_env=False
        ) as http:
            result = await callback(scenario | {"http": http}, pending)
            code = result["code"][0]
            left = await http.post("/api/auth/oidc/exchange-code", json={"code": code})
            right = await scenario["http"].post("/api/auth/oidc/exchange-code", json={"code": code})
            assert left.status_code == right.status_code == 200 and left.json() == right.json()
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 10)
        sock.close()


async def test_password_logout_revokes_only_current_token_and_preserves_oidc_session(scenario):
    """密码退出撤销当前 JWT，其他本地和企业登录会话不被结束。"""
    enterprise, _ = await login(scenario)
    async with scenario["db"]() as db:
        (await db.get(User, enterprise["user_id"])).password_hash = AuthUtils.hash_password("fixture-local-password")
        await db.commit()
    credentials = {"username": enterprise["uid"], "password": "fixture-local-password"}
    first = (await scenario["http"].post("/api/auth/token", data=credentials)).json()["access_token"]
    second = (await scenario["http"].post("/api/auth/token", data=credentials)).json()["access_token"]
    assert first != second
    assert (await scenario["http"].get("/api/auth/me", headers={"Authorization": "Bearer " + first + "="})).status_code == 200
    assert (await scenario["http"].post("/api/auth/oidc/logout", headers={"Authorization": "Bearer " + first})).status_code == 200
    assert (await scenario["http"].get("/api/auth/me", headers={"Authorization": "Bearer " + first})).status_code == 401
    assert (await scenario["http"].get("/api/auth/me", headers={"Authorization": "Bearer " + first + "="})).status_code == 401
    for token in [second, enterprise["access_token"]]:
        assert (await scenario["http"].get("/api/auth/me", headers={"Authorization": "Bearer " + token})).status_code == 200
    async with scenario["db"]() as db:
        assert await db.scalar(select(func.count()).select_from(RevokedAccessToken)) == 1
