import asyncio
import uuid
from typing import Any
from datetime import datetime

from langchain_core.messages import AIMessageChunk, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver

from src.agents.registry import State, BaseAgent
from src.agents.chatbot.configuration import ChatbotConfiguration

class ChatbotAgent(BaseAgent):
    _graph_cache = None

    def __init__(self, configuration: ChatbotConfiguration = None):
        super().__init__(configuration)
        self.configuration = configuration or ChatbotConfiguration()
        self.llm = configuration.llm

    def llm_call(self, state: State) -> dict[str, Any]:
        tools = self.configuration.tools
        system_prompt = {
            "role": "system",
            "content": (
                f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
        }
        messages = [system_prompt] + state["messages"]
        model = self.llm.bind_tools(tools)

        res = model.invoke(messages)
        return {"messages": [res]}

    def get_graph(self):
        """构建图"""
        if ChatbotAgent._graph_cache is None:
            workflow = StateGraph(State)
            workflow.add_node("chatbot", self.llm_call)
            workflow.add_node("tools", ToolNode(tools=self.configuration.tools))
            workflow.add_edge(START, "chatbot")
            workflow.add_conditional_edges(
                "chatbot",
                tools_condition,
            )
            workflow.add_edge("tools", "chatbot")
            workflow.add_edge("chatbot", END)

            graph = workflow.compile(checkpointer=MemorySaver())
            ChatbotAgent._graph_cache = graph

        return ChatbotAgent._graph_cache

    def stream_values(self, messages: list[str], config: RunnableConfig = None):
        graph = self.get_graph()
        for event in graph.stream({"messages": messages}, stream_mode="values", config=config):
            yield event["messages"]

    def stream_messages(self, messages: list[str], config: RunnableConfig = None):
        graph = self.get_graph()
        for msg, metadata in graph.stream({"messages": messages}, stream_mode="messages", config=config):
            msg_type = msg.type

            return_keys = config.get("configurable", {}).get("return_keys", [])
            if not return_keys or msg_type in return_keys:
                yield msg, metadata


def main():
    agent = ChatbotAgent(ChatbotConfiguration())

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    from src.agents import agent_cli
    agent_cli(agent, config)


if __name__ == "__main__":
    main()
    # asyncio.run(main())
