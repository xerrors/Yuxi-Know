"""短期委托与登录身份用途隔离。"""

from datetime import timedelta

import jwt
import pytest

from yuxi.modules.identity.security import AuthUtils
from yuxi.modules.knowledge.mcp import auth as security
from yuxi.shared.datetime import utc_now


@pytest.fixture(autouse=True)
def signing_config(monkeypatch):
    """每个进程使用显式相同部署配置。"""
    monkeypatch.setenv("JWT_SECRET_KEY", "knowledge-test-" + "k" * 40)
    monkeypatch.setenv("YUXI_INSTANCE_ID", "knowledge-test")


@pytest.mark.parametrize("selection", ["all", [], ["kb-a"]])
def test_delegation_preserves_exact_scope_and_cannot_authenticate_as_login(selection):
    """同一签名密钥不能跨 audience 重放。"""
    token = security.create_knowledge_token(uid="user", selection=selection)
    payload = security.verify_knowledge_token(token)
    assert payload["sub"] == "user" and payload["selection"] == selection
    assert set(payload) == {"sub", "iss", "aud", "purpose", "selection", "iat", "exp"}
    assert payload["exp"] - payload["iat"] == 300
    assert AuthUtils.decode_token(token) is None
    with pytest.raises(ValueError):
        security.verify_knowledge_token(AuthUtils.create_access_token({"sub": "1"}))


@pytest.mark.parametrize(
    "changes",
    [
        {"aud": "other"},
        {"iss": "other"},
        {"purpose": "login"},
        {"selection": None},
        {"selection": [""]},
        {"exp": utc_now() - timedelta(seconds=1)},
        {"iat": utc_now() + timedelta(seconds=60)},
        {"exp": utc_now() + timedelta(days=1)},
        {"sub": ""},
    ],
)
def test_invalid_delegation_claims_are_rejected(changes, monkeypatch):
    """重新签名非法主张也不能绕过委托契约。"""
    token = security.create_knowledge_token(uid="user", selection=[])
    claims = jwt.decode(token, options={"verify_signature": False})
    claims.update(changes)
    token = jwt.encode(claims, "knowledge-test-" + "k" * 40, algorithm="HS256")
    with pytest.raises(ValueError):
        security.verify_knowledge_token(token)


def test_missing_shared_configuration_never_generates_process_random_key(monkeypatch):
    """跨进程委托配置缺失必须失败。"""
    monkeypatch.delenv("JWT_SECRET_KEY")
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        security.create_knowledge_token(uid="user", selection="all")
    monkeypatch.setenv("JWT_SECRET_KEY", "knowledge-test-" + "k" * 40)
    monkeypatch.delenv("YUXI_INSTANCE_ID")
    with pytest.raises(ValueError, match="YUXI_INSTANCE_ID"):
        security.create_knowledge_token(uid="user", selection="all")
