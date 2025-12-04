from langchain.agents import create_agent

from src import config
from src.agents.common import BaseAgent, get_mcp_tools, load_chat_model
from src.agents.common.middlewares import context_aware_prompt, context_based_model
from src.agents.common.toolkits.mysql import get_mysql_tools
from src.utils import logger

_mcp_servers = {"mcp-server-chart": {"command": "npx", "args": ["-y", "@antv/mcp-server-chart"], "transport": "stdio"}}


class SqlReporterAgent(BaseAgent):
    name = "数据库报表助手"
    description = "一个能够生成 SQL 查询报告的智能体助手。同时调用 Charts MCP 生成图表。"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def get_tools(self):
        chart_tools = await get_mcp_tools("mcp-server-chart", additional_servers=_mcp_servers)
        mysql_tools = get_mysql_tools()
        return chart_tools + mysql_tools

    async def get_graph(self, **kwargs):
        if self.graph:
            return self.graph

        # 创建 SqlReporterAgent
        graph = create_agent(
            model=load_chat_model(config.default_model),  # 默认模型，会被 middleware 覆盖
            tools=await self.get_tools(),
            middleware=[context_aware_prompt, context_based_model],
            checkpointer=await self._get_checkpointer(),
        )

        self.graph = graph
        logger.info("SqlReporterAgent 构建成功")
        return graph
