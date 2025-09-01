import os

from tavily import TavilyClient

from src.utils.logging_config import logger


class WebSearcher:
    def __init__(self):
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise ValueError("TAVILY_API_KEY environment variable is not set")
        self.client = TavilyClient(api_key)
        logger.info("WebSearcher initialized with Tavily client")

    def search(self, query: str, max_results: int = 1) -> list[dict]:
        """
        使用 Tavily 搜索相关内容

        Args:
            query: 搜索查询
            max_results: 最大返回结果数

        Returns:
            搜索结果列表
        """
        try:
            search_results = self.client.search(query=query, search_depth="basic", max_results=max_results)

            # 提取需要的信息
            formatted_results = []
            for result in search_results["results"][:max_results]:
                formatted_results.append(
                    {
                        "title": result.get("title", ""),
                        "content": result.get("content", ""),
                        "url": result.get("url", ""),
                        "score": result.get("score", 0),
                    }
                )

            return formatted_results

        except Exception as e:
            logger.error(f"Error during web search: {str(e)}")
            return []

    def format_search_results(self, results: list[dict]) -> str:
        """
        将搜索结果格式化为文本

        Args:
            results: 搜索结果列表

        Returns:
            格式化后的文本
        """
        if not results:
            return "没有找到相关的网络搜索结果。"

        formatted_text = "以下是相关的网络搜索结果：\n\n"
        for i, result in enumerate(results, 1):
            formatted_text += f"{i}. {result['title']}\n"
            formatted_text += f"   {result['content']}\n"
            formatted_text += f"   来源: {result['url']}\n\n"

        return formatted_text
