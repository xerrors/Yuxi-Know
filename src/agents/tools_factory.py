import json
import asyncio
import inspect
import types
from collections.abc import Callable
from typing import Annotated, Any

from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool, tool
from langchain_tavily import TavilySearch

from src import config, graph_base, knowledge_base
from src.utils import logger


# 工具注册表 - 移到前面以避免NameError
_TOOLS_REGISTRY = {}


class KnowledgeRetrieverModel(BaseModel):
    query_text: str = Field(
        description=(
            "查询的关键词，查询的时候，应该尽量以可能帮助回答这个问题的关键词进行查询，"
            "不要直接使用用户的原始输入去查询。"
        )
    )

def get_runnable_tools():
    """获取所有可运行的工具（给大模型使用）"""
    tools = _TOOLS_REGISTRY.copy()

    # 获取所有知识库
    for db_Id, retrieve_info in knowledge_base.get_retrievers().items():
        _id = f"retrieve_{db_Id[:8]}" # Deepseek does not support non-alphanumeric characters in tool names
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
        tools[_id] = StructuredTool.from_function(
            coroutine=async_retriever_wrapper,  # 指定为协程
            name=_id,
            description=description,
            args_schema=KnowledgeRetrieverModel,
            metadata=retrieve_info
        )

    return tools

def get_all_tools_info():
    """获取所有工具的信息（用于前端展示）"""
    tools_info = {}

    tools = get_runnable_tools()

    # 获取注册的工具信息
    for _id, tool_obj in tools.items():

        metadata = getattr(tool_obj, 'metadata', {}) or {}
        info = {
            "id": _id,
            "name": metadata.get('name', _id),
            "description": metadata.get('description') or getattr(tool_obj, 'description', ''),
            'metadata': metadata,
            "args": []
        }

        # 获取工具参数信息
        if hasattr(tool_obj, 'args_schema') and tool_obj.args_schema:
            schema = tool_obj.args_schema.schema()
            if 'properties' in schema:
                for arg_name, arg_info in schema['properties'].items():
                    info["args"].append({
                        "name": arg_name,
                        "type": arg_info.get('type', ''),
                        "description": arg_info.get('description', '')
                    })
        tools_info[info['id']] = info

    return tools_info

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

# 更新工具注册表
_TOOLS_REGISTRY.update({
    "Calculator": calculator,
    "QueryKnowledgeGraph": query_knowledge_graph,
})

if config.enable_web_search:
    _TOOLS_REGISTRY["WebSearchWithTavily"] = TavilySearch(max_results=10)
