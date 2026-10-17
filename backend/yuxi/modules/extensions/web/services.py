"""读取全局配置并执行供应商网页搜索与抓取。"""

from datetime import date, timedelta
from time import perf_counter
from typing import Literal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.infrastructure.observability.logging import logger
from yuxi.modules.extensions.options import WEB_PROVIDER_OPTIONS
from yuxi.modules.extensions.web.schemas import FetchInput, SearchInput, SearchResult
from yuxi.modules.system.options import system_options
from yuxi.shared.errors import InvalidInputError, OperationTimeoutError, UpstreamError

_ENDPOINTS = {
    ("tavily", "search"): "https://api.tavily.com/search",
    ("tavily", "fetch"): "https://api.tavily.com/extract",
    ("deepseek", "search"): "https://api.deepseek.com/v1/tools/search",
    ("deepseek", "fetch"): "https://api.deepseek.com/v1/tools/fetch",
    ("doubao", "search"): "https://open.feedcoopapi.com/search_api/web_search",
}


async def get_web_configuration(db: AsyncSession | None = None) -> dict:
    """解析当前配置；显式选择即使无凭据也不切换供应商。"""
    config = await system_options.get(db)
    keys = {provider: (await option.get(db)).get("api_key") or "" for provider, option in WEB_PROVIDER_OPTIONS.items()}
    search = (config.get("web_search_provider") or "").strip().lower() or next((provider for provider in keys if keys[provider]), None)
    fetch = (config.get("web_fetch_provider") or "").strip().lower() or next(
        (provider for provider in ("tavily", "deepseek") if keys[provider]), None
    )
    return {"search": search, "fetch": fetch, "keys": keys}


async def available_web_tools() -> set[str]:
    """按最新凭据决定本轮可装配的网页工具。"""
    config = await get_web_configuration()
    available = {
        f"web_{operation}"
        for operation in ("search", "fetch")
        if (config[operation], operation) in _ENDPOINTS and config["keys"].get(config[operation])
    }
    for operation in ("search", "fetch"):
        name = f"web_{operation}"
        if name not in available:
            reason = (
                "credentials_missing" if not config[operation] or (config[operation], operation) in _ENDPOINTS else "provider_unavailable"
            )
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
    payload = _search_payload(provider, request)
    started = perf_counter()
    data = await _post(provider, "search", key, payload)
    try:
        if provider == "doubao":
            if data.get("ResponseMetadata", {}).get("Error"):
                raise UpstreamError("豆包搜索失败，请检查服务权限与额度", code="web_provider_rejected")
            items = data["Result"]["WebResults"]
        else:
            items = data["results"]
        if not isinstance(items, list):
            raise ValueError("invalid result list")
        results = [_search_result(provider, item, request.include_raw_content) for item in items]
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
    payload = {"url": request.url}
    if provider == "tavily":
        payload = {"urls": [request.url], "format": "markdown", "extract_depth": "basic"}
    started = perf_counter()
    data = await _post(provider, "fetch", key, payload)
    try:
        item = data["results"][0] if provider == "tavily" else data
        content = item.get("raw_content") if provider == "tavily" else item.get("content")
        title = item.get("title") or ""
        if not isinstance(content, str) or not content.strip() or not isinstance(title, str):
            raise ValueError("missing page content")
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
    if provider is not None and (provider, operation) not in _ENDPOINTS:
        raise InvalidInputError("该供应商不支持此网页工具")
    if provider is not None and api_key is not None:
        key = api_key.strip()
    else:
        config = await get_web_configuration(db)
        provider = provider or config[operation]
        key = config["keys"].get(provider, "")
    if (provider, operation) not in _ENDPOINTS or not key:
        raise InvalidInputError("网页工具未配置，请在设置 → 网络搜索中配置供应商和 API Key", code="web_credentials_missing")
    return provider, key


