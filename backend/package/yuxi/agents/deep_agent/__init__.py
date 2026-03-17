"""Deep Agent - 深度分析智能体模块

基于 deepagents 库构建的深度分析智能体，具备以下特性：
- 任务规划和分解能力
- 深度知识搜索和分析
- 子智能体协作
- 文件系统和长期记忆
- 综合分析和报告生成
"""

from .context import DeepContext
from .graph import DeepAgent

__all__ = [
    "DeepAgent",
    "DeepContext",
]

# 模块元数据
__version__ = "1.0.0"
__author__ = "Yuxi-Know Team"
__description__ = "基于 create_deep_agent 的深度分析智能体"
