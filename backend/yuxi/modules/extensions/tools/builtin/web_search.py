"""稳定注册网页工具，供应商与凭据在执行时解析。"""

from langchain_core.tools import ToolException

from yuxi.modules.extensions.tools.registry import tool
from yuxi.modules.extensions.web.schemas import FetchInput, SearchInput
from yuxi.modules.extensions.web.services import fetch_web, search_web
from yuxi.shared.errors import DomainError


@tool(
    category="builtin",
    tags=["搜索"],
    display_name="网络搜索",
    config_guide="在设置 → 网络搜索中配置默认搜索供应商和 API Key。",
    name_or_callable="web_search",
    args_schema=SearchInput,
)
async def web_search(
    query: str,
    count: int = 10,
    time_range: str | None = None,
    sites: list[str] | None = None,
    block_hosts: list[str] | None = None,
    content_format: str = "markdown",
    include_raw_content: bool = False,
) -> dict:
    """搜索公开网页，返回标题、链接、摘要和相关片段；需要全文时使用 web_fetch。"""
    try:
        return await search_web(
            SearchInput(
                query=query,
                count=count,
                time_range=time_range,
                sites=sites,
                block_hosts=block_hosts,
                content_format=content_format,
                include_raw_content=include_raw_content,
            )
        )
    except DomainError as exc:
        raise ToolException(exc.message) from None


@tool(
    category="builtin",
    tags=["搜索"],
    display_name="网页抓取",
    config_guide="在设置 → 网络搜索中配置默认 Fetch 供应商和 API Key。",
    name_or_callable="web_fetch",
    args_schema=FetchInput,
)
async def web_fetch(url: str) -> dict:
    """读取指定公开网页的 Markdown 正文，适用于深入阅读搜索结果中的链接。"""
    try:
        return await fetch_web(FetchInput(url=url))
    except DomainError as exc:
        raise ToolException(exc.message) from None
