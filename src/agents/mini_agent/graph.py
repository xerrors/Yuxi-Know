from langchain.agents import create_agent

from src import config
from src.agents.common import BaseAgent, get_buildin_tools, load_chat_model
from src.agents.common.middlewares import context_aware_prompt, context_based_model


class MiniAgent(BaseAgent):
    name = "智能体 Demo"
    description = "一个基于内置工具的智能体示例"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def get_tools(self):
        return get_buildin_tools()

    async def get_graph(self, **kwargs):
        if self.graph:
            return self.graph

        # 创建 MiniAgent
        graph = create_agent(
            model=load_chat_model(config.default_model),  # 实际会被覆盖
            tools=self.get_tools(),
            middleware=[context_aware_prompt, context_based_model],
            checkpointer=await self._get_checkpointer(),
        )

        self.graph = graph
        return graph
