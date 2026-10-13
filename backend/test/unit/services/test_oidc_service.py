"""OIDC 配置的生产边界；签名与状态在真实协议 integration 中验证。"""

import pytest

from yuxi.modules.identity.oidc import OIDCConfig


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:pass@example.com",
        "https://example.com/#token",
        "javascript:alert(1)",
        "https://example.com/\nheader",
    ],
)
def test_production_urls_reject_plaintext_credentials_and_ambiguous_urls(monkeypatch, url):
    """生产信任根和发现端点不得携带明文、凭据或歧义控制字符。"""
    monkeypatch.setenv("YUXI_ENV", "production")
    with pytest.raises(ValueError):
        OIDCConfig.validate_url(url)


def test_development_http_is_explicit_and_disabled_config_needs_no_secrets(monkeypatch):
    """开发联调允许 HTTP，关闭 OIDC 的部署不需要配置。"""
    monkeypatch.setenv("YUXI_ENV", "development")
    OIDCConfig.validate_url("http://localhost:39090/realms/test")
    monkeypatch.setenv("OIDC_ENABLED", "false")
    assert not OIDCConfig.from_env().enabled


@pytest.mark.parametrize(
    "overrides",
    [
        {"issuer_url": ""},
        {"redirect_uri": "https://yuxi.example/auth/callback"},
        {"scopes": "profile"},
        {"issuer_url": "https://idp.example?tenant=other"},
    ],
)
def test_incomplete_login_configuration_fails(overrides):
    """启用后必须具备完整信任根、准确回调与 openid scope。"""
    config = OIDCConfig(
        **(
            {
                "enabled": True,
                "issuer_url": "https://idp.example",
                "client_id": "fixture",
                "client_secret": "secret",
                "redirect_uri": "https://yuxi.example/api/auth/oidc/callback",
            }
            | overrides
        )
    )
    with pytest.raises(ValueError):
        config.validate_configuration()


def test_automatic_username_binding_is_not_a_configuration_bypass(monkeypatch):
    """旧同名关联开关明确拒绝，不能静默保留不安全分支。"""
    monkeypatch.setenv("OIDC_ENABLED", "true")
    monkeypatch.setenv("OIDC_USE_RAW_USERNAME", "true")
    with pytest.raises(ValueError, match="已退役"):
        OIDCConfig.from_env()
