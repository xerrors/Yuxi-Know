"""OIDC 配置模块"""
import os
from pydantic import BaseModel, Field


class OIDCConfig(BaseModel):
    """OIDC 配置模型"""

    # 是否启用 OIDC 认证
    enabled: bool = Field(default=False, description="是否启用 OIDC 认证")

    # OIDC Provider 配置
    issuer_url: str = Field(default="", description="OIDC Provider 的 issuer URL")
    client_id: str = Field(default="", description="OIDC Client ID")
    client_secret: str = Field(default="", description="OIDC Client Secret")

    # 回调 URL（可选，默认自动构建）
    redirect_uri: str = Field(default="", description="OIDC 回调 URL")

    # 授权端点（可选，自动从 discovery 获取）
    authorization_endpoint: str = Field(default="", description="授权端点 URL")
    token_endpoint: str = Field(default="", description="Token 端点 URL")
    userinfo_endpoint: str = Field(default="", description="UserInfo 端点 URL")
    end_session_endpoint: str = Field(default="", description="登出端点 URL")

    # 认证源名称
    provider_name: str = Field(default="OIDC登录", description="认证源名称，显示在登录按钮上的文字")

    # 请求的 scope
    scopes: str = Field(default="openid profile email", description="请求的 scope")

    # 是否自动创建用户
    auto_create_user: bool = Field(default=True, description="是否自动创建用户")

    # 默认角色
    default_role: str = Field(default="user", description="OIDC 用户的默认角色")

    # 默认部门名称
    default_department: str = Field(default="OIDC用户", description="OIDC 用户的默认部门")

    # 用户名映射字段
    username_claim: str = Field(default="preferred_username", description="用户名映射字段")

    # 邮箱映射字段
    email_claim: str = Field(default="email", description="邮箱映射字段")

    # 姓名映射字段
    name_claim: str = Field(default="name", description="姓名映射字段")

    @classmethod
    def from_env(cls) -> "OIDCConfig":
        """从环境变量加载配置"""
        enabled = os.environ.get("OIDC_ENABLED", "false").lower() == "true"

        if not enabled:
            return cls(enabled=False)

        return cls(
            enabled=enabled,
            provider_name=os.environ.get("OIDC_PROVIDER_NAME", "OIDC登录"),
            issuer_url=os.environ.get("OIDC_ISSUER_URL", ""),
            client_id=os.environ.get("OIDC_CLIENT_ID", ""),
            client_secret=os.environ.get("OIDC_CLIENT_SECRET", ""),
            redirect_uri=os.environ.get("OIDC_REDIRECT_URI", ""),
            authorization_endpoint=os.environ.get("OIDC_AUTHORIZATION_ENDPOINT", ""),
            token_endpoint=os.environ.get("OIDC_TOKEN_ENDPOINT", ""),
            userinfo_endpoint=os.environ.get("OIDC_USERINFO_ENDPOINT", ""),
            end_session_endpoint=os.environ.get("OIDC_END_SESSION_ENDPOINT", ""),
            scopes=os.environ.get("OIDC_SCOPES", "openid profile email"),
            auto_create_user=os.environ.get("OIDC_AUTO_CREATE_USER", "true").lower() == "true",
            default_role=os.environ.get("OIDC_DEFAULT_ROLE", "user"),
            default_department=os.environ.get("OIDC_DEFAULT_DEPARTMENT", "OIDC用户"),
            username_claim=os.environ.get("OIDC_USERNAME_CLAIM", "preferred_username"),
            email_claim=os.environ.get("OIDC_EMAIL_CLAIM", "email"),
            name_claim=os.environ.get("OIDC_NAME_CLAIM", "name"),
        )

    def is_configured(self) -> bool:
        """检查配置是否完整"""
        if not self.enabled:
            return False
        return all([
            self.issuer_url,
            self.client_id,
            self.client_secret,
        ])


# 全局配置实例
oidc_config = OIDCConfig.from_env()
