from __future__ import annotations

import os

from typing import Type, Annotated, Optional, TypedDict
from abc import abstractmethod
from dataclasses import dataclass, fields, field

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import BaseMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph.message import add_messages

from src.config import SimpleConfig


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
class Configuration(SimpleConfig):
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
        return {f.name: getattr(cls, f.name) for f in fields(cls) if f.init}



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
        }

    def check_requirements(self):
        if not hasattr(self, "requirements") or not self.requirements:
            return
        for requirement in self.requirements:
            if requirement not in os.environ:
                raise ValueError(f"{requirement} is not set")

    def stream_values(self, messages: list[str], config_schema: RunnableConfig = None, **kwargs):
        graph = self.get_graph(config_schema=config_schema, **kwargs)
        for event in graph.stream({"messages": messages}, stream_mode="values", config=config_schema):
            yield event["messages"]

    def stream_messages(self, messages: list[str], config_schema: RunnableConfig = None, **kwargs):
        graph = self.get_graph(config_schema=config_schema, **kwargs)
        conf = self.config_schema.from_runnable_config(config_schema)
        for msg, metadata in graph.stream({"messages": messages}, stream_mode="messages", config=config_schema):
            msg_type = msg.type

            return_keys =conf.return_keys
            if not return_keys or msg_type in return_keys:
                yield msg, metadata

    @abstractmethod
    def get_graph(self, **kwargs) -> CompiledStateGraph:
        pass