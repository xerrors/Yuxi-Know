from dataclasses import dataclass, field

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from src import config
from src.models import select_model
from src.agents.registry import Configuration

def get_default_requirements():
    return ["TAVILY_API_KEY"]

@tool
def multiply(first_int: int, second_int: int) -> int:
    """Multiply two integers together."""
    return first_int * second_int

@dataclass(kw_only=True)
class ChatbotConfiguration(Configuration):
    requirements: list[str] = field(default_factory=get_default_requirements)
    llm: ChatOpenAI | None = None
    model_provider: str = "zhipu"
    model_name: str = "glm-4-plus"

    def __post_init__(self):
        # TODO 需要确保这里的模型是支持 tools 的
        if self.llm is None:
            self.llm = select_model(config=config,
                                    model_provider=self.model_provider,
                                    model_name=self.model_name).chat_open_ai
