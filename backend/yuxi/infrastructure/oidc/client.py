"""有界 OIDC 协议调用、discovery 信任根及非对称签名验证。"""

import asyncio
import base64
import hashlib
import hmac
import time

import httpx
import jwt

from yuxi.modules.identity.oidc import MAX_TOKEN_AGE
from yuxi.shared.errors import PermissionDeniedError, UpstreamError

ALGORITHMS = ("RS256", "RS384", "RS512", "ES256", "ES384", "ES512")
LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"


class OIDCClient:
    """按部署配置缓存公开元数据，未知 kid 的刷新有频率上限。"""

    def __init__(self):
        self.cache = {}
        self.lock = asyncio.Lock()

    async def metadata(self, config):
        """精确核对发现文档的 issuer，再采用管理员覆盖或发现端点。"""
        config.validate_configuration()
        key = (config.issuer_url, config.client_id)
        now = time.monotonic()
        async with self.lock:
            cached = self.cache.get(key)
            if cached and cached["until"] > now:
                return cached
            data = await self.request("GET", config.issuer_url.rstrip("/") + "/.well-known/openid-configuration")
            if data.get("issuer") != config.issuer_url:
                raise UpstreamError("OIDC discovery issuer 不匹配")
            endpoints = {}
            try:
                for name in ("authorization_endpoint", "token_endpoint", "userinfo_endpoint", "jwks_uri"):
                    value = getattr(config, name, "") or data.get(name)
                    if not isinstance(value, str):
                        raise ValueError("missing endpoint")
                    config.validate_url(value)
                    endpoints[name] = value
            except (TypeError, ValueError) as exc:
                raise UpstreamError("OIDC discovery 端点无效") from exc
            supported = data.get("id_token_signing_alg_values_supported", [])
            if not isinstance(supported, list):
                raise UpstreamError("OIDC discovery 算法列表无效")
            endpoints.update(algorithms=[a for a in ALGORITHMS if a in supported], until=now + 300, keys=[], keys_checked=0)
            if not endpoints["algorithms"]:
                raise UpstreamError("OIDC 不支持允许的非对称签名算法")
            self.cache[key] = endpoints
            return endpoints

    async def authenticate(self, config, code, state):
        """兑换 PKCE 授权码，验证 ID token 后才读取匹配的 UserInfo。"""
        metadata = await self.metadata(config)
        token = await self.request(
            "POST",
            metadata["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": state["verifier"],
                "redirect_uri": config.redirect_uri,
                "client_id": config.client_id,
                "client_secret": config.client_secret,
            },
        )
        access_token = token.get("access_token")
        if (
            not isinstance(access_token, str)
            or not access_token
            or not access_token.isascii()
            or any(c.isspace() or ord(c) < 32 for c in access_token)
            or str(token.get("token_type", "")).lower() != "bearer"
        ):
            raise UpstreamError("OIDC token 响应无效")
        claims = await self.verify(config, token.get("id_token"))
        if not isinstance(claims.get("nonce"), str) or not hmac.compare_digest(claims["nonce"], state["nonce"]):
            raise PermissionDeniedError("OIDC nonce 不匹配")
        if "at_hash" in claims:
            algorithm = jwt.get_unverified_header(token["id_token"])["alg"]
            digest = hashlib.new("sha" + algorithm[-3:], access_token.encode("ascii")).digest()
            expected = base64.urlsafe_b64encode(digest[: len(digest) // 2]).rstrip(b"=").decode()
            if not isinstance(claims["at_hash"], str) or not hmac.compare_digest(claims["at_hash"], expected):
                raise PermissionDeniedError("OIDC access token 不匹配")
        userinfo = await self.request("GET", metadata["userinfo_endpoint"], headers={"Authorization": "Bearer " + access_token})
        if userinfo.get("sub") != claims["sub"]:
            raise PermissionDeniedError("OIDC UserInfo 身份不匹配")
        return claims, userinfo

    async def verify(self, config, token, *, logout=False):
        """只使用可信 JWKS 验证 token；拒绝对称算法及来自 token 的取钥 URL。"""
        if not isinstance(token, str) or not token or len(token) > 16384:
            raise PermissionDeniedError("OIDC token 无效")
        metadata = await self.metadata(config)
        try:
            header = jwt.get_unverified_header(token)
            alg, kid = header.get("alg"), header.get("kid")
            if alg not in metadata["algorithms"] or not isinstance(kid, str) or not kid or header.get("crit"):
                raise ValueError("unsupported header")
            async with self.lock:
                matches = [key for key in metadata["keys"] if key.get("kid") == kid]
                now = time.monotonic()
                if not matches and now - metadata["keys_checked"] >= 30:
                    metadata["keys_checked"] = now
                    jwks = await self.request("GET", metadata["jwks_uri"])
                    if not isinstance(jwks.get("keys"), list):
                        raise ValueError("invalid JWKS")
                    metadata["keys"] = [key for key in jwks["keys"] if isinstance(key, dict)]
                    matches = [key for key in metadata["keys"] if key.get("kid") == kid]
            if len(matches) != 1:
                raise ValueError("unknown signing key")
            key = matches[0]
            if key.get("use", "sig") != "sig" or key.get("alg", alg) != alg or "verify" not in key.get("key_ops", ["verify"]):
                raise ValueError("invalid signing key usage")
            claims = jwt.decode(
                token,
                jwt.PyJWK.from_dict(key, algorithm=alg).key,
                algorithms=[alg],
                issuer=config.issuer_url,
                audience=config.client_id,
                leeway=30,
                options={"require": ["iss", "aud", "exp", "iat"] + ([] if logout else ["sub", "nonce"])},
            )
            for name in ("exp", "iat"):
                if type(claims[name]) is not int or not 0 <= claims[name] <= 253402300799:
                    raise ValueError("invalid timestamp")
            if claims["exp"] <= claims["iat"] or time.time() - claims["iat"] > MAX_TOKEN_AGE:
                raise ValueError("stale token")
            audiences = claims["aud"] if isinstance(claims["aud"], list) else [claims["aud"]]
            if audiences != [config.client_id] or ("azp" in claims and claims["azp"] != config.client_id):
                raise ValueError("untrusted audience")
            for name in ("sub", "sid"):
                if name in claims and (not isinstance(claims[name], str) or not 0 < len(claims[name]) <= 255):
                    raise ValueError("invalid identity")
            if logout:
                if (
                    not (claims.get("sub") or claims.get("sid"))
                    or "nonce" in claims
                    or not isinstance(claims.get("jti"), str)
                    or not 0 < len(claims["jti"]) <= 255
                    or claims.get("events") != {LOGOUT_EVENT: {}}
                ):
                    raise ValueError("invalid logout claims")
            elif "events" in claims:
                raise ValueError("logout token used for login")
            return claims
        except (jwt.PyJWTError, TypeError, ValueError, KeyError) as exc:
            raise PermissionDeniedError("OIDC token 校验失败") from exc

    @staticmethod
    async def request(method, url, **kwargs):
        """限制响应体和整体等待，不把远端正文或凭据写入异常信息。"""
        try:
            async with asyncio.timeout(20), httpx.AsyncClient(follow_redirects=False, timeout=10) as client:
                async with client.stream(method, url, **kwargs) as response:
                    response.raise_for_status()
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 1024 * 1024:
                            raise ValueError("response too large")
                    import json

                    result = json.loads(data)
                    if not isinstance(result, dict):
                        raise ValueError("response is not an object")
                    return result
        except (httpx.HTTPError, TimeoutError, ValueError) as exc:
            raise UpstreamError("OIDC 认证中心请求失败，请重试或联系管理员") from exc


client = OIDCClient()
