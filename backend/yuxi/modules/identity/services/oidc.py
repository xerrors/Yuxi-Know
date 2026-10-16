"""OIDC 登录、结果发布和可撤销会话的事务用例。"""

import base64
import hashlib
import json
import secrets
from urllib.parse import urlencode

from sqlalchemy import select

from yuxi.infrastructure.oidc.client import client
from yuxi.infrastructure.redis import get_async_redis_client
from yuxi.modules.identity import oidc
from yuxi.modules.identity.models import Department
from yuxi.modules.identity.repositories.oidc import OIDCRepository
from yuxi.modules.identity.security import AuthUtils
from yuxi.modules.identity.services.login import login_result
from yuxi.shared.datetime import utc_now
from yuxi.shared.errors import PermissionDeniedError, StateConflictError

_MATCH = """
local raw = redis.call('GET', KEYS[1])
if not raw then return false end
local item = cjson.decode(raw)
if item.browser ~= ARGV[1] then return false end
if ARGV[2] == 'consume' then redis.call('DEL', KEYS[1]) end
return raw
"""


class OIDCService:
    """短期浏览器事务存 Redis，身份与撤销事实存 PostgreSQL。"""

    def __init__(self, db=None):
        self.db = db
        self.config = oidc.get_oidc_config()
        self.repo = OIDCRepository(db)
        namespace = hashlib.sha256(
            (self.config.issuer_url + "\0" + self.config.client_id + "\0" + self.config.redirect_uri).encode()
        ).hexdigest()
        self.prefix = "yuxi:oidc:" + namespace + ":"

    async def start(self, browser):
        """一次授权固定 nonce、PKCE verifier 和原始浏览器。"""
        self.require_enabled()
        metadata = await client.metadata(self.config)
        verifier = secrets.token_urlsafe(48)
        nonce, state = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        payload = {"browser": self.fingerprint(browser), "nonce": nonce, "verifier": verifier}
        redis = await get_async_redis_client()
        await redis.set(self.prefix + "state:" + state, json.dumps(payload), ex=oidc.STATE_TTL)
        params = {
            "client_id": self.config.client_id,
            "response_type": "code",
            "scope": self.config.scopes,
            "redirect_uri": self.config.redirect_uri,
            "state": state,
            "nonce": nonce,
            "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode(),
            "code_challenge_method": "S256",
        }
        if self.config.force_prompt_login:
            params["prompt"] = "login"
        return metadata["authorization_endpoint"] + "?" + urlencode(params)

    async def callback(self, code, state, browser, denied=False):
        """原子消费 state，验证全部远端证据后提交身份，再发布结果。"""
        self.require_enabled()
        transaction = await self.record("state", state, browser, consume=True)
        if denied or not code:
            raise PermissionDeniedError("登录已取消，请重新登录")
        claims, userinfo = await client.authenticate(self.config, code, transaction)
        try:
            session, user = await self.repo.create_session(self.config, claims, userinfo)
            token = AuthUtils.create_access_token(
                {"sub": str(user.id), "oidc_sid": session.id}, expires_delta=session.expires_at - utc_now()
            )
            payload = {"browser": transaction["browser"], "user_id": user.id, "session_id": session.id, "token": token}
            await self.db.commit()
        except BaseException:
            await self.db.rollback()
            raise
        result = secrets.token_urlsafe(32)
        redis = await get_async_redis_client()
        await redis.set(self.prefix + "result:" + result, json.dumps(payload), ex=oidc.RESULT_TTL)
        return result

    async def exchange(self, code, browser):
        """幂等恢复同一登录结果，每次兑换重新检查账号及会话撤销。"""
        self.require_enabled()
        payload = await self.record("result", code, browser)
        _, user = await self.repo.active_session(payload["session_id"], payload["user_id"], self.config.issuer_url, lock=True)
        department = (
            await self.db.scalar(select(Department.name).where(Department.id == user.department_id)) if user.department_id else None
        )
        response = login_result(user, payload["token"], department)
        await self.db.rollback()
        return response

    async def backchannel_logout(self, token):
        """只有专用签名通知可以撤销对应提供商的会话。"""
        self.require_enabled()
        claims = await client.verify(self.config, token, logout=True)
        try:
            await self.repo.backchannel_logout(self.config, claims)
            await self.db.commit()
        except BaseException:
            await self.db.rollback()
            raise

    def require_enabled(self):
        """关闭集成同时拒绝现有 OIDC 结果兑换。"""
        if not self.config.enabled:
            raise PermissionDeniedError("OIDC 登录未启用")

    @staticmethod
    def fingerprint(value):
        """短期存储只保存浏览器关联摘要。"""
        return hashlib.sha256(value.encode()).hexdigest()

    async def record(self, kind, code, browser, consume=False):
        """错误浏览器不能消耗合法事务；state 只允许成功消费一次。"""
        if not code or not browser:
            raise StateConflictError("登录会话已失效，请重新登录")
        redis = await get_async_redis_client()
        raw = await redis.eval(_MATCH, 1, self.prefix + kind + ":" + code, self.fingerprint(browser), "consume" if consume else "read")
        if not raw:
            raise StateConflictError("登录会话已失效，请重新登录")
        return json.loads(raw)
