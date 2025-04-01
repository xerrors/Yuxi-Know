from dataclasses import dataclass, field
from datetime import datetime, timezone

from langchain_community.tools.tavily_search import TavilySearchResults

from src.agents.registry import Configuration
from src.agents.tools_factory import multiply, add, subtract, divide



def get_default_tools():
    return ["TavilySearchResults", "multiply", "add", "subtract", "divide"]

@dataclass(kw_only=True)
class ChatbotConfiguration(Configuration):
    """Chatbot 的配置"""

    system_prompt: str = field(
        default=f"You are a helpful assistant. Now is {datetime.now(tz=timezone.utc).isoformat()}",
        metadata={
            "description": "The system prompt to use for the agent's interactions. "
            "This prompt sets the context and behavior for the agent."
        },
    )

    model: str = field(
        default="zhipu/glm-4-plus",
        metadata={
            "description": "The name of the language model to use for the agent's main interactions. "
            "Should be in the form: provider/model-name."
        },
    )

    tools: list = field(
        default_factory=get_default_tools,
        metadata={
            "description": "The tools to use for the agent's interactions. "
            "Should be in the form: provider/model-name."
        },
    )

    temperature: float = field(
        default=0.7,
        metadata={
            "description": "控制模型生成结果的随机性，值越大随机性越高，建议范围 0.0-1.0"
        },
    )

    use_tools: bool = field(
        default=True,
        metadata={
            "description": "是否启用工具调用功能"
        },
    )

    max_iterations: int = field(
        default=10,
        metadata={
            "description": "智能体最大执行步数，防止无限循环"
        },
    )

