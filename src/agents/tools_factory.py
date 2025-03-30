import json
import re
import os
from typing import Any, Callable, Optional, Type, Union


from pydantic import BaseModel, Field
from langchain.agents import tool
from langchain_core.tools import Tool, BaseTool


_TOOLS_REGISTRY = {}

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

