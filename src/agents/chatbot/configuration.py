from dataclasses import dataclass, field
from datetime import datetime, timezone


from src.agents.registry import Configuration

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

