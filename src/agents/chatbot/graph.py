from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware

from src.agents.common import BaseAgent, load_chat_model
from src.agents.common.mcp import get_mcp_tools
from src.agents.common.middlewares import (
    inject_attachment_context,
)
from src.agents.common.tools import get_kb_based_tools

from .context import Context
from .tools import get_tools


class ChatbotAgent(BaseAgent):
    name = "智能体助手"
    description = "基础的对话机器人，可以回答问题，默认不使用任何工具，可在配置中启用需要的工具。"
    capabilities = ["file_upload"]  # 支持文件上传功能

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.context_schema = Context

    async def get_tools(self, tools: list[str] = None, mcps=None, knowledges=None):
        # 1. 基础工具 (从 context.tools 中筛选)
        all_basic_tools = get_tools()
        selected_tools = []

        if tools:
            # 创建工具映射表
            tools_map = {t.name: t for t in all_basic_tools}
            for tool_name in tools:
                if tool_name in tools_map:
                    selected_tools.append(tools_map[tool_name])

        # 2. 知识库工具
        if knowledges:
            kb_tools = get_kb_based_tools(db_names=knowledges)
            selected_tools.extend(kb_tools)

        # 3. MCP 工具
        if mcps:
            for server_name in mcps:
                mcp_tools = await get_mcp_tools(server_name)
                selected_tools.extend(mcp_tools)

        return selected_tools

    async def get_graph(self, **kwargs):
        """构建图"""
        if self.graph:
            return self.graph

        # 获取上下文配置
        context = self.context_schema.from_file(module_name=self.module_name)

        # 使用 create_agent 创建智能体
        graph = create_agent(
            model=load_chat_model(context.model),  # 使用 context 中的模型配置
            tools=await self.get_tools(context.tools, context.mcps, context.knowledges),
            system_prompt=context.system_prompt,
            middleware=[
                inject_attachment_context,  # 附件上下文注入
                ModelRetryMiddleware(),  # 模型重试中间件
            ],
            checkpointer=await self._get_checkpointer(),
        )

        self.graph = graph
        return graph


def main():
    pass


if __name__ == "__main__":
    main()
    # asyncio.run(main())
