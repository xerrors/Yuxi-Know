from dataclasses import dataclass, field
from typing import Annotated

from src.agents.common import BaseContext, gen_tool_info
from src.agents.common.mcp import MCP_SERVERS

from .tools import get_tools


@dataclass(kw_only=True)
class Context(BaseContext):
    tools: Annotated[list[dict], {"__template_metadata__": {"kind": "tools"}}] = field(
        default_factory=list,
        metadata={
            "name": "工具",
            "options": gen_tool_info(get_tools()),
            "description": "合同审批相关工具列表",
        },
    )

    mcps: list[str] = field(
        default_factory=list,
        metadata={"name": "MCP服务器", "options": list(MCP_SERVERS.keys()), "description": "MCP服务器列表"},
    )

    # 合同审批特定的配置项
    risk_level: str = field(
        default="中等",
        metadata={
            "name": "风险等级",
            "options": ["低", "中等", "高"],
            "description": "合同风险评估的严格程度",
        },
    )

    check_types: list[str] = field(
        default_factory=lambda: ["法律", "财务", "商业"],
        metadata={
            "name": "检查类型",
            "options": ["法律", "财务", "商业", "技术", "合规"],
            "description": "合同审核的重点领域",
        },
    )

    # 流式输出控制
    streaming: bool = field(
        default=False,
        metadata={
            "name": "流式输出",
            "description": "是否启用流式输出，关闭后将等待完整响应后一次性返回",
        },
    )