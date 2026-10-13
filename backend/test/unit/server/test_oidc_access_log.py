"""OIDC认证日志对直接和替代 URI 使用相同敏感边界。"""

from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from yuxi.api.middleware.access_log import AccessLogMiddleware


@pytest.mark.parametrize(
    "path",
    [
        "/api/auth/oidc/callback",
        "/api/auth/oidc/callback/",
        "/api/auth/oidc/%63allback",
        "//api/auth/oidc/callback",
        "/api//auth/oidc/callback",
        "/api/other/../auth/oidc/callback",
    ],
)
def test_authentication_query_is_not_logged_through_alternative_paths(path):
    """404、自动跳转及正常回调同样不保留认证 query。"""
    logger = Mock()
    app = FastAPI()
    app.add_middleware(AccessLogMiddleware, logger=logger)
    marker = "fixture-secret-callback-marker"
    with TestClient(app) as http:
        http.get(path + "?code=" + marker + "&state=" + marker, follow_redirects=False)
    log = " ".join(str(call.args) for call in logger.info.call_args_list)
    assert logger.info.call_count == 1
    assert marker not in log
    assert "GET" in log and "404" in log
