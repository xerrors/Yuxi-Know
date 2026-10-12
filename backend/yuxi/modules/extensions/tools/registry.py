from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field


@dataclass
class ToolExtraMetadata:
    """附加元数据（用装饰器注册）"""

    category: str = ""  # 分类: builtin, knowledge
    tags: list[str] = field(default_factory=list)
    display_name: str = ""  # 显示名称（给人看的名字）
    icon: str = ""
    config_guide: str = ""  # 配置说明（给人看的使用前配置提示）


# 全局注册表: tool_name -> ToolExtraMetadata
_extra_registry: dict[str, ToolExtraMetadata] = {}

# 全局工具实例列表（由 @tool 装饰器自动收集）
_all_tool_instances: list = []


def get_extra_metadata(tool_name: str) -> ToolExtraMetadata | None:
    """获取工具附加元数据"""
    return deepcopy(_extra_registry.get(tool_name))


def get_all_extra_metadata() -> dict[str, ToolExtraMetadata]:
    """获取所有附加元数据"""
    return deepcopy(_extra_registry)


def get_all_tool_instances() -> list:
    """获取所有工具实例（由 @tool 装饰器自动收集）"""
    return list(_all_tool_instances)


def register_tool(tool_obj, metadata: ToolExtraMetadata) -> None:
    """通过同一入口登记现有工具实例和附加信息。"""
    _extra_registry[tool_obj.name] = deepcopy(metadata)
    tool_obj.handle_tool_error = True
    _all_tool_instances.append(tool_obj)


# 基于 langchain.tool 的拓展装饰器
def tool(
    category: str = "",
    tags: list[str] = None,
    display_name: str = "",
    icon: str = "",
    config_guide: str = "",
    name_or_callable: str | Callable | None = None,
    description: str | None = None,
    args_schema: type | None = None,
    return_direct: bool = False,
):
    """基于 langchain.tool 的拓展装饰器，同时注册元数据

    使用方式:
    @tool(category="builtin", tags=["计算"], display_name="计算器")
    def calculator(a: float, b: float, operation: str) -> float:
        ...

    或者保留原有的 name_or_callable 和 description 参数来自定义工具名称和说明。
    """
    from langchain.tools import tool as langchain_tool

    # 先应用 langchain tool 装饰器
    langchain_decorator = langchain_tool(
        name_or_callable=name_or_callable,
        description=description,
        args_schema=args_schema,
        return_direct=return_direct,
    )

    def decorator(func: Callable) -> Callable:
        # 应用 langchain 装饰器
        tool_obj = langchain_decorator(func)

        # 注册附加元数据
        metadata = ToolExtraMetadata(
            category=category,
            tags=tags or [],
            display_name=display_name,
            icon=icon,
            config_guide=config_guide,
        )

        # 自动收集工具实例
        register_tool(tool_obj, metadata)

        return tool_obj

    return decorator
