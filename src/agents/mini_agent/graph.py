from langchain.agents import create_agent

from src.agents.common import BaseAgent, load_chat_model
from src.agents.common.middlewares import (
    RuntimeConfigMiddleware,
)
from src.services.mcp_service import get_tools_from_all_servers


class MiniAgent(BaseAgent):
    name = "智能体 Demo"
    description = "一个基于内置工具的智能体示例"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def get_graph(self, **kwargs):
        """构建图"""
        context = self.context_schema.from_file(module_name=self.module_name)
        all_mcp_tools = await get_tools_from_all_servers()

        graph = create_agent(
            model=load_chat_model(context.model),
            system_prompt=context.system_prompt,
            middleware=[
                RuntimeConfigMiddleware(extra_tools=all_mcp_tools),
            ],
            checkpointer=await self._get_checkpointer(),
        )

        return graph
