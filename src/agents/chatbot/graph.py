import uuid
from pathlib import Path
from typing import Any, cast

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.runtime import Runtime

from src import config as sys_config
from src.agents.common.base import BaseAgent
from src.agents.common.mcp import get_mcp_tools
from src.agents.common.models import load_chat_model
from src.utils import logger

from .context import Context
from .state import State
from .tools import get_tools


class ChatbotAgent(BaseAgent):
    name = "智能体助手"
    description = "基础的对话机器人，可以回答问题，默认不使用任何工具，可在配置中启用需要的工具。"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.graph = None
        self.checkpointer = InMemorySaver()
        self.context_schema = Context
        self.workdir = Path(sys_config.save_dir) / "agents" / self.module_name
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.agent_tools = None

    def get_tools(self):
        return get_tools()

    async def _get_invoke_tools(self, selected_tools: list[str], selected_mcps: list[str]):
        """根据配置获取工具。
        默认不使用任何工具。
        如果配置为列表，则使用列表中的工具。
        """
        enabled_tools = []
        self.agent_tools = self.agent_tools or self.get_tools()
        if selected_tools and isinstance(selected_tools, list) and len(selected_tools) > 0:
            # 使用配置中指定的工具
            enabled_tools = [tool for tool in self.agent_tools if tool.name in selected_tools]

        if selected_mcps and isinstance(selected_mcps, list) and len(selected_mcps) > 0:
            for mcp in selected_mcps:
                enabled_tools.extend(await get_mcp_tools(mcp))

        return enabled_tools

    async def llm_call(self, state: State, runtime: Runtime[Context] = None) -> dict[str, Any]:
        """调用 llm 模型 - 异步版本以支持异步工具"""
        model = load_chat_model(runtime.context.model)

        # 这里要根据配置动态获取工具
        available_tools = await self._get_invoke_tools(runtime.context.tools, runtime.context.mcps)
        logger.info(f"LLM binded ({len(available_tools)}) available_tools: {[tool.name for tool in available_tools]}")

        if available_tools:
            model = model.bind_tools(available_tools)

        # 使用异步调用
        response = cast(
            AIMessage,
            await model.ainvoke([{"role": "system", "content": runtime.context.system_prompt}, *state.messages]),
        )
        return {"messages": [response]}

    async def dynamic_tools_node(self, state: State, runtime: Runtime[Context]) -> dict[str, list[ToolMessage]]:
        """Execute tools dynamically based on configuration.

        This function gets the available tools based on the current configuration
        and executes the requested tool calls from the last message.
        """
        # Get available tools based on configuration
        available_tools = await self._get_invoke_tools(runtime.context.tools, runtime.context.mcps)

        # Create a ToolNode with the available tools
        tool_node = ToolNode(available_tools)

        # Execute the tool node
        result = await tool_node.ainvoke(state)

        return cast(dict[str, list[ToolMessage]], result)

    async def get_graph(self, **kwargs):
        """构建图"""
        if self.graph:
            return self.graph

        builder = StateGraph(State, context_schema=self.context_schema)
        builder.add_node("chatbot", self.llm_call)
        builder.add_node("tools", self.dynamic_tools_node)
        builder.add_edge(START, "chatbot")
        builder.add_conditional_edges(
            "chatbot",
            tools_condition,
        )
        builder.add_edge("tools", "chatbot")
        builder.add_edge("chatbot", END)

        graph = builder.compile(checkpointer=self.checkpointer, name=self.name)
        self.graph = graph
        return graph


def main():
    agent = ChatbotAgent(Context)

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    from src.agents.utils import agent_cli

    agent_cli(agent, config)


if __name__ == "__main__":
    main()
    # asyncio.run(main())
