import textwrap
from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, ModelResponse, dynamic_prompt, wrap_model_call

from src.agents.common.base import BaseAgent
from src.agents.common.models import load_chat_model
from src.agents.common.mcp import get_mcp_tools
from src.agents.common.toolkits.mysql import get_mysql_tools
from src.utils import logger

_mcp_servers = {
    "mcp-server-chart": {
        "url": "https://mcp.api-inference.modelscope.net/9993ae42524c4c/mcp",
        "transport": "streamable_http",
    },
}

@dynamic_prompt
def context_aware_prompt(request: ModelRequest) -> str:
    user_prompt = request.runtime.context.system_prompt
    agent_prompt = user_prompt + textwrap.dedent("""
        You are an SQL reporting assistant. Your task is to generate SQL queries based on user requests
        and provide insights from the database. Use the tools provided to you to answer the questions.
        """)

    return agent_prompt


@wrap_model_call
async def context_based_model(request: ModelRequest, handler) -> ModelResponse:
    # 从 runtime context 读取配置
    model_spec = request.runtime.context.model
    model = load_chat_model(model_spec)

    request = request.override(model=model)
    return await handler(request)


class SqlReporterAgent(BaseAgent):
    name = "SQL 报告助手"
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
            model=load_chat_model("siliconflow/Qwen/Qwen3-235B-A22B-Instruct-2507"),
            tools=await self.get_tools(),
            middleware=[context_aware_prompt, context_based_model],
            checkpointer=await self._get_checkpointer(),
        )

        self.graph = graph
        logger.info("SqlReporterAgent 构建成功")
        return graph