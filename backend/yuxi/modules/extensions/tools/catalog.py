from copy import deepcopy
from typing import Any


def _extract_tool_info(tool_obj) -> dict:
    """从 tool_obj 提取基础信息"""
    metadata = getattr(tool_obj, "metadata", {}) or {}
    info = {
        "slug": tool_obj.name,
        "name": metadata.get("name", tool_obj.name),  # 显示名称优先从 metadata 获取
        "description": tool_obj.description,
        "metadata": metadata,
        "args": [],
    }

    if hasattr(tool_obj, "args_schema") and tool_obj.args_schema:
        schema = tool_obj.args_schema
        if hasattr(schema, "model_json_schema"):
            schema = schema.model_json_schema()
        elif hasattr(schema, "schema"):
            schema = schema.schema()
        for arg_name, arg_info in schema.get("properties", {}).items():
            info["args"].append(
                {
                    "name": arg_name,
                    "type": arg_info.get("type", ""),
                    "description": arg_info.get("description", ""),
                }
            )
    return info


def get_tool_metadata(category: str | None = None) -> list[dict]:
    """从当前注册表派生独立元数据，动态注册立即可见。"""
    from yuxi.modules.extensions.tools.registry import get_all_extra_metadata, get_all_tool_instances

    extra_meta = get_all_extra_metadata()
    result = []
    for tool in get_all_tool_instances():
        extra = extra_meta.get(tool.name)
        tool_category = extra.category if extra else "builtin"
        if category is not None and tool_category != category:
            continue
        info = _extract_tool_info(tool)
        info.update(category=tool_category, tags=extra.tags if extra else [], config_guide=extra.config_guide if extra else "")
        if extra and extra.display_name:
            info["name"] = extra.display_name
        result.append(deepcopy(info))
    return result


def get_tool_instances_by_category(category: str) -> list[Any]:
    from yuxi.modules.extensions.tools.registry import get_all_extra_metadata, get_all_tool_instances

    extra_meta = get_all_extra_metadata()
    tools = []
    for tool in get_all_tool_instances():
        tool_meta = extra_meta.get(tool.name)
        tool_category = tool_meta.category if tool_meta else "builtin"
        if tool_category == category:
            tools.append(tool)
    return tools
