"""OIDC 身份、会话与登出记录；提交边界由 service 拥有。"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert

from yuxi.infrastructure.oidc.client import MAX_TOKEN_AGE
from yuxi.modules.identity.models import Department, OIDCIdentity, OIDCLogout, OIDCSession, User
from yuxi.modules.identity.oidc import SESSION_TTL
from yuxi.shared.datetime import utc_now
from yuxi.shared.errors import PermissionDeniedError


class OIDCRepository:
    """提供商事务锁串行化短身份写入，远端调用始终在锁外。"""

    def __init__(self, db):
        self.db = db

    async def create_session(self, config, claims, userinfo):
        """远端登出事件先于会话发布时拒绝旧认证。"""
        await self.lock_provider(config.issuer_url)
        issued = datetime.fromtimestamp(claims["iat"], UTC)
        events = select(OIDCLogout.id).where(
            OIDCLogout.issuer == config.issuer_url,
            OIDCLogout.expires_at > utc_now(),
            OIDCLogout.provider_sid.is_not(None) | (OIDCLogout.issued_at >= issued),
        )
        events = events.where((OIDCLogout.subject.is_(None)) | (OIDCLogout.subject == claims["sub"]))
        events = events.where((OIDCLogout.provider_sid.is_(None)) | (OIDCLogout.provider_sid == claims.get("sid")))
        if await self.db.scalar(events.limit(1)):
            raise PermissionDeniedError("认证中心会话已退出，请重新登录")
        identity, user = await self.resolve_user(config, claims, userinfo)
        session = OIDCSession(
            id=secrets.token_urlsafe(32),
            identity_id=identity.id,
            provider_sid=claims.get("sid"),
            issued_at=issued,
            expires_at=utc_now() + timedelta(seconds=SESSION_TTL),
        )
        self.db.add(session)
        user.last_login = utc_now()
        await self.db.flush()
        return session, user

    async def active_session(self, session_id, user_id, issuer, *, lock=False):
        """认证和结果重试都回读账号、提供商和会话的当前状态。"""
        query = (
            select(OIDCSession, User)
            .join(OIDCIdentity, OIDCIdentity.id == OIDCSession.identity_id)
            .join(User, User.id == OIDCIdentity.user_id)
            .where(
                OIDCSession.id == session_id,
                User.id == user_id,
                OIDCIdentity.issuer == issuer,
                OIDCSession.revoked_at.is_(None),
                OIDCSession.expires_at > utc_now(),
            )
        )
        if lock:
            query = query.with_for_update(of=(OIDCSession, User))
        row = (await self.db.execute(query)).first()
        if not row:
            raise PermissionDeniedError("OIDC 会话已失效，请重新登录")
        self.require_active(row.User)
        return row.OIDCSession, row.User

    async def revoke_session(self, session_id, user_id):
        """当前本地会话退出幂等，不影响同人的其他浏览器会话。"""
        identity_ids = select(OIDCIdentity.id).where(OIDCIdentity.user_id == user_id)
        await self.db.execute(
            update(OIDCSession).where(OIDCSession.id == session_id, OIDCSession.identity_id.in_(identity_ids)).values(revoked_at=utc_now())
        )

    async def backchannel_logout(self, config, claims):
        """通知去重、晚认证阻断与匹配会话撤销在同一事务。"""
        await self.lock_provider(config.issuer_url)
        now = utc_now()
        await self.db.execute(delete(OIDCLogout).where(OIDCLogout.expires_at <= now))
        event_id = hashlib.sha256((config.issuer_url + "\0" + claims["jti"]).encode()).hexdigest()
        if await self.db.get(OIDCLogout, event_id):
            return
        issued = datetime.fromtimestamp(claims["iat"], UTC)
        self.db.add(
            OIDCLogout(
                id=event_id,
                issuer=config.issuer_url,
                subject=claims.get("sub"),
                provider_sid=claims.get("sid"),
                issued_at=issued,
                expires_at=max(datetime.fromtimestamp(claims["exp"], UTC), now) + timedelta(seconds=MAX_TOKEN_AGE + 60),
            )
        )
        identities = select(OIDCIdentity.id).where(OIDCIdentity.issuer == config.issuer_url)
        if claims.get("sub"):
            identities = identities.where(OIDCIdentity.subject == claims["sub"])
        query = update(OIDCSession).where(OIDCSession.identity_id.in_(identities))
        if claims.get("sid"):
            query = query.where(OIDCSession.provider_sid == claims["sid"])
        else:
            query = query.where(OIDCSession.issued_at <= issued)
        await self.db.execute(query.values(revoked_at=now))

    async def lock_provider(self, issuer):
        """登录和远端登出采用同一锁，避免登出与晚回调相互越过。"""
        key = int.from_bytes(hashlib.sha256(("oidc:" + issuer).encode()).digest()[:8], signed=True)
        await self.db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})

    async def resolve_user(self, config, claims, userinfo):
        """只按已验证 issuer+sub 开户或复用，名称仅用作展示。"""
        identity = await self.db.scalar(
            select(OIDCIdentity).where(OIDCIdentity.issuer == config.issuer_url, OIDCIdentity.subject == claims["sub"])
        )
        if identity:
            user = await self.db.scalar(select(User).where(User.id == identity.user_id).with_for_update())
            self.require_active(user)
            return identity, user
        if not config.auto_create_user:
            raise PermissionDeniedError("用户未开通，请联系管理员")
        department = config.default_department
        if config.fetch_department_info:
            value = userinfo.get(config.department_claim)
            if isinstance(value, str) and value.strip():
                department = value.strip()[:50]
        await self.db.execute(
            insert(Department).values(name=department, description="OIDC用户部门").on_conflict_do_nothing(index_elements=["name"])
        )
        department_id = await self.db.scalar(select(Department.id).where(Department.name == department))
        fingerprint = hashlib.sha256((config.issuer_url + "\0" + claims["sub"]).encode()).hexdigest()
        display = userinfo.get(config.name_claim) or userinfo.get(config.username_claim)
        display = display.strip()[:60] if isinstance(display, str) else ""
        # 固定 namespace 和随机显示名后缀不允许外部声明挑选本地账号。
        user = User(
            uid="oidc:" + fingerprint,
            username=(display or "企业用户") + "-" + secrets.token_hex(6),
            password_hash="!OIDC",
            role="user",
            department_id=department_id,
        )
        self.db.add(user)
        await self.db.flush()
        identity = OIDCIdentity(issuer=config.issuer_url, subject=claims["sub"], user_id=user.id)
        self.db.add(identity)
        await self.db.flush()
        return identity, user

    @staticmethod
    def require_active(user):
        """外部认证不能恢复注销账号、清除锁定或登录 Public end_user。"""
        if not user or user.is_deleted or user.user_kind != "human" or user.is_login_locked():
            raise PermissionDeniedError("账号不可用，请联系管理员")
