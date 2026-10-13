"""OIDC 的单提供商配置与公开协议常量。"""

import os
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

FRONTEND_CALLBACK_PATH = "/auth/oidc/callback"
FRONTEND_LOGIN_PATH = "/login"
COOKIE_NAME = "yuxi_oidc_browser"
STATE_TTL = 300
RESULT_TTL = 60
SESSION_TTL = 3600
MAX_TOKEN_AGE = 600


class OIDCConfig(BaseModel):
    """启用时拒绝不完整或不安全的部署配置。"""

    enabled: bool = False
    issuer_url: str = ""
    client_id: str = ""
    client_secret: str = Field(default="", repr=False)
    redirect_uri: str = ""
    authorization_endpoint: str = ""
    token_endpoint: str = ""
    userinfo_endpoint: str = ""
    provider_name: str = "OIDC登录"
    scopes: str = "openid profile email"
    auto_create_user: bool = True
    default_department: str = "OIDC用户"
    name_claim: str = "name"
    username_claim: str = "preferred_username"
    fetch_department_info: bool = False
    department_claim: str = "department"
    force_prompt_login: bool = False

    @classmethod
    def from_env(cls):
        """读取现有部署变量，原始用户名自动合并不再作为登录证明。"""
        if os.getenv("OIDC_ENABLED", "false").lower() != "true":
            return cls()
        values = {name: os.getenv("OIDC_" + name.upper(), str(field.default)).strip() for name, field in cls.model_fields.items()}
        config = cls(**values)
        if os.getenv("OIDC_USE_RAW_USERNAME", "false").lower() == "true":
            raise ValueError("OIDC_USE_RAW_USERNAME 已退役；请迁移历史绑定并关闭此配置")
        if os.getenv("OIDC_DEFAULT_ROLE", "user") != "user":
            raise ValueError("OIDC 自动开户只允许普通用户角色")
        config.validate_configuration()
        return config

    def validate_configuration(self):
        """配置拥有信任根，端点与回调必须明确且生产只允许 HTTPS。"""
        if not all((self.issuer_url, self.client_id, self.client_secret, self.redirect_uri)):
            raise ValueError("OIDC 需要完整的 issuer、client、secret 和回调地址")
        for field in (
            "issuer_url",
            "redirect_uri",
            "authorization_endpoint",
            "token_endpoint",
            "userinfo_endpoint",
        ):
            value = getattr(self, field)
            if value:
                self.validate_url(value)
        issuer, callback = urlsplit(self.issuer_url), urlsplit(self.redirect_uri)
        if issuer.query or callback.query or callback.path != "/api/auth/oidc/callback":
            raise ValueError("OIDC issuer 不含查询，回调路径必须为 /api/auth/oidc/callback")
        if len(self.issuer_url) > 512 or not 0 < len(self.default_department) <= 50:
            raise ValueError("OIDC issuer 或默认部门长度无效")
        if "openid" not in self.scopes.split():
            raise ValueError("OIDC scopes 必须包含 openid")

    @staticmethod
    def validate_url(value):
        """校验配置与 discovery 的远端 URL，拒绝凭据、fragment 和生产明文。"""
        parsed = urlsplit(value)
        production = os.getenv("YUXI_ENV", "").lower() in {"prod", "production"}
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
            or any(c.isspace() for c in value)
            or (production and parsed.scheme != "https")
        ):
            raise ValueError("OIDC URL 无效或生产环境未使用 HTTPS")
        if parsed.port is not None and not 0 < parsed.port <= 65535:
            raise ValueError("OIDC URL 端口无效")

    @property
    def secure_cookie(self):
        """回调使用 HTTPS 时仅发送安全 cookie。"""
        return self.redirect_uri.startswith("https://")


def get_oidc_config() -> OIDCConfig:
    """在实际配置消费入口读取环境，导入模型不触发部署校验。"""
    return OIDCConfig.from_env()
