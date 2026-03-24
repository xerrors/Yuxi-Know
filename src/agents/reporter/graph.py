from dataclasses import dataclass, field
from typing import Annotated

from deepagents.middleware.filesystem import FilesystemMiddleware
from langchain.agents import create_agent

from src.agents.common import BaseAgent, BaseContext, load_chat_model
from src.agents.common.backends import create_agent_composite_backend
from src.agents.common.middlewares import RuntimeConfigMiddleware, save_attachments_to_fs
from src.agents.common.toolkits.mysql import get_mysql_tools
from src.services.mcp_service import get_mcp_server_names, get_tools_from_all_servers
from src.utils import logger


def _create_fs_backend(rt):
    return create_agent_composite_backend(rt)


PROMPT = """你的任务是根据用户指令，使用数据库工具和图表工具生成 SQL 报告。
请先理解需求，再给出准确且高效的 SQL 查询；必要时调用图表工具并在最终回答中以 Markdown 图片形式展示结果。
"""


@dataclass(kw_only=True)
class ReporterContext(BaseContext):
    system_prompt: Annotated[str, {"__template_metadata__": {"kind": "prompt"}}] = field(
        default=PROMPT,
        metadata={"name": "系统提示词", "description": "描述 SQL 报告助手的行为"},
    )
    mcps: Annotated[list[str], {"__template_metadata__": {"kind": "mcps"}}] = field(
        default_factory=lambda: ["mcp-server-chart"],
        metadata={
            "name": "MCP 服务",
            "options": lambda: get_mcp_server_names(),
            "description": "报告场景默认启用图表 MCP。",
        },
    )


class SqlReporterAgent(BaseAgent):
    name = "数据报表助手"
    description = "根据用户需求生成 SQL 查询并输出图表化报告。"
    context_schema = ReporterContext
    capabilities = ["file_upload", "files"]

    async def get_graph(self, **kwargs):
        context = self.context_schema.from_file(module_name=self.module_name)
        all_mcp_tools = await get_tools_from_all_servers()
        graph = create_agent(
            model=load_chat_model(context.model),
            system_prompt=context.system_prompt,
            tools=get_mysql_tools(),
            middleware=[
                FilesystemMiddleware(backend=_create_fs_backend),
                RuntimeConfigMiddleware(extra_tools=all_mcp_tools),
                save_attachments_to_fs,
            ],
            checkpointer=await self._get_checkpointer(),
        )
        logger.info("SqlReporterAgent graph created")
        return graph
