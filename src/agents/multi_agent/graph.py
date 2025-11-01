from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import tools_condition

from src.agents.common.toolagent import ToolAgent

from .context import Context
from .state import State
from .tools import get_tools


class SampleMultiAgent(ToolAgent):
    name = "MultiAgent智能体"
    description = "Supervisor智能体，具有调用其他子智能体的能力(在工具中添加)"

    # TODO[已完成]: 通过将其他agent封装为工具的方式添加了多智能体调度
    """
    你是一个多智能体核心，通过多智能体调用的方式帮助用户完成一系列任务：

    1.当你需要知识库问答功能时，请调用对话聊天智能体实现
    2.当你需要加密计算的时候，请调用加密计算智能体实现
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.graph = None
        self.checkpointer = None
        self.context_schema = Context
        self.agent_tools = None

    def get_tools(self):
        return get_tools()

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

        self.checkpointer = await self._get_checkpointer()
        graph = builder.compile(checkpointer=self.checkpointer, name=self.name)
        self.graph = graph
        return graph


def main():
    pass


if __name__ == "__main__":
    main()
    # asyncio.run(main())
