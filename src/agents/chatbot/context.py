from typing import Annotated
from dataclasses import dataclass, field

from src.agents.common.context import BaseContext
from src.agents.common.tools import gen_tool_info

from .tools import get_tools

@dataclass(kw_only=True)
class Context(BaseContext):

    model: Annotated[str, {"__template_metadata__": {"kind": "llm"}}] = field(
        default="siliconflow/Qwen/Qwen3-235B-A22B-Instruct-2507",
        metadata={
            "name": "智能体模型",
            "options": [],
            "description": "智能体的驱动模型"
        },
    )

    tools: Annotated[list[dict], {"__template_metadata__": {"kind": "tools"}}] = field(
        default_factory=list,
        metadata={
            "name": "工具",
            "options": gen_tool_info(get_tools()),  # 这里的选择是所有的工具
            "description": "工具列表"
        },
    )
