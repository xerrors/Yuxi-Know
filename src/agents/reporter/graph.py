from dataclasses import dataclass, field
from typing import Annotated

from langchain.agents import create_agent

from src.agents.common import BaseAgent, BaseContext, load_chat_model
from src.agents.common.middlewares import (
    RuntimeConfigMiddleware,
)
from src.agents.common.toolkits.mysql import get_mysql_tools
from src.services.mcp_service import get_mcp_server_names, get_tools_from_all_servers
from src.utils import logger


@dataclass(kw_only=True)
class ReporterContext(BaseContext):
    """覆盖 BaseContext，定义数据库报表助手智能体的可配置参数"""

    mcps: Annotated[list[str], {"__template_metadata__": {"kind": "mcps"}}] = field(
        default_factory=lambda: ["mcp-server-chart"],
        metadata={
            "name": "MCP服务器",
            "options": lambda: get_mcp_server_names(),
            "description": (
                "MCP服务器列表，建议使用支持 SSE 的 MCP 服务器，"
                "如果需要使用 uvx 或 npx 运行的服务器，也请在项目外部启动 MCP 服务器，并在项目中配置 MCP 服务器。"
            ),
        },
    )


class SqlReporterAgent(BaseAgent):
    name = "数据库报表助手"
    description = (
        "一个能够生成 SQL 查询报告的智能体助手。同时调用 Charts MCP 生成图表。"
        "MySQL 工具默认启用，无法选择，mcp 默认启用 Charts MCPs。"
    )
    context_schema = ReporterContext

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def get_graph(self, **kwargs):
        """构建图"""
        context = self.context_schema.from_file(module_name=self.module_name)
        all_mcp_tools = await get_tools_from_all_servers()

        graph = create_agent(
            model=load_chat_model(context.model),
            system_prompt=context.system_prompt,
            tools=get_mysql_tools(),  # MySQL 工具默认启用，这里添加的 tools，不会在工具选择框中出现
            middleware=[
                RuntimeConfigMiddleware(extra_tools=all_mcp_tools),
            ],
            checkpointer=await self._get_checkpointer(),
        )

        logger.info("SqlReporterAgent 构建成功")
        return graph
