from dataclasses import dataclass, field
from typing import Annotated

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware

from src.agents.common import BaseAgent, BaseContext, load_chat_model
from src.agents.common.middlewares import (
    RuntimeConfigMiddleware,
)
from src.agents.common.toolkits.mysql import get_mysql_tools
from src.agents.common.tools import gen_tool_info, get_buildin_tools
from src.services.mcp_service import get_tools_from_all_servers
from src.utils import logger


@dataclass(kw_only=True)
class ReporterContext(BaseContext):
    # 覆盖默认的工具列表，添加 MySQL 工具包
    tools: Annotated[list[dict], {"__template_metadata__": {"kind": "tools"}}] = field(
        default_factory=lambda: [t.name for t in get_mysql_tools()],
        metadata={
            "name": "工具",
            # 添加额外的 MySQL 工具包选项
            "options": lambda: gen_tool_info(get_buildin_tools() + get_mysql_tools()),
            "description": "包含内置的工具，以及用于数据库报表生成的 MySQL 工具包。",
        },
    )

    def __post_init__(self):
        self.mcps = ["mcp-server-chart"]  # 默认启用 Charts MCPs


class SqlReporterAgent(BaseAgent):
    name = "数据库报表助手"
    description = "一个能够生成 SQL 查询报告的智能体助手。同时调用 Charts MCP 生成图表。"
    context_schema = ReporterContext

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def get_graph(self, **kwargs):
        """构建图"""
        context = self.context_schema.from_file(module_name=self.module_name)
        all_mcp_tools = await get_tools_from_all_servers()
        # 合并 MySQL 工具和 MCP 工具
        extra_tools = get_mysql_tools() + all_mcp_tools

        graph = create_agent(
            model=load_chat_model(context.model),
            system_prompt=context.system_prompt,
            middleware=[
                RuntimeConfigMiddleware(extra_tools=extra_tools),
            ],
            checkpointer=await self._get_checkpointer(),
        )

        logger.info("SqlReporterAgent 构建成功")
        return graph
