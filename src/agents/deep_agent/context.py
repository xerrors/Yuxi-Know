"""Deep Agent Context - 基于BaseContext的深度分析上下文配置"""

from dataclasses import field

from src.agents.common.context import BaseContext


DEEP_PROMPT = """你是一个能够处理复杂、多步骤任务的深度分析代理。

你拥有以下资源：
- 用于分解复杂任务的规划工具
- 用于存储上下文和长期记忆的文件系统
- 用于委派专业工作的子代理
- 知识图谱查询与分析工具

你的工作方式：
1. 仔细分析用户的请求
2. 如果任务复杂，则制定计划
3. 使用合适的工具和子代理
4. 提供全面且有充分推理的回应
5. 存储重要信息以备将来参考

在分析中注重深度、准确性和全面性。"""


class DeepContext(BaseContext):
    """
    Deep Agent 的上下文配置，继承自 BaseContext
    专门用于深度分析任务的配置管理
    """

    # 深度分析专用的系统提示词
    system_prompt: str = field(
        default=DEEP_PROMPT,
        metadata={"name": "系统提示词", "description": "Deep智能体的角色和行为指导"},
    )
