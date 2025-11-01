from __future__ import annotations

import os
from abc import abstractmethod
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver, aiosqlite
from langgraph.graph.state import CompiledStateGraph

from src import config as sys_config
from src.agents.common.context import BaseContext
from src.utils import logger


class BaseAgent:
    """
    定义一个基础 Agent 供 各类 graph 继承
    """

    name = "base_agent"
    description = "base_agent"

    def __init__(self, **kwargs):
        self.graph = None  # will be covered by get_graph
        self.checkpointer = None
        self.context_schema = BaseContext
        self.workdir = Path(sys_config.save_dir) / "agents" / self.module_name
        self.workdir.mkdir(parents=True, exist_ok=True)

    @property
    def module_name(self) -> str:
        """Get the module name of the agent class."""
        return self.__class__.__module__.split(".")[-2]

    @property
    def id(self) -> str:
        """Get the agent's class name."""
        return self.__class__.__name__

    async def get_info(self):
        return {
            "id": self.id,
            "name": self.name if hasattr(self, "name") else "Unknown",
            "description": self.description if hasattr(self, "description") else "Unknown",
            "configurable_items": self.context_schema.get_configurable_items(),
            "has_checkpointer": await self.check_checkpointer(),
        }

    async def get_config(self):
        return self.context_schema.from_file(module_name=self.module_name)

    async def stream_values(self, messages: list[str], input_context=None, **kwargs):
        graph = await self.get_graph()
        context = self.context_schema.from_file(module_name=self.module_name, input_context=input_context)
        for event in graph.astream({"messages": messages}, stream_mode="values", context=context):
            yield event["messages"]

    async def stream_messages(self, messages: list[str], input_context=None, **kwargs):
        graph = await self.get_graph()
        context = self.context_schema.from_file(module_name=self.module_name, input_context=input_context)
        logger.debug(f"stream_messages: {context}")
        # TODO Checkpointer 似乎还没有适配最新的 1.0 Context API
        input_config = {"configurable": input_context, "recursion_limit": 100}
        async for msg, metadata in graph.astream(
            {"messages": messages}, stream_mode="messages", context=context, config=input_config
        ):
            yield msg, metadata

    async def invoke_messages(self, messages: list[str], input_context=None, **kwargs):
        graph = await self.get_graph()
        context = self.context_schema.from_file(module_name=self.module_name, input_context=input_context)
        logger.debug(f"invoke_messages: {context}")
        input_config = {"configurable": input_context, "recursion_limit": 100}
        msg = await graph.ainvoke({"messages": messages}, context=context, config=input_config)
        return msg

    async def check_checkpointer(self):
        app = await self.get_graph()
        if not hasattr(app, "checkpointer") or app.checkpointer is None:
            logger.warning(f"智能体 {self.name} 的 Graph 未配置 checkpointer，无法获取历史记录")
            return False
        return True

    async def get_history(self, user_id, thread_id) -> list[dict]:
        """获取历史消息"""
        try:
            app = await self.get_graph()

            if not await self.check_checkpointer():
                return []

            config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}
            state = await app.aget_state(config)

            result = []
            if state:
                messages = state.values.get("messages", [])
                for msg in messages:
                    if hasattr(msg, "model_dump"):
                        msg_dict = msg.model_dump()  # 转换成字典
                    else:
                        msg_dict = dict(msg) if hasattr(msg, "__dict__") else {"content": str(msg)}
                    result.append(msg_dict)

            return result

        except Exception as e:
            logger.error(f"获取智能体 {self.name} 历史消息出错: {e}")
            return []

    @abstractmethod
    async def get_graph(self, **kwargs) -> CompiledStateGraph:
        """
        获取并编译对话图实例。
        必须确保在编译时设置 checkpointer，否则将无法获取历史记录。
        例如: graph = workflow.compile(checkpointer=sqlite_checkpointer)
        """
        pass

    async def _get_checkpointer(self):
        # 创建数据库连接并确保设置 checkpointer
        checkpointer = None

        try:
            checkpointer = AsyncSqliteSaver(await self.get_async_conn())

        except Exception as e:
            logger.error(f"构建 Graph 设置 checkpointer 时出错: {e}, 尝试使用内存存储")
            checkpointer = InMemorySaver()

        return checkpointer

    async def get_async_conn(self) -> aiosqlite.Connection:
        """获取异步数据库连接"""
        return await aiosqlite.connect(os.path.join(self.workdir, "aio_history.db"))

    async def get_aio_memory(self) -> AsyncSqliteSaver:
        """获取异步存储实例"""
        return AsyncSqliteSaver(await self.get_async_conn())
