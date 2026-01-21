from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware

from src.agents.common import BaseAgent, load_chat_model
from src.agents.common.middlewares import (
    RuntimeConfigMiddleware,
    inject_attachment_context,
)
from src.agents.common.tools import get_buildin_tools


class ChatbotAgent(BaseAgent):
    name = "智能体助手"
    description = "基础的对话机器人，可以回答问题，可在配置中启用需要的工具。"
    capabilities = ["file_upload"]  # 支持文件上传功能

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def get_graph(self, **kwargs):
        """构建图"""
        context = self.context_schema()

        # 使用 create_agent 创建智能体
        graph = create_agent(
            model=load_chat_model(context.model),
            tools=get_buildin_tools(),
            system_prompt=context.system_prompt,
            middleware=[
                inject_attachment_context,  # 附件上下文注入
                RuntimeConfigMiddleware(),  # 运行时配置应用（模型/工具/知识库/MCP/提示词）
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
