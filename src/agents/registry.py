from __future__ import annotations

import os

from typing import Type, Annotated, Optional, TypedDict
from enum import Enum
from abc import abstractmethod
from dataclasses import dataclass, fields, field

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import BaseMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph.message import add_messages

from src.config import SimpleConfig
from src.utils import logger

class State(TypedDict):
    """
    定义一个基础 State 供 各类 graph 继承, 其中:
    1. messages 为所有 graph 的核心信息队列, 所有聊天工作流均应该将关键信息补充到此队列中;
    2. history 为所有工作流单次启动时获取 history_len 的 messages 所用(节约成本, 及防止单轮对话 tokens 占用长度达到 llm 支持上限),
    history 中的信息理应是可以被丢弃的.
    """
    messages: Annotated[list[BaseMessage], add_messages]
    history: Optional[list[BaseMessage]]


@dataclass(kw_only=True)
class Configuration(dict):
    """
    定义一个基础 Configuration 供 各类 graph 继承
    """

    @classmethod
    def from_runnable_config(
        cls, config: Optional[RunnableConfig] = None
    ) -> Configuration:
        """Create a Configuration instance from a RunnableConfig object."""
        configurable = (config.get("configurable") or {}) if config else {}
        _fields = {f.name for f in fields(cls) if f.init}
        return cls(**{k: v for k, v in configurable.items() if k in _fields})

    @classmethod
    def to_dict(cls):
        # 创建一个实例来处理 default_factory
        instance = cls()
        confs = {}
        configurable_items = {}
        for f in fields(cls):
            if f.init and not f.metadata.get("hide", False):
                value = getattr(instance, f.name)
                if callable(value) and hasattr(value, "__call__"):
                    confs[f.name] = value()
                else:
                    confs[f.name] = value

                if f.metadata.get("configurable"):
                    configurable_items[f.name] = {
                        "type": f.type.__name__,
                        "name": f.metadata.get("name", f.name),
                        "options": f.metadata.get("options", []),
                        "default": f.default,
                        "description": f.metadata.get("description", ""),
                    }
        confs["configurable_items"] = configurable_items
        return confs



class BaseAgent():

    """
    定义一个基础 Agent 供 各类 graph 继承
    """

    name: str = field(default="base_agent")
    description: str = field(default="base_agent")
    config_schema: Configuration = Configuration
    requirements: list[str]

    def __init__(self, **kwargs):
        self.check_requirements()

    @classmethod
    def get_info(cls):
        return {
            "name": cls.name,
            "description": cls.description,
            "config_schema": cls.config_schema.to_dict(),
            "requirements": cls.requirements if hasattr(cls, "requirements") else [],
            "all_tools": cls.all_tools if hasattr(cls, "all_tools") else [],
        }

    def check_requirements(self):
        if not hasattr(self, "requirements") or not self.requirements:
            return
        for requirement in self.requirements:
            if requirement not in os.environ:
                raise ValueError(f"没有配置{requirement} 环境变量，请在 src/.env 文件中配置，并重新启动服务")

    def stream_values(self, messages: list[str], config_schema: RunnableConfig = None, **kwargs):
        graph = self.get_graph(config_schema=config_schema, **kwargs)
        for event in graph.stream({"messages": messages}, stream_mode="values", config=config_schema):
            yield event["messages"]

    def stream_messages(self, messages: list[str], config_schema: RunnableConfig = None, **kwargs):
        graph = self.get_graph(config_schema=config_schema, **kwargs)

        for msg, metadata in graph.stream({"messages": messages}, stream_mode="messages", config=config_schema):
            yield msg, metadata

    @abstractmethod
    def get_graph(self, **kwargs) -> CompiledStateGraph:
        pass