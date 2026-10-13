"""当前 Yuxi 凭据退出，不操作认证中心的共享会话。"""

from datetime import UTC, datetime

from yuxi.modules.identity.repositories.login_sessions import LoginSessionRepository
from yuxi.modules.identity.repositories.oidc import OIDCRepository


async def logout_current_session(db, token, claims):
    """提交当前凭据撤销后返回；SSO 及其他浏览器会话继续有效。"""
    if claims.get("oidc_sid"):
        await OIDCRepository(db).revoke_session(claims["oidc_sid"], int(claims["sub"]))
    else:
        await LoginSessionRepository(db).revoke_token(token, datetime.fromtimestamp(claims["exp"], UTC))
    await db.commit()
    return {"logout_url": None}
