"""Deep Agent Context - 基于BaseContext的深度分析上下文配置"""

from dataclasses import dataclass, field
from typing import Annotated

from yuxi.agents import BaseContext

from .prompt import DEEP_PROMPT


@dataclass
class DeepContext(BaseContext):
    """
    Deep Agent 的上下文配置，继承自 BaseContext
    专门用于深度分析任务的配置管理
    """

    # 深度分析专用的系统提示词
    system_prompt: Annotated[str, {"__template_metadata__": {"kind": "prompt"}}] = field(
        default=DEEP_PROMPT,
        metadata={"name": "系统提示词", "description": "Deep智能体的角色和行为指导"},
    )

    subagents_model: Annotated[str, {"__template_metadata__": {"kind": "llm"}}] = field(
        default="siliconflow/Pro/deepseek-ai/DeepSeek-V3.2",
        metadata={
            "name": "Sub-agent Model",
            "description": "子智能体的默认模型，会被子智能体的配置覆盖。",
        },
    )
