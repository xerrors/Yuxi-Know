from langgraph.constants import END
from langgraph.graph import StateGraph

from src.agents.common.toolagent import ToolAgent

from .context import Context
from .state import State
from .tools import get_tools


def tools_branch_continue(state: State):
    messages = state.messages
    last_message = messages[-1]
    # 如果无工具调用则结束
    if not last_message.tool_calls:
        return "end"
    else:
        return "continue"


class ReActAgent(ToolAgent):
    name = "ReActAgent"
    description = "符合 ReAct 范式的智能体，可以通过调用工具来完成复杂任务。"

    """
    提示词示例：
    你是一个智能体助手

    你的所有需要计算的工作不能自己计算，只能通过调用加密计算机工具进行,你只能通过调用该工具的方式进行计算才能得到正确答案。计算顺序是正常的。

    例如 2+3+2，你必须调用两次加密计算机工具进行运算，最终结果为9。
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
        # 创建 ReActAgent
        """构建图"""
        if self.graph:
            return self.graph

        builder = StateGraph(State, context_schema=self.context_schema)
        builder.add_node("agent", self.llm_call)
        builder.add_node("tools", self.dynamic_tools_node)
        builder.set_entry_point("agent")
        # 添加条件边：agent 决定是否调用工具继续还是结束对话
        builder.add_conditional_edges(
            "agent",
            tools_branch_continue,
            {
                "continue": "tools",  # 调用工具
                "end": END,  # 结束对话
            },
        )
        builder.add_edge("tools", "agent")
        self.checkpointer = await self._get_checkpointer()
        graph = builder.compile(checkpointer=self.checkpointer, name=self.name)
        self.graph = graph
        return graph
