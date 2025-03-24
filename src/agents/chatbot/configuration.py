from dataclasses import dataclass, field
from typing import List

from langchain_core.messages import SystemMessage
from langchain_core.tools import Tool
from langchain_openai import ChatOpenAI

from src import config
from src.models import select_model
from src.agents.registry import Configuration

def get_default_llm():
    return select_model(config).chat_open_ai

def get_default_tools():
    from langchain_community.tools.tavily_search import TavilySearchResults
    return [TavilySearchResults(max_results=10)]

def get_default_requirements():
    return ["TAVILY_API_KEY"]

@dataclass(kw_only=True)
class ChatbotConfiguration(Configuration):
    name: str = "chatbot"
    description: str = "A chatbot that can answer questions and help with tasks."
    requirements: list[str] = field(default_factory=get_default_requirements)
    tools: list[Tool] = field(default_factory=get_default_tools)
    llm: ChatOpenAI = field(default_factory=get_default_llm)
