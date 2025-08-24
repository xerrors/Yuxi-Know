import os
import uuid
from typing import Any
from pathlib import Path
from datetime import datetime, timezone

import sqlite3
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver, aiosqlite

from src import config as sys_config
from src.utils import logger
from src.agents.registry import State, BaseAgent
from src.agents.utils import load_chat_model, get_cur_time_with_utc
from src.agents.chatbot.configuration import ChatbotConfiguration
from src.agents.tools_factory import get_buildin_tools

class ChatbotAgent(BaseAgent):
    name = "智能体助手"
    description = "基础的对话机器人，可以回答问题，默认不使用任何工具，可在配置中启用需要的工具。"
    config_schema = ChatbotConfiguration

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.graph = None
        self.workdir = Path(sys_config.save_dir) / "agents" / self.id
        self.workdir.mkdir(parents=True, exist_ok=True)

    def _get_tools(self, tools: list[str]):
        """根据配置获取工具。
        默认不使用任何工具。
        如果配置为列表，则使用列表中的工具。
        """
        platform_tools = get_buildin_tools()
        if tools is None or not isinstance(tools, list) or len(tools) == 0:
            # 默认不使用任何工具
            logger.info("未配置工具或配置为空，不使用任何工具")
            return []
        else:
            # 使用配置中指定的工具
            tool_names = [tool for tool in platform_tools.keys() if tool in tools]
            logger.info(f"使用工具: {tool_names}")
            return [platform_tools[tool] for tool in tool_names]

    async def llm_call(self, state: State, config: RunnableConfig = None) -> dict[str, Any]:
        """调用 llm 模型 - 异步版本以支持异步工具"""
        conf = self.config_schema.from_runnable_config(config, module_name=self.module_name)

        system_prompt = f"{conf.system_prompt} Now is {get_cur_time_with_utc()}"
        model = load_chat_model(conf.model)

        if tools := self._get_tools(conf.tools):
            model = model.bind_tools(tools)

        # 使用异步调用
        res = await model.ainvoke(
            [{"role": "system", "content": system_prompt}, *state["messages"]]
        )
        return {"messages": [res]}

    async def get_graph(self, config_schema: RunnableConfig = None, **kwargs):
        """构建图"""
        if self.graph:
            return self.graph

        runnable_tools = get_buildin_tools()
        tools = list(runnable_tools.values())
        tools_name = list(runnable_tools.keys())
        logger.debug(f"build graph `{self.id}` with tools: {tools_name}")

        workflow = StateGraph(State, config_schema=self.config_schema)
        workflow.add_node("chatbot", self.llm_call)
        workflow.add_node("tools", ToolNode(tools=tools))
        workflow.add_edge(START, "chatbot")
        workflow.add_conditional_edges(
            "chatbot",
            tools_condition,
        )
        workflow.add_edge("tools", "chatbot")
        workflow.add_edge("chatbot", END)

        # 创建数据库连接并确保设置 checkpointer
        try:
            sqlite_checkpointer = AsyncSqliteSaver(await self.get_async_conn())
            graph = workflow.compile(checkpointer=sqlite_checkpointer)
            self.graph = graph
            return graph
        except Exception as e:
            logger.error(f"构建 Graph 设置 checkpointer 时出错: {e}")
            # 即使出错也返回一个可用的图实例，只是无法保存历史
            graph = workflow.compile()
            self.graph = graph
            return graph

    async def get_async_conn(self) -> aiosqlite.Connection:
        """获取异步数据库连接"""
        return await aiosqlite.connect(os.path.join(self.workdir, "aio_history.db"))

    async def get_aio_memory(self) -> AsyncSqliteSaver:
        """获取异步存储实例"""
        return AsyncSqliteSaver(await self.get_async_conn())

def main():
    agent = ChatbotAgent(ChatbotConfiguration())

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    from src.agents.utils import agent_cli
    agent_cli(agent, config)


if __name__ == "__main__":
    main()
    # asyncio.run(main())
