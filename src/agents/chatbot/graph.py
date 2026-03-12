from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelRetryMiddleware,
    TodoListMiddleware,
)

from src.agents.common import BaseAgent, load_chat_model
from src.agents.common.backends import create_agent_composite_backend
from src.agents.common.middlewares import (
    RuntimeConfigMiddleware,
    save_attachments_to_fs,
)
from src.agents.common.middlewares.knowledge_base_middleware import KnowledgeBaseMiddleware
from src.agents.common.middlewares.skills_middleware import SkillsMiddleware
from src.sandbox.middleware import SandboxMiddleware
from src.services.mcp_service import get_tools_from_all_servers


def _create_fs_backend(rt):
    """创建文件存储后端"""
    return create_agent_composite_backend(rt)


class ChatbotAgent(BaseAgent):
    name = "智能体助手"
    description = "基础的对话机器人，可以回答问题，可在配置中启用需要的工具。"
    capabilities = ["file_upload", "files", "todo"]  # 支持文件上传功能

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
            model=load_chat_model(fully_specified_name=context.model),
            system_prompt=context.system_prompt,
            middleware=[
                save_attachments_to_fs,  # 附件注入提示词
                FilesystemMiddleware(backend=_create_fs_backend),  # 文件系统后端
                KnowledgeBaseMiddleware(),  # 知识库工具
                SandboxMiddleware(), # 沙盒引擎上下文分配
                RuntimeConfigMiddleware(extra_tools=all_mcp_tools),  # 运行时配置应用（模型/工具/MCP/提示词）
                SkillsMiddleware(),  # Skills 中间件（提示词注入、依赖展开、动态激活）
                ModelRetryMiddleware(),  # 模型重试中间件
                TodoListMiddleware(),
                PatchToolCallsMiddleware(),
            ],
            checkpointer=await self._get_checkpointer(),
        )

        return graph


def main():
    pass


if __name__ == "__main__":
    main()
    # asyncio.run(main())
