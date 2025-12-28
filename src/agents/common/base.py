from __future__ import annotations

import importlib.util
import os
import tomllib as tomli
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
    capabilities: list[str] = []  # 智能体能力列表，如 ["file_upload", "web_search"] 等
    context_schema: type[BaseContext] = BaseContext  # 智能体上下文 schema

    def __init__(self, **kwargs):
        self.graph = None  # will be covered by get_graph
        self.checkpointer = None
        self.workdir = Path(sys_config.save_dir) / "agents" / self.module_name
        self.workdir.mkdir(parents=True, exist_ok=True)
        self._metadata_cache = None  # Cache for metadata to avoid repeated file reads

    @property
    def module_name(self) -> str:
        """Get the module name of the agent class."""
        return self.__class__.__module__.split(".")[-2]

    @property
    def id(self) -> str:
        """Get the agent's class name."""
        return self.__class__.__name__

    async def get_info(self):
        # Load metadata from file
        metadata = self.load_metadata()

        # Merge metadata with class attributes, metadata takes precedence
        return {
            "id": self.id,
            "name": metadata.get("name", getattr(self, "name", "Unknown")),
            "description": metadata.get("description", getattr(self, "description", "Unknown")),
            "examples": metadata.get("examples", []),
            "configurable_items": self.context_schema.get_configurable_items(),
            "has_checkpointer": await self.check_checkpointer(),
            "capabilities": getattr(self, "capabilities", []),  # 智能体能力列表
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

        # 从 input_context 中提取 attachments（如果有）
        attachments = (input_context or {}).get("attachments", [])
        input_config = {"configurable": input_context, "recursion_limit": 300}

        async for msg, metadata in graph.astream(
            {"messages": messages, "attachments": attachments},
            stream_mode="messages",
            context=context,
            config=input_config,
        ):
            yield msg, metadata

    async def invoke_messages(self, messages: list[str], input_context=None, **kwargs):
        graph = await self.get_graph()
        context = self.context_schema.from_file(module_name=self.module_name, input_context=input_context)
        logger.debug(f"invoke_messages: {context}")

        # 从 input_context 中提取 attachments（如果有）
        attachments = (input_context or {}).get("attachments", [])
        input_config = {"configurable": input_context, "recursion_limit": 100}

        msg = await graph.ainvoke(
            {"messages": messages, "attachments": attachments}, context=context, config=input_config
        )
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

    def reload_graph(self):
        """重置 graph 缓存，强制下次调用 get_graph 时重新构建"""
        self.graph = None
        logger.info(f"{self.name} graph 缓存已清空，将在下次调用时重新构建")

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
        conn = await aiosqlite.connect(os.path.join(self.workdir, "aio_history.db"))
        # Patch: langgraph's AsyncSqliteSaver expects is_alive() method which aiosqlite may not have
        if not hasattr(conn, "is_alive"):
            conn.is_alive = lambda: True
        return conn

    async def get_aio_memory(self) -> AsyncSqliteSaver:
        """获取异步存储实例"""
        return AsyncSqliteSaver(await self.get_async_conn())

    def load_metadata(self) -> dict:
        """Load metadata from metadata.toml file in the agent's source directory."""
        if self._metadata_cache is not None:
            return self._metadata_cache

        # Try to find metadata.toml in the agent's source directory
        try:
            # Get the agent's source file directory
            agent_module = self.__class__.__module__

            # Use importlib to get the module's file path
            spec = importlib.util.find_spec(agent_module)
            if spec and spec.origin:
                agent_file = Path(spec.origin)
                agent_dir = agent_file.parent
            else:
                # Fallback: construct path from module name
                module_path = agent_module.replace(".", "/")
                agent_file = Path(f"src/{module_path}.py")
                agent_dir = agent_file.parent

            metadata_file = agent_dir / "metadata.toml"

            if metadata_file.exists():
                with open(metadata_file, "rb") as f:
                    metadata = tomli.load(f)
                    self._metadata_cache = metadata
                    logger.debug(f"Loaded metadata from {metadata_file}")
                    return metadata
            else:
                logger.debug(f"No metadata.toml found for {self.module_name} at {metadata_file}")
                self._metadata_cache = {}
                return {}

        except Exception as e:
            logger.error(f"Error loading metadata for {self.module_name}: {e}")
            self._metadata_cache = {}
            return {}
