"""OIDC 认证工具类"""
import secrets
import urllib.parse
from typing import Any, Optional

import httpx
from yuxi.utils import logger

from server.utils.oidc_config import oidc_config


class OIDCProviderMetadata:
    """OIDC Provider 元数据"""

    def __init__(self):
        self.authorization_endpoint: Optional[str] = None
        self.token_endpoint: Optional[str] = None
        self.userinfo_endpoint: Optional[str] = None
        self.end_session_endpoint: Optional[str] = None
        self._loaded = False

    async def load(self, issuer_url: str) -> bool:
        """从 discovery 端点加载元数据"""
        if self._loaded:
            return True

        try:
            # 构建 discovery URL
            discovery_url = f"{issuer_url.rstrip('/')}/.well-known/openid-configuration"

            async with httpx.AsyncClient() as client:
                response = await client.get(discovery_url, timeout=30.0)
                response.raise_for_status()
                metadata = response.json()

            self.authorization_endpoint = metadata.get("authorization_endpoint")
            self.token_endpoint = metadata.get("token_endpoint")
            self.userinfo_endpoint = metadata.get("userinfo_endpoint")
            self.end_session_endpoint = metadata.get("end_session_endpoint")

            self._loaded = True
            logger.info(f"OIDC discovery loaded from {discovery_url}")
            return True

        except Exception as e:
            logger.error(f"Failed to load OIDC discovery: {e}")
            return False


class OIDCUtils:
    """OIDC 工具类"""

    _metadata: Optional[OIDCProviderMetadata] = None
    _state_store: dict[str, dict[str, Any]] = {}  # 简单的 state 存储

    @classmethod
    async def get_metadata(cls) -> Optional[OIDCProviderMetadata]:
        """获取 OIDC Provider 元数据"""
        if not oidc_config.enabled or not oidc_config.is_configured():
            return None

        if cls._metadata is None:
            cls._metadata = OIDCProviderMetadata()

            # 优先使用配置中的端点
            if oidc_config.authorization_endpoint:
                cls._metadata.authorization_endpoint = oidc_config.authorization_endpoint
                cls._metadata.token_endpoint = oidc_config.token_endpoint
                cls._metadata.userinfo_endpoint = oidc_config.userinfo_endpoint
                cls._metadata.end_session_endpoint = oidc_config.end_session_endpoint
                cls._metadata._loaded = True
            else:
                # 从 discovery 加载
                success = await cls._metadata.load(oidc_config.issuer_url)
                if not success:
                    return None

        return cls._metadata

    @classmethod
    def generate_state(cls, redirect_path: str = "/") -> str:
        """生成 state 参数并存储"""
        state = secrets.token_urlsafe(32)
        cls._state_store[state] = {"redirect_path": redirect_path}
        return state

    @classmethod
    def verify_state(cls, state: str) -> Optional[dict[str, Any]]:
        """验证 state 参数"""
        return cls._state_store.pop(state, None)

    @classmethod
    def generate_nonce(cls) -> str:
        """生成 nonce 参数"""
        return secrets.token_urlsafe(32)

    @classmethod
    async def build_authorization_url(cls, redirect_path: str = "/") -> Optional[str]:
        """构建授权 URL"""
        metadata = await cls.get_metadata()
        if not metadata or not metadata.authorization_endpoint:
            return None

        state = cls.generate_state(redirect_path)
        nonce = cls.generate_nonce()

        # 构建 redirect_uri
        redirect_uri = oidc_config.redirect_uri
        if not redirect_uri:
            # 自动构建回调 URL
            redirect_uri = "/api/auth/oidc/callback"

        params = {
            "client_id": oidc_config.client_id,
            "response_type": "code",
            "scope": oidc_config.scopes,
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": nonce,
        }

        query_string = urllib.parse.urlencode(params)
        return f"{metadata.authorization_endpoint}?{query_string}"

    @classmethod
    async def exchange_code_for_token(cls, code: str) -> Optional[dict[str, Any]]:
        """用授权码交换令牌"""
        metadata = await cls.get_metadata()
        if not metadata or not metadata.token_endpoint:
            return None

        redirect_uri = oidc_config.redirect_uri or "/api/auth/oidc/callback"

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": oidc_config.client_id,
            "client_secret": oidc_config.client_secret,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    metadata.token_endpoint,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()

        except Exception as e:
            logger.error(f"Failed to exchange code for token: {e}")
            return None

    @classmethod
    async def get_userinfo(cls, access_token: str) -> Optional[dict[str, Any]]:
        """获取用户信息"""
        metadata = await cls.get_metadata()
        if not metadata or not metadata.userinfo_endpoint:
            return None

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    metadata.userinfo_endpoint,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()

        except Exception as e:
            logger.error(f"Failed to get userinfo: {e}")
            return None

    @classmethod
    async def build_logout_url(cls, id_token: Optional[str] = None) -> Optional[str]:
        """构建登出 URL"""
        metadata = await cls.get_metadata()
        if not metadata or not metadata.end_session_endpoint:
            return None

        params = {"client_id": oidc_config.client_id}

        if id_token:
            params["id_token_hint"] = id_token

        if oidc_config.redirect_uri:
            params["post_logout_redirect_uri"] = oidc_config.redirect_uri

        query_string = urllib.parse.urlencode(params)
        return f"{metadata.end_session_endpoint}?{query_string}"

    @classmethod
    def extract_user_info(cls, userinfo: dict[str, Any]) -> dict[str, Any]:
        """从 userinfo 中提取用户信息"""
        # 获取 sub (subject) - OIDC 用户的唯一标识
        sub = userinfo.get("sub", "")

        # 获取用户名
        username = userinfo.get(oidc_config.username_claim, "")
        if not username:
            username = userinfo.get("preferred_username", "")
        if not username:
            username = userinfo.get("email", "").split("@")[0]
        if not username:
            username = sub[:20]  # 使用 sub 的前20位

        # 获取邮箱
        email = userinfo.get(oidc_config.email_claim, "")
        if not email:
            email = userinfo.get("email", "")

        # 获取显示名称
        name = userinfo.get(oidc_config.name_claim, "")
        if not name:
            name = userinfo.get("name", "")
        if not name:
            name = username

        return {
            "sub": sub,
            "username": username,
            "email": email,
            "name": name,
            "raw": userinfo,
        }
