"""Define a simple chatbot agent.

This agent returns a predefined response without using an actual LLM.
"""

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph

from src.agents.registry import State, BaseAgent
from src.agents.chatbot.configuration import ChatbotConfiguration
from src.agents.tools_factory import search_tool

class ChatbotAgent(BaseAgent):
    def __init__(self, configuration: ChatbotConfiguration):
        super().__init__(configuration)
        self.llm = configuration.llm
        self.tools = [search_tool]

    async def _get_tools(self):
        return self.tools

    async def llm_call(self, state: State) -> Dict[str, Any]:
        return await self.llm.invoke(state.messages)

    async def get_graph(self):
        workflow = StateGraph(State, config_schema=ChatbotConfiguration)
        workflow.add_node("chat", self.chat)
        workflow.add_edge("__start__", "chat")
        return workflow.compile()

    async def invoke(self, messages: List[str], config: RunnableConfig) -> Dict[str, Any]:
        return await self.get_graph().invoke({"messages": messages}, config)

