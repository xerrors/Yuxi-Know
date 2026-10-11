"""按供应商配置注册网页搜索工具。"""

import os

import httpx
from langchain_core.tools import tool as langchain_tool
from pydantic import BaseModel, Field

from yuxi.infrastructure.observability.logging import logger
from yuxi.modules.extensions.tools.registry import ToolExtraMetadata, _all_tool_instances, _extra_registry

_DOUBAO_SEARCH_URL = "https://open.feedcoopapi.com/search_api/web_search"

DOUBAO_SEARCH_DESCRIPTION = """执行网络网页搜索，通过豆包联网搜索获取实时高质量互联网网页内容、新闻和站点资料。

适用场景：
1. 获取最新的时事新闻、即时信息或最新科技动态
2. 检索特定网站的内容（通过 sites 参数指定）
3. 查找指定时间范围内发布的新闻或文章（通过 time_range 参数过滤）

参数使用建议：
- query: 输入简短清晰的搜索关键词或简短提问
- count: 默认 10 条，深度调研可适当调大（最多 50 条）
- time_range: 需要最新消息或时效性强的资讯时建议传入 'OneDay'、'OneWeek' 或 'OneMonth'
- sites: 仅需特定站点（如官媒、平台）时传入站点域名
"""


class DoubaoSearchInput(BaseModel):
    """豆包网页搜索参数。"""

    query: str = Field(description="搜索查询词，1-100字符，必须精准描述检索需求")
    count: int = Field(default=10, ge=1, le=50, description="返回搜索结果数量，支持 1-50 条，默认 10 条")
    time_range: str | None = Field(
        default=None,
        description=(
            "按发文时间筛选结果。可选枚举值:\n"
            "- 'OneDay': 近24小时内\n"
            "- 'OneWeek': 近1周内\n"
            "- 'OneMonth': 近1个月内\n"
            "- 'OneYear': 近1年内\n"
            "- 'YYYY-MM-DD..YYYY-MM-DD': 自定义日期范围区间 (如 '2025-01-01..2025-12-31')"
        ),
    )
    sites: list[str] | None = Field(default=None, description="指定限定搜索的完整域名列表 (如 ['sohu.com', '163.com'])，最多支持 20 个站点")
    block_hosts: list[str] | None = Field(default=None, description="指定屏蔽的搜索域名列表 (如 ['example.com'])，最多支持 5 个站点")
    content_format: str = Field(default="text", description="正文返回格式，支持 'text' (纯文本) 或 'markdown' (Markdown 格式)，默认 'text'")


@langchain_tool("web_search", args_schema=DoubaoSearchInput, description=DOUBAO_SEARCH_DESCRIPTION)
def _doubao_search(
    query: str,
    count: int = 10,
    time_range: str | None = None,
    sites: list[str] | None = None,
    block_hosts: list[str] | None = None,
    content_format: str = "text",
) -> dict:
    """执行豆包搜索并返回网页结果。"""
    api_key = os.getenv("DOUBAO_SEARCH_API_KEY")
    if not api_key:
        return {"query": query, "results": [], "error": "DOUBAO_SEARCH_API_KEY 未配置"}

    payload = _build_doubao_search_payload(query, count, time_range, sites, block_hosts, content_format)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(_DOUBAO_SEARCH_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.error(f"Doubao search failed: {exc}")
        return {"query": query, "results": [], "error": str(exc)}

    return _parse_doubao_search_response(query, data)


def _build_doubao_search_payload(
    query: str,
    count: int,
    time_range: str | None,
    sites: list[str] | None,
    block_hosts: list[str] | None,
    content_format: str,
) -> dict:
    """构造供应商搜索请求。"""
    filter_obj: dict[str, str | bool] = {"NeedUrl": True}
    if sites:
        filter_obj["Sites"] = "|".join(sites[:20])
    if block_hosts:
        filter_obj["BlockHosts"] = "|".join(block_hosts[:5])

    payload = {
        "Query": query[:100],
        "SearchType": "web",
        "Count": min(max(1, count), 50),
        "Filter": filter_obj,
        "ContentFormats": "markdown" if content_format.lower() == "markdown" else "text",
    }
    if time_range:
        payload["TimeRange"] = time_range
    return payload


def _parse_doubao_search_response(query: str, data: dict) -> dict:
    """将供应商响应转换为工具结果。"""
    error_info = data.get("ResponseMetadata", {}).get("Error")
    if error_info:
        logger.error(f"Doubao search API returned error: {error_info}")
        return {"query": query, "results": [], "error": error_info.get("Message", "Unknown error")}

    result_data = data.get("Result") or {}
    results = []
    for item in result_data.get("WebResults") or []:
        res_item = {
            "title": item.get("Title") or "",
            "url": item.get("Url") or "",
            "content": item.get("Summary") or item.get("Snippet") or item.get("Content") or "",
            "score": item.get("RankScore"),
        }
        if item.get("SiteName"):
            res_item["site_name"] = item["SiteName"]
        if item.get("PublishTime"):
            res_item["publish_time"] = item["PublishTime"]
        results.append(res_item)

    return {
        "query": query,
        "results": results,
        "response_time": result_data.get("TimeCost", 0) / 1000.0,
    }


def _create_doubao_search():
    """返回豆包网页搜索工具。"""
    return _doubao_search


def _create_tavily_search():
    """创建统一命名的 Tavily 搜索工具。"""
    from langchain_tavily import TavilySearch

    return TavilySearch(name="web_search")


# provider -> (required env var, factory, display name)
_WEB_SEARCH_PROVIDERS = {
    "doubao": ("DOUBAO_SEARCH_API_KEY", _create_doubao_search, "豆包 网页搜索"),
    "tavily": ("TAVILY_API_KEY", _create_tavily_search, "Tavily 网页搜索"),
}


def _register_web_search_tool() -> None:
    """注册配置或自动选择的网页搜索工具。"""
    provider = _resolve_web_search_provider()
    if provider is None:
        reason = "provider_unavailable" if os.getenv("WEB_SEARCH_PROVIDER", "").strip() else "credentials_missing"
        logger.bind(component="web_search", reason=reason, available=False).warning(
            "component=web_search reason={} available=false 网页搜索不可用，工具未注册", reason
        )
        return

    _, create_tool, display_name = _WEB_SEARCH_PROVIDERS[provider]
    _extra_registry["web_search"] = ToolExtraMetadata(category="builtin", tags=["搜索"], display_name=display_name)
    _all_tool_instances.append(create_tool())


def _resolve_web_search_provider() -> str | None:
    """从显式配置或可用凭据选择搜索供应商。"""
    configured = os.getenv("WEB_SEARCH_PROVIDER", "").strip().lower()
    if configured:
        if configured not in _WEB_SEARCH_PROVIDERS:
            logger.warning(f"Unknown WEB_SEARCH_PROVIDER '{configured}', ignoring.")
            return None
        env_key, _, _ = _WEB_SEARCH_PROVIDERS[configured]
        if not os.getenv(env_key):
            logger.warning(f"WEB_SEARCH_PROVIDER is set to '{configured}', but {env_key} is not configured.")
            return None
        return configured

    return next(
        (provider for provider, (env_key, _, _) in _WEB_SEARCH_PROVIDERS.items() if os.getenv(env_key)),
        None,
    )


# 模块加载时注册网络搜索工具
try:
    _register_web_search_tool()
except Exception as e:
    logger.bind(component="web_search", reason="registration_failed", error_type=type(e).__name__, available=False).warning(
        "component=web_search reason=registration_failed error_type={} available=false 网页搜索注册失败，工具不可用",
        type(e).__name__,
    )
