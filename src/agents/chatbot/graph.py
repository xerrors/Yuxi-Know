from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware

from src.agents.common import BaseAgent, load_chat_model
from src.agents.common.middlewares import (
    inject_attachment_context,
)
from src.agents.common.tools import get_tools_from_context


class ChatbotAgent(BaseAgent):
    name = "智能体助手"
    description = "基础的对话机器人，可以回答问题，可在配置中启用需要的工具。"
    capabilities = ["file_upload"]  # 支持文件上传功能

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def get_graph(self, **kwargs):
        """构建图"""
        if self.graph:
            return self.graph

        # 获取上下文配置
        context = self.context_schema.from_file(module_name=self.module_name)

        # 使用 create_agent 创建智能体
        graph = create_agent(
            model=load_chat_model(context.model),  # 使用 context 中的模型配置
            tools=await get_tools_from_context(context),
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
