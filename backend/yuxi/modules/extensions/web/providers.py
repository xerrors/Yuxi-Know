"""按供应商目录映射网页搜索与抓取请求、响应和端点。"""

from datetime import date, timedelta

from yuxi.modules.extensions.web.schemas import FetchInput, SearchInput, SearchResult
from yuxi.shared.errors import InvalidInputError, UpstreamError
from yuxi.shared.web_providers import PROVIDERS_BY_ID

_MAX_QUERY_LENGTH = {"tavily": 400, "deepseek": 128, "doubao": 100}
_MAX_RESULTS = {"tavily": 20}
_SCORE_MAX = {"tavily": 1, "deepseek": 3, "doubao": 1}


def endpoint(provider_id: str, operation: str) -> str:
    """返回目录中声明的官方端点；不支持的操作在调用前已被拒绝。"""
    provider = PROVIDERS_BY_ID[provider_id]
    target = provider.search_endpoint if operation == "search" else provider.fetch_endpoint
    if target is None:
        raise InvalidInputError("该供应商不支持此网页工具")
    return target


def search_payload(provider_id: str, request: SearchInput) -> dict:
    """映射供应商参数并显式拒绝超限输入。"""
    days = {"OneDay": 1, "OneWeek": 7, "OneMonth": 30, "OneYear": 365}
    if len(request.query) > _MAX_QUERY_LENGTH[provider_id]:
        raise InvalidInputError("搜索词超过当前供应商的长度限制")
    if provider_id == "tavily":
        if request.count > _MAX_RESULTS[provider_id]:
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
    if provider_id == "deepseek":
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


def search_items(provider_id: str, data: dict) -> list:
    """从供应商响应中取出结果列表，同时识别豆包的显式错误。"""
    if provider_id == "doubao":
        if data.get("ResponseMetadata", {}).get("Error"):
            raise UpstreamError("豆包搜索失败，请检查服务权限与额度", code="web_provider_rejected")
        return data["Result"]["WebResults"]
    return data["results"]


def search_result(provider_id: str, item: dict, include_raw_content: bool) -> dict:
    """保留供应商各字段的实际语义，不混淆相关摘要与正文。"""
    if not isinstance(item, dict):
        raise ValueError("invalid result item")
    if provider_id == "doubao":
        values = {
            "title": item["Title"],
            "url": item["Url"],
            "snippet": item.get("Snippet") or "",
            "relevant_content": item.get("Summary") or "",
            "raw_content": item.get("Content") or "",
            "score": item.get("RankScore"),
            "score_max": _SCORE_MAX[provider_id],
            "site_name": item.get("SiteName"),
            "publish_time": item.get("PublishTime"),
        }
    else:
        values = {
            "title": item["title"],
            "url": item["url"],
            "snippet": item.get("snippet") or "",
            "relevant_content": item.get("content" if provider_id == "tavily" else "summary") or "",
            "raw_content": item.get("raw_content" if provider_id == "tavily" else "content") or "",
            "score": item.get("score" if provider_id == "tavily" else "rerank_score"),
            "score_max": _SCORE_MAX[provider_id],
            "site_name": item.get("site_name"),
            "publish_time": item.get("published_date" if provider_id == "tavily" else "date"),
        }
    if not include_raw_content:
        values["raw_content"] = ""
    return SearchResult.model_validate(values).model_dump()


def fetch_payload(provider_id: str, request: FetchInput) -> dict:
    """按供应商协议构造正文抓取请求。"""
    if provider_id == "tavily":
        return {"urls": [request.url], "format": "markdown", "extract_depth": "basic"}
    return {"url": request.url}


def fetch_result(provider_id: str, data: dict) -> tuple[str, str]:
    """返回标题与正文；供应商响应缺字段由调用方统一映射为上游错误。"""
    if provider_id == "tavily":
        item = data["results"][0]
        content = item.get("raw_content")
        title = item.get("title") or ""
    else:
        content = data.get("content")
        title = data.get("title") or ""
    if not isinstance(content, str) or not content.strip() or not isinstance(title, str):
        raise ValueError("missing page content")
    return title, content
