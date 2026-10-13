"""本地 JWT 撤销事实的持久查询。"""

import hashlib

from jwt.utils import base64url_decode
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from yuxi.modules.identity.models import RevokedAccessToken
from yuxi.shared.datetime import utc_now


class LoginSessionRepository:
    """只保存凭据摘要；过期清理由退出事务一起提交。"""

    def __init__(self, db):
        self.db = db

    async def revoke_token(self, token, expires_at):
        """撤销当前 JWT，重复提交相同凭据不产生重复记录。"""
        await self.db.execute(delete(RevokedAccessToken).where(RevokedAccessToken.expires_at <= utc_now()))
        await self.db.execute(insert(RevokedAccessToken).values(id=self.fingerprint(token), expires_at=expires_at).on_conflict_do_nothing())

    async def is_revoked(self, token):
        """每次鉴权回读持久撤销记录，重启不会复活旧凭据。"""
        return await self.db.get(RevokedAccessToken, self.fingerprint(token)) is not None

    @staticmethod
    def fingerprint(token):
        """已验证凭据的等价签名编码拥有同一撤销摘要。"""
        signing_input, signature = token.rsplit(".", 1)
        # PyJWT 接受签名段的尾部 padding；按签名字节归一，避免换一种编码绕过撤销。
        return hashlib.sha256(signing_input.encode("ascii") + b"\0" + base64url_decode(signature)).hexdigest()
