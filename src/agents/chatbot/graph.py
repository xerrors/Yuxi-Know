from deepagents.backends import CompositeBackend, StateBackend
from deepagents.middleware.filesystem import FilesystemMiddleware
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware

from src.agents.common import BaseAgent, load_chat_model
from src.agents.common.backends.minio_backend import MinIOBackend
from src.agents.common.middlewares import (
    RuntimeConfigMiddleware,
    save_attachments_to_fs,
)
from src.services.mcp_service import get_tools_from_all_servers


def _create_fs_backend_factory(rt) -> CompositeBackend:
    """创建混合文件存储后端工厂函数（供 FilesystemMiddleware 使用）。

    /attachments/* 路由到 MinIO（供附件中间件使用）
    其他路径使用 StateBackend（内存存储，用于临时文件和大结果卸载）

    注意：rt (runtime) 由 FilesystemMiddleware 在初始化时自动传入。
    """
    return CompositeBackend(
        default=StateBackend(rt),  # 传入 runtime
        routes={
            "/attachments/": MinIOBackend(bucket_name="chat-attachments"),
        },
    )


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
                save_attachments_to_fs,  # 附件保存到文件系统
                FilesystemMiddleware(backend=_create_fs_backend_factory, tool_token_limit_before_evict=5000),
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
