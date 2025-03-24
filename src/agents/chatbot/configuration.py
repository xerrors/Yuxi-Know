from dataclasses import dataclass, field
from typing import List

from langchain_core.tools import Tool
from langchain_openai import ChatOpenAI

from src import config
from src.models import select_model
from src.agents.registry import Configuration


@dataclass(kw_only=True)
class ChatbotConfiguration(Configuration):
    name: str = "chatbot"
    llm: ChatOpenAI = field(default_factory=select_model().chat_open_ai)
    tools: List[Tool] = field(default_factory=list)