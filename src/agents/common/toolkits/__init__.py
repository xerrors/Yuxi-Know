# toolkits 包
from .registry import (
    ToolExtraMetadata,
    get_all_extra_metadata,
    get_all_tool_instances,
    get_extra_metadata,
    tool,
)

# 工具获取函数
from .kbs import get_common_kb_tools

# 触发各模块的 @tool 装饰器执行，自动注册工具
from . import buildin
from . import debug
from . import mysql


__all__ = [
    "get_extra_metadata",
    "get_all_extra_metadata",
    "get_all_tool_instances",
    "ToolExtraMetadata",
    "tool",
    "get_common_kb_tools",
]
