"""有界 OAuth discovery、客户端注册与授权码协议。"""

import asyncio
import json
import re
from urllib.parse import urlsplit

import httpx

from yuxi.modules.extensions.mcp.oauth_config import MCPOAuthConfig, origin, validate_url
from yuxi.shared.errors import UpstreamError


class OAuthTokenRejected(Exception):
    """授权服务器明确拒绝刷新令牌。"""


async def request_json(method, url, *, origins, **kwargs):
    """限制来源、重定向、响应体与超时，错误不包含远端正文。"""
    validate_url(url, origins=origins)
    try:
        async with asyncio.timeout(20), httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            async with client.stream(method, url, **kwargs) as response:
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 1024 * 1024:
                        raise ValueError("oversized OAuth response")
                data = json.loads(body)
                if response.status_code in (400, 401) and isinstance(data, dict) and data.get("error") == "invalid_grant":
                    raise OAuthTokenRejected()
                response.raise_for_status()
                if not isinstance(data, dict):
                    raise ValueError("invalid OAuth response")
                return data
    except (httpx.HTTPError, ValueError, TimeoutError) as exc:
        raise UpstreamError("MCP 授权服务请求失败，请检查配置、网络或重试", code="mcp_oauth_upstream") from exc


async def discover(server):
    """资源挑战必须指向已配置 MCP 来源，授权服务器必须匹配超管信任根。"""
    config = MCPOAuthConfig.model_validate(server.oauth_config)
    validate_url(server.url)
    resource_origin = origin(server.url)
    try:
        async with asyncio.timeout(20), httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            async with client.stream("GET", server.url, headers={"Accept": "application/json, text/event-stream"}) as response:
                challenge = response.headers.get("www-authenticate", "")
        match = re.search(r'resource_metadata="([^"]+)"', challenge)
        resource_url = match[1] if match else resource_origin + "/.well-known/oauth-protected-resource" + urlsplit(server.url).path
        resource = await request_json("GET", resource_url, origins={resource_origin})
        if resource.get("resource") != server.url or config.issuer_url not in resource.get("authorization_servers", []):
            raise ValueError("resource metadata mismatch")
        issuer = urlsplit(config.issuer_url)
        path = "/.well-known/oauth-authorization-server" + issuer.path.rstrip("/")
        metadata = await request_json("GET", origin(config.issuer_url) + path, origins={origin(config.issuer_url)})
        if metadata.get("issuer") != config.issuer_url or "S256" not in metadata.get("code_challenge_methods_supported", []):
            raise ValueError("untrusted issuer or missing PKCE")
        for field in ("authorization_endpoint", "token_endpoint"):
            validate_url(metadata[field], origins={origin(config.issuer_url)})
        if config.registration == "dynamic":
            validate_url(metadata["registration_endpoint"], origins={origin(config.issuer_url)})
        return metadata
    except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError) as exc:
        raise UpstreamError("MCP 授权元数据无效或与超级管理员配置不匹配") from exc


async def token_request(metadata, config, client, data):
    """按发现文档支持的方式认证客户端，始终绑定目标 resource。"""
    supported = metadata.get("token_endpoint_auth_methods_supported", ["client_secret_basic"])
    secret = client.get("client_secret")
    kwargs = {}
    if secret and "client_secret_basic" in supported:
        kwargs["auth"] = httpx.BasicAuth(client["client_id"], secret)
    elif secret and "client_secret_post" in supported:
        data = {**data, "client_secret": secret}
    elif secret or "none" not in supported:
        raise UpstreamError("授权服务器不支持当前客户端认证方式")
    return await request_json(
        "POST",
        metadata["token_endpoint"],
        origins={origin(config.issuer_url)},
        data={**data, "client_id": client["client_id"]},
        headers={"Accept": "application/json"},
        **kwargs,
    )
