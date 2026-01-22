from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware

from src.agents.common import BaseAgent, load_chat_model
from src.agents.common.middlewares import (
    RuntimeConfigMiddleware,
    inject_attachment_context,
)
from src.services.mcp_service import get_tools_from_all_servers


class ChatbotAgent(BaseAgent):
    name = "智能体助手"
    description = "基础的对话机器人，可以回答问题，可在配置中启用需要的工具。"
    capabilities = ["file_upload"]  # 支持文件上传功能

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def get_graph(self, **kwargs):
        """构建图"""
        context = self.context_schema()
        all_mcp_tools = (
            await get_tools_from_all_servers()
        )  # 因为异步加载，无法放在 RuntimeConfigMiddleware 的 __init__ 中

        # 使用 create_agent 创建智能体
        # 注意：tools 参数由 RuntimeConfigMiddleware 在 wrap_model_call 中动态设置
        graph = create_agent(
            model=load_chat_model(context.model),
            system_prompt=context.system_prompt,
            middleware=[
                inject_attachment_context,  # 附件上下文注入
                RuntimeConfigMiddleware(extra_tools=all_mcp_tools),  # 运行时配置应用（模型/工具/知识库/MCP/提示词）
                ModelRetryMiddleware(),  # 模型重试中间件
            ],
            checkpointer=await self._get_checkpointer(),
        )

        return graph


def main():
    pass


if __name__ == "__main__":
    main()
    # asyncio.run(main())
