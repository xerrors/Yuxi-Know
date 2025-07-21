import json
import asyncio
from collections.abc import Callable
from typing import Annotated, Any

from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool, tool
from langchain_tavily import TavilySearch

from src import config, graph_base, knowledge_base
from src.utils import logger


class KnowledgeRetrieverModel(BaseModel):
    query_text: str = Field(
        description=(
            "查询的关键词，查询的时候，应该尽量以可能帮助回答这个问题的关键词进行查询，"
            "不要直接使用用户的原始输入去查询。"
        )
    )

def get_all_tools():
    """获取所有工具"""
    tools = _TOOLS_REGISTRY.copy()

    # 获取所有知识库
    for db_Id, retrieve_info in knowledge_base.get_retrievers().items():
        name = f"retrieve_{db_Id[:8]}" # Deepseek does not support non-alphanumeric characters in tool names
        description = (
            f"使用 {retrieve_info['name']} 知识库进行检索。\n"
            f"下面是这个知识库的描述：\n{retrieve_info['description']}"
        )

        # 创建异步工具，确保正确处理异步检索器
        async def async_retriever_wrapper(query_text: str, db_id=db_Id, retriever_info=retrieve_info):
            """异步检索器包装函数"""
            retriever = retriever_info["retriever"]
            try:
                if asyncio.iscoroutinefunction(retriever):
                    result = await retriever(query_text)
                else:
                    result = retriever(query_text)
                return result
            except Exception as e:
                logger.error(f"Error in retriever {db_id}: {e}")
                return f"检索失败: {str(e)}"

        # 使用 StructuredTool.from_function 创建异步工具
        tools[name] = StructuredTool.from_function(
            coroutine=async_retriever_wrapper,  # 指定为协程
            name=name,
            description=description,
            args_schema=KnowledgeRetrieverModel
        )

    return tools

class BaseToolOutput:
    """
    LLM 要求 Tool 的输出为 str，但 Tool 用在别处时希望它正常返回结构化数据。
    只需要将 Tool 返回值用该类封装，能同时满足两者的需要。
    基类简单的将返回值字符串化，或指定 format="json" 将其转为 json。
    用户也可以继承该类定义自己的转换方法。
    """

    def __init__(
        self,
        data: Any,
        format: str | Callable | None = None,
        data_alias: str = "",
        **extras: Any,
    ) -> None:
        self.data = data
        self.format = format
        self.extras = extras
        if data_alias:
            setattr(self, data_alias, property(lambda obj: obj.data))

    def __str__(self) -> str:
        if self.format == "json":
            return json.dumps(self.data, ensure_ascii=False, indent=2)
        elif callable(self.format):
            return self.format(self)
        else:
            return str(self.data)

@tool
def calculator(a: float, b: float, operation: str) -> float:
    """Calculate two numbers. operation: add, subtract, multiply, divide"""
    if operation == "add":
        return a + b
    elif operation == "subtract":
        return a - b
    elif operation == "multiply":
        return a * b
    elif operation == "divide":
        return a / b
    else:
        raise ValueError(f"Invalid operation: {operation}, only support add, subtract, multiply, divide")

@tool
def query_knowledge_graph(query: Annotated[str, "The keyword to query knowledge graph."]):
    """Use this to query knowledge graph."""
    return graph_base.query_node(query, hops=2)




_TOOLS_REGISTRY = {
    "Calculator": calculator,
    "QueryKnowledgeGraph": query_knowledge_graph,
}

if config.enable_web_search:
    _TOOLS_REGISTRY["WebSearchWithTavily"] = TavilySearch(max_results=10)
