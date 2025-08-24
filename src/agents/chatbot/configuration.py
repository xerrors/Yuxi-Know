import uuid

from dataclasses import dataclass, field

from src.agents.registry import Configuration
from src.agents.tools_factory import get_buildin_tools

@dataclass(kw_only=True)
class ChatbotConfiguration(Configuration):
    """Chatbot 的配置

    配置说明：

    metadata 中 configurable 为 True 的配置项可以被用户配置，
    configurable 为 False 的配置项不能被用户配置，只能由开发者预设。
    除非显示配置为 False，否则所有配置项都默认可配置。
    """

    system_prompt: str = field(
        default="You are a helpful assistant.",
        metadata={
            "name": "系统提示词",
            "description": "用来描述智能体的角色和行为"
        },
    )

    model: str = field(
        default="siliconflow/Qwen/Qwen3-235B-A22B-Instruct-2507",
        metadata={
            "name": "智能体模型",
            "options": [],
            "description": "智能体的驱动模型"
        },
    )

    tools: list[str] = field(
        default_factory=list,
        metadata={
            "name": "工具",
            "options": list(get_buildin_tools().keys()),  # 这里的选择是所有的工具
            "description": "工具列表"
        },
    )
