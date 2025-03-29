from __future__ import annotations

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

    def __init__(self, **kwargs):
        pass

    @abstractmethod
    def get_graph(self) -> CompiledStateGraph:
        pass