"""OIDC HTTP 与浏览器 cookie 适配，不拥有登录业务。"""

import re
import secrets
from urllib.parse import urlencode

from fastapi import HTTPException
from fastapi.responses import RedirectResponse

from yuxi.modules.identity import oidc
from yuxi.modules.identity.services.oidc import OIDCService
from yuxi.modules.identity.services.logout import logout_current_session
from yuxi.shared.errors import DomainError

NO_STORE = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


async def get_oidc_config_handler():
    """公共配置只暴露入口开关和显示名。"""
    return {"enabled": oidc.oidc_config.enabled, "provider_name": oidc.oidc_config.provider_name}


async def oidc_login_url_handler(request, response):
    """浏览器发起流程，cookie 不能由前端脚本读取。"""
    browser = request.cookies.get(oidc.COOKIE_NAME, "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", browser):
        browser = secrets.token_urlsafe(32)
    url = await OIDCService().start(browser)
    response.headers.update(NO_STORE)
    response.set_cookie(
        oidc.COOKIE_NAME, browser, max_age=600, httponly=True, secure=oidc.oidc_config.secure_cookie, samesite="lax", path="/api/auth/oidc"
    )
    return {"login_url": url}


async def oidc_callback_handler(code, state, request, db, error=""):
    """回调只跳转固定站内路径，远端错误正文不回显。"""
    try:
        result = await OIDCService(db).callback(code, state, request.cookies.get(oidc.COOKIE_NAME, ""), denied=bool(error))
        target = oidc.FRONTEND_CALLBACK_PATH + "?" + urlencode({"code": result})
    except DomainError as exc:
        await db.rollback()
        target = oidc.FRONTEND_LOGIN_PATH + "?" + urlencode({"oidc_error": exc.message})
    return RedirectResponse(target, status_code=302, headers=NO_STORE)


async def oidc_exchange_code_handler(code, request, response, db):
    """同浏览器兑换结果；由会话行负责撤销和重试的可见结局。"""
    response.headers.update(NO_STORE)
    return await OIDCService(db).exchange(code, request.cookies.get(oidc.COOKIE_NAME, ""))


async def oidc_logout_handler(request, db):
    """本地 JWT 身份由认证依赖验证，API Key 不执行浏览器退出。"""
    payload = getattr(request.state, "jwt_payload", {})
    if getattr(request.state, "api_key", None):
        raise HTTPException(403, "API Key 不支持此操作")
    return await logout_current_session(db, request.state.jwt_token, payload)
