"""外部网页搜索与抓取供应商的静态目录，供配置定义和运行时适配共享。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WebProvider:
    """一个供应商的公开身份、凭据变量与官方端点。"""

    id: str
    name: str
    environment: str
    supports_fetch: bool
    search_endpoint: str
    fetch_endpoint: str | None


WEB_PROVIDERS = (
    WebProvider(
        id="tavily",
        name="Tavily",
        environment="TAVILY_API_KEY",
        supports_fetch=True,
        search_endpoint="https://api.tavily.com/search",
        fetch_endpoint="https://api.tavily.com/extract",
    ),
    WebProvider(
        id="deepseek",
        name="DeepSeek",
        environment="DEEPSEEK_API_KEY",
        supports_fetch=True,
        search_endpoint="https://api.deepseek.com/v1/tools/search",
        fetch_endpoint="https://api.deepseek.com/v1/tools/fetch",
    ),
    WebProvider(
        id="doubao",
        name="豆包 Custom",
        environment="DOUBAO_SEARCH_API_KEY",
        supports_fetch=False,
        search_endpoint="https://open.feedcoopapi.com/search_api/web_search",
        fetch_endpoint=None,
    ),
)

PROVIDERS_BY_ID = {provider.id: provider for provider in WEB_PROVIDERS}
SEARCH_PROVIDER_IDS = tuple(provider.id for provider in WEB_PROVIDERS)
FETCH_PROVIDER_IDS = tuple(provider.id for provider in WEB_PROVIDERS if provider.supports_fetch)
