from langchain.agents import create_agent

from src.agents.common import BaseAgent, load_chat_model
from src.agents.common.mcp import MCP_SERVERS
from src.agents.common.middlewares import (
    DynamicToolMiddleware,
    context_aware_prompt,
    context_based_model,
    inject_attachment_context,
)
from src.agents.common.subagents import calc_agent_tool

from .context import Context
from .tools import get_tools


class ChatbotAgent(BaseAgent):
    name = "智能体助手"
    description = "基础的对话机器人，可以回答问题，默认不使用任何工具，可在配置中启用需要的工具。"
    capabilities = ["file_upload"]  # 支持文件上传功能

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.graph = None
        self.checkpointer = None
        self.context_schema = Context

    def get_tools(self):
        """返回基本工具"""
        base_tools = get_tools()
        base_tools.append(calc_agent_tool)
        return base_tools

    async def get_graph(self, **kwargs):
        """构建图"""
        if self.graph:
            return self.graph

        # 创建动态工具中间件实例，并传入所有可用的 MCP 服务器列表
        dynamic_tool_middleware = DynamicToolMiddleware(
            base_tools=self.get_tools(), mcp_servers=list(MCP_SERVERS.keys())
        )

        # 预加载所有 MCP 工具并注册到 middleware.tools
        await dynamic_tool_middleware.initialize_mcp_tools()

        # 使用 create_agent 创建智能体，并传入 middleware
        graph = create_agent(
            model=load_chat_model("siliconflow/Qwen/Qwen3-235B-A22B-Instruct-2507"),  # 默认模型，会被 middleware 覆盖
            tools=get_tools(),  # 注册基础工具
            middleware=[
                context_aware_prompt,  # 动态系统提示词
                inject_attachment_context,  # 附件上下文注入（LangChain 标准中间件）
                context_based_model,  # 动态模型选择
                dynamic_tool_middleware,  # 动态工具选择（支持 MCP 工具注册）
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
