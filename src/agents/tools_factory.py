import json
import re
import os
from typing import Any, Callable, Optional, Type, Union, Annotated


from pydantic import BaseModel, Field
from langchain_core.tools import tool, BaseTool, StructuredTool
from langchain_community.tools.tavily_search import TavilySearchResults

from src import graph_base, knowledge_base, config

# refs https://github.com/chatchat-space/LangGraph-Chatchat chatchat-server/chatchat/server/agent/tools_factory/tools_registry.py
def regist_tool(
    *args: Any,
    title: str = "",
    description: str = "",
    return_direct: bool = False,
    args_schema: Optional[Type[BaseModel]] = None,
    infer_schema: bool = True,
) -> Union[Callable, BaseTool]:
    """
    wrapper of langchain tool decorator
    add tool to registry automatically
    """

    def _parse_tool(t: BaseTool):
        nonlocal description, title

        _TOOLS_REGISTRY[t.name] = t

        # change default description
        if not description:
            if t.func is not None:
                description = t.func.__doc__
            elif t.coroutine is not None:
                description = t.coroutine.__doc__
        t.description = " ".join(re.split(r"\n+\s*", description))
        # set a default title for human
        if not title:
            title = "".join([x.capitalize() for x in t.name.split("_")])
        setattr(t, "_title", title)

    def wrapper(def_func: Callable) -> BaseTool:
        partial_ = tool(
            *args,
            return_direct=return_direct,
            args_schema=args_schema,
            infer_schema=infer_schema,
        )
        t = partial_(def_func)
        _parse_tool(t)
        return t

    if len(args) == 0:
        return wrapper
    else:
        t = tool(
            *args,
            return_direct=return_direct,
            args_schema=args_schema,
            infer_schema=infer_schema,
        )
        _parse_tool(t)
        return t


class KnowledgeRetrieverModel(BaseModel):
    query: str = Field(description="查询的关键词，查询的时候，应该尽量以可能帮助回答这个问题的关键词进行查询，不要直接使用用户的原始输入去查询。")



def get_all_tools():
    """获取所有工具"""
    tools = _TOOLS_REGISTRY.copy()

    # 获取所有知识库
    for db_Id, retrieve_info in knowledge_base.get_retrievers().items():
        name = f"retrieve_{retrieve_info['name']}"
        description = (
            f"使用 {retrieve_info['name']} 知识库进行检索。\n"
            f"下面是这个知识库的描述：\n{retrieve_info['description']}"
        )
        tools[name] = StructuredTool.from_function(
            retrieve_info["retriever"],
            name=name,
            description=description,
            args_schema=KnowledgeRetrieverModel)

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
        format: str | Callable = None,
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
    """Calculate two numbers."""
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
def get_knowledge_graph(query: Annotated[str, "The query to get knowledge graph."]):
    """Use this to get knowledge graph."""
    return graph_base.query_node(query, hops=2)




_TOOLS_REGISTRY = {
    "calculator": calculator,
    "get_knowledge_graph": get_knowledge_graph,
}

if config.enable_web_search:
    _TOOLS_REGISTRY["TavilySearchResults"] = TavilySearchResults(max_results=10)
