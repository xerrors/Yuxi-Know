from abc import abstractmethod
from typing import Any, cast

from langchain.messages import AIMessage, ToolMessage
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime

from src.agents.common.base import BaseAgent
from src.agents.common.mcp import get_mcp_tools
from src.agents.common.models import load_chat_model
from src.utils import logger

from .state import BaseState
from .context import BaseContext

class ToolAgent(BaseAgent):
    name = "ToolAgent"
    description = "具有工具调用能力的Agent"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.graph = None
        self.checkpointer = None
        self.context_schema = BaseContext
        self.agent_tools = None


    # TODO:[修改建议] _get_invoke_tools,llm_call,dynamic_tools_node这类针对工具调用的功能大多数Agent都能用得到
    # 可以通过一个ToolAgent类继承BaseAgent,通过重写抽象方法获取tools,通过继承BaseState和BaseContext获取配置
    # 必要时可通过重写以下方法实现其他逻辑
    @abstractmethod
    def get_tools(self):
        logger.error(f"get_tools() is not implemented in {self.__class__.__name__}")
        return []


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

    async def llm_call(self, state: BaseState, runtime: Runtime[BaseContext] = None) -> dict[str, Any]:
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

    async def dynamic_tools_node(self, state: BaseState, runtime: Runtime[BaseContext]) -> dict[str, list[ToolMessage]]:
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
