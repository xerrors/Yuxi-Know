# toolkits 包

# 触发各模块的 @tool 装饰器执行、自动注册工具
from yuxi.modules.extensions.tools import builtin

# 工具获取函数
from yuxi.modules.extensions.tools.registry import (
    ToolExtraMetadata,
    get_all_extra_metadata,
    get_all_tool_instances,
    get_extra_metadata,
    tool,
)

__all__ = [
    "get_extra_metadata",
    "get_all_extra_metadata",
    "get_all_tool_instances",
    "ToolExtraMetadata",
    "tool",
    # 触发各模块的 @tool 装饰器执行、自动注册工具
    "builtin",
]