async def _post(provider: str, operation: str, key: str, payload: dict) -> dict:
    """只请求固定官方端点，错误不包含凭据或供应商响应正文。"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(_ENDPOINTS[provider, operation], headers={"Authorization": f"Bearer {key}"}, json=payload)
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


def _search_payload(provider: str, request: SearchInput) -> dict:
    """映射供应商参数并显式拒绝超限输入。"""
    days = {"OneDay": 1, "OneWeek": 7, "OneMonth": 30, "OneYear": 365}
    if len(request.query) > {"tavily": 400, "deepseek": 128, "doubao": 100}[provider]:
        raise InvalidInputError("搜索词超过当前供应商的长度限制")
    if provider == "tavily":
        if request.count > 20:
            raise InvalidInputError("Tavily 最多返回 20 条结果")
        payload = {
            "query": request.query,
            "max_results": request.count,
            "search_depth": "basic",
            "auto_parameters": False,
            "include_answer": False,
            "include_raw_content": request.content_format if request.include_raw_content else False,
            "include_domains": request.sites or [],
            "exclude_domains": request.block_hosts or [],
        }
        if request.time_range in days:
            payload["time_range"] = {"OneDay": "day", "OneWeek": "week", "OneMonth": "month", "OneYear": "year"}[request.time_range]
        elif request.time_range:
            payload["start_date"], payload["end_date"] = request.time_range.split("..")
        return payload
    if provider == "deepseek":
        query = request.query
        if request.sites:
            query += " " + " OR ".join(f"site:{site}" for site in request.sites)
        for site in request.block_hosts or []:
            query += f" -site:{site}"
        if request.time_range in days:
            query += f" after:{date.today() - timedelta(days=days[request.time_range])}"
        elif request.time_range:
            start, end = request.time_range.split("..")
            query += f" after:{start} before:{end}"
        if len(query) > 128:
            raise InvalidInputError("包含站点与时间过滤后的 DeepSeek 搜索词不能超过 128 字符")
        if request.include_raw_content and request.content_format != "markdown":
            raise InvalidInputError("DeepSeek 正文仅支持 markdown，请设置 content_format=markdown")
        return {"query": query, "count": request.count, "need_content": request.include_raw_content}
    filters = {"NeedUrl": True}
    if request.sites:
        filters["Sites"] = "|".join(request.sites)
    if request.block_hosts:
        filters["BlockHosts"] = "|".join(request.block_hosts)
    payload = {
        "Query": request.query,
        "SearchType": "web",
        "Count": request.count,
        "Filter": filters,
        "ContentFormats": request.content_format,
    }
    if request.time_range:
        payload["TimeRange"] = request.time_range
    return payload


def _search_result(provider: str, item: dict, include_raw_content: bool) -> dict:
    """保留供应商各字段的实际语义，不混淆相关摘要与正文。"""
    if not isinstance(item, dict):
        raise ValueError("invalid result item")
    if provider == "doubao":
        values = {
            "title": item["Title"],
            "url": item["Url"],
            "snippet": item.get("Snippet") or "",
            "relevant_content": item.get("Summary") or "",
            "raw_content": item.get("Content") or "",
            "score": item.get("RankScore"),
            "score_max": 1,
            "site_name": item.get("SiteName"),
            "publish_time": item.get("PublishTime"),
        }
    else:
        values = {
            "title": item["title"],
            "url": item["url"],
            "snippet": item.get("snippet") or "",
            "relevant_content": item.get("content" if provider == "tavily" else "summary") or "",
            "raw_content": item.get("raw_content" if provider == "tavily" else "content") or "",
            "score": item.get("score" if provider == "tavily" else "rerank_score"),
            "score_max": 1 if provider == "tavily" else 3,
            "site_name": item.get("site_name"),
            "publish_time": item.get("published_date" if provider == "tavily" else "date"),
        }
    if not include_raw_content:
        values["raw_content"] = ""
    return SearchResult.model_validate(values).model_dump()
