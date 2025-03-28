import asyncio
import uuid
from typing import Any
from datetime import datetime

from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver

from src.agents.registry import State, BaseAgent
from src.agents.chatbot.configuration import ChatbotConfiguration, multiply

class ChatbotAgent(BaseAgent):
    name = "chatbot"
    description = "A chatbot that can answer questions and help with tasks."
    _graph_cache = None
    config_schema = ChatbotConfiguration

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _get_tools(self, config_schema: RunnableConfig):
        """根据配置获取工具"""
        conf = ChatbotConfiguration.from_runnable_config(config_schema)
        tools = [multiply]
        if not conf:
            return tools

        if conf.get("use_web", None):
            from langchain_community.tools.tavily_search import TavilySearchResults
            tools.append(TavilySearchResults(max_results=10))

        return tools

    def llm_call(self, state: State, config: RunnableConfig) -> dict[str, Any]:
        model = self.llm.bind_tools(self._get_tools(config))

        res = model.invoke(state["messages"])
        return {"messages": [res]}

    def get_graph(self, config_schema: RunnableConfig = None):
        """构建图"""
        workflow = StateGraph(State)
        workflow.add_node("chatbot", self.llm_call)
        workflow.add_node("tools", ToolNode(tools=self._get_tools(config_schema)))
        workflow.add_edge(START, "chatbot")
        workflow.add_conditional_edges(
            "chatbot",
            tools_condition,
        )
        workflow.add_edge("tools", "chatbot")
        workflow.add_edge("chatbot", END)

        graph = workflow.compile(checkpointer=MemorySaver())
        return graph

    def stream_values(self, messages: list[str], config_schema: RunnableConfig = None):
        graph = self.get_graph(config_schema)
        for event in graph.stream({"messages": messages}, stream_mode="values", config=config_schema):
            yield event["messages"]

    def stream_messages(self, messages: list[str], config: RunnableConfig = None):
        graph = self.get_graph(config)
        for msg, metadata in graph.stream({"messages": messages}, stream_mode="messages", config=config):
            msg_type = msg.type

            return_keys = config.get("configurable", {}).get("return_keys", [])
            if not return_keys or msg_type in return_keys:
                yield msg, metadata

def main():
    agent = ChatbotAgent(ChatbotConfiguration())

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    from src.agents.utils import agent_cli
    agent_cli(agent, config)


if __name__ == "__main__":
    main()
    # asyncio.run(main())
