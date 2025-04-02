import asyncio
import uuid
from typing import Any
from datetime import datetime, timezone

from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver # 实际上没有起作用


from src.utils import logger
from src.agents.registry import State, BaseAgent
from src.agents.utils import load_chat_model, get_cur_time_with_utc
from src.agents.chatbot.configuration import ChatbotConfiguration
from src.agents.tools_factory import _TOOLS_REGISTRY

class ChatbotAgent(BaseAgent):
    name = "chatbot"
    description = "A chatbot that can answer questions and help with tasks."
    requirements = ["TAVILY_API_KEY", "ZHIPUAI_API_KEY"]
    all_tools = ["TavilySearchResults", "multiply", "add", "subtract", "divide"]
    config_schema = ChatbotConfiguration

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _get_tools(self, config_schema: RunnableConfig):
        """根据配置获取工具，如果配置为空，则使用所有工具，如果配置为列表，则使用列表中的工具，
        如果配置为其他类型，则抛出错误"""
        conf_tools = config_schema.get("tools")
        if conf_tools == None:
            tool_names = self.all_tools
        elif isinstance(conf_tools, list):
            tool_names = [tool for tool in self.all_tools if tool in conf_tools]
        else:
            raise ValueError(f"tools 配置错误: {conf_tools}")

        logger.info(f"Tools: {tool_names}")
        return [_TOOLS_REGISTRY[tool] for tool in tool_names]

    def llm_call(self, state: State, config: RunnableConfig = None) -> dict[str, Any]:
        """调用 llm 模型"""
        config_schema = config or {}
        conf = self.config_schema.from_runnable_config(config_schema)

        system_prompt = f"{conf.system_prompt} Now is {get_cur_time_with_utc()}"
        model = load_chat_model(conf.model)
        model_with_tools = model.bind_tools(self._get_tools(config_schema))
        logger.info(f"llm_call with config: {conf}, {conf.model}")

        res = model_with_tools.invoke(
            [{"role": "system", "content": system_prompt}, *state["messages"]]
        )
        return {"messages": [res]}

    def get_graph(self, config_schema: RunnableConfig = None, **kwargs):
        """构建图"""
        workflow = StateGraph(State, config_schema=self.config_schema)
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


def main():
    agent = ChatbotAgent(ChatbotConfiguration())

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    from src.agents.utils import agent_cli
    agent_cli(agent, config)


if __name__ == "__main__":
    main()
    # asyncio.run(main())
