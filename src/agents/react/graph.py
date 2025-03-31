import asyncio
import uuid
from typing import Any
from datetime import datetime

from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from langchain_community.tools.tavily_search import TavilySearchResults


from src.agents.registry import State, BaseAgent
from src.agents.utils import load_chat_model
from src.agents.react.configuration import ReActConfiguration, multiply

class ReActAgent(BaseAgent):
    name = "react"
    description = "A react agent that can answer questions and help with tasks."

    def get_graph(self, **kwargs):
        """构建图"""
        from .workflows import graph
        return graph

def main():
    agent = ReActAgent(ReActConfiguration())

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    from src.agents.utils import agent_cli
    agent_cli(agent, config)


if __name__ == "__main__":
    main()
    # asyncio.run(main())
