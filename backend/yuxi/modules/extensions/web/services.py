"""读取全局配置并执行供应商网页搜索与抓取。"""

from time import perf_counter
from typing import Literal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.infrastructure.observability.logging import logger
from yuxi.modules.extensions.options import WEB_PROVIDER_OPTIONS
from yuxi.modules.extensions.web import providers
from yuxi.modules.extensions.web.schemas import FetchInput, SearchInput
from yuxi.modules.system.options import system_options
from yuxi.shared.errors import InvalidInputError, OperationTimeoutError, UpstreamError
from yuxi.shared.web_providers import FETCH_PROVIDER_IDS, PROVIDERS_BY_ID


def _supports(provider_id: str | None, operation: Literal["search", "fetch"]) -> bool:
    """目录声明了该操作才允许调用；未知供应商一律拒绝。"""
    provider = PROVIDERS_BY_ID.get(provider_id or "")
    return provider is not None and (operation == "search" or provider.supports_fetch)


async def get_web_configuration(db: AsyncSession | None = None) -> dict:
    """解析当前配置；显式选择即使无凭据也不切换供应商。"""
    config = await system_options.get(db)
    keys = {provider_id: (await option.get(db)).get("api_key") or "" for provider_id, option in WEB_PROVIDER_OPTIONS.items()}
    search = (config.get("web_search_provider") or "").strip().lower() or next((provider for provider in keys if keys[provider]), None)
    fetch = (config.get("web_fetch_provider") or "").strip().lower() or next(
        (provider for provider in FETCH_PROVIDER_IDS if keys[provider]), None
    )
    return {"search": search, "fetch": fetch, "keys": keys}


async def available_web_tools() -> set[str]:
    """按最新凭据决定本轮可装配的网页工具。"""
    config = await get_web_configuration()
    available = {
        f"web_{operation}"
        for operation in ("search", "fetch")
        if _supports(config[operation], operation) and config["keys"].get(config[operation])
    }
    for operation in ("search", "fetch"):
        name = f"web_{operation}"
        if name not in available:
            reason = "provider_unavailable" if config[operation] and not _supports(config[operation], operation) else "credentials_missing"
            logger.bind(component=name, reason=reason, available=False).warning(
                "component={} reason={} available=false 网页工具未配置，本轮不绑定该能力", name, reason
            )
    return available


async def search_web(
    request: SearchInput,
    *,
    provider: str | None = None,
    api_key: str | None = None,
    db: AsyncSession | None = None,
) -> dict:
    """使用默认或管理员测试指定的供应商执行搜索。"""
    provider, key = await _resolve_credentials("search", provider, api_key, db)
    payload = providers.search_payload(provider, request)
    started = perf_counter()
    data = await _post(provider, "search", key, payload)
    try:
        items = providers.search_items(provider, data)
        if not isinstance(items, list):
            raise ValueError("invalid result list")
        results = [providers.search_result(provider, item, request.include_raw_content) for item in items]
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise UpstreamError("搜索供应商返回了无效结果", code="web_provider_invalid_response") from exc
    return {"query": request.query, "provider": provider, "results": results, "response_time": perf_counter() - started}


async def fetch_web(
    request: FetchInput,
    *,
    provider: str | None = None,
    api_key: str | None = None,
    db: AsyncSession | None = None,
) -> dict:
    """通过官方正文接口读取单个网页，不在 Yuxi 主机下载目标 URL。"""
    provider, key = await _resolve_credentials("fetch", provider, api_key, db)
    payload = providers.fetch_payload(provider, request)
    started = perf_counter()
    data = await _post(provider, "fetch", key, payload)
    try:
        title, content = providers.fetch_result(provider, data)
    except (KeyError, IndexError, TypeError, AttributeError, ValueError) as exc:
        raise UpstreamError("未能获取可用的网页正文", code="web_content_unavailable") from exc
    return {
        "url": request.url,
        "title": title,
        "content": content,
        "format": "markdown",
        "provider": provider,
        "response_time": perf_counter() - started,
    }


async def _resolve_credentials(
    operation: Literal["search", "fetch"], provider: str | None, api_key: str | None, db: AsyncSession | None
) -> tuple[str, str]:
    """测试草稿仅覆盖本次请求，不写配置、不跨供应商回退。"""
    if provider is not None and not _supports(provider, operation):
        raise InvalidInputError("该供应商不支持此网页工具")
    if provider is not None and api_key is not None:
        key = api_key.strip()
    else:
        config = await get_web_configuration(db)
        provider = provider or config[operation]
        key = config["keys"].get(provider, "")
    if not _supports(provider, operation) or not key:
        raise InvalidInputError("网页工具未配置，请在设置 → 网络搜索中配置供应商和 API Key", code="web_credentials_missing")
    return provider, key


async def _post(provider: str, operation: str, key: str, payload: dict) -> dict:
    """只请求固定官方端点，错误不包含凭据或供应商响应正文。"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                providers.endpoint(provider, operation),
                headers={"Authorization": f"Bearer {key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("invalid response")
            return data
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        messages = {
            401: "API Key 无效或已失效",
            402: "供应商余额不足",
            403: "供应商拒绝访问，请检查服务权限或网页访问策略",
            404: "未能获取可用的网页内容",
            429: "供应商限流或额度不足，请稍后重试",
            432: "供应商额度已用尽",
            433: "供应商额度已用尽",
        }
        logger.bind(component="web_tools", provider=provider, operation=operation, status=status).warning("网页供应商请求失败")
        raise UpstreamError(messages.get(status, "网页供应商请求失败"), code="web_provider_rejected") from exc
    except httpx.TimeoutException as exc:
        raise OperationTimeoutError("网页供应商请求超时，请稍后重试", code="web_provider_timeout") from exc
    except (httpx.RequestError, ValueError) as exc:
        raise UpstreamError("网页供应商连接失败或响应无效", code="web_provider_unavailable") from exc
