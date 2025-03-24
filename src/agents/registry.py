from typing import Type, Annotated, Optional, TypedDict
from abc import abstractmethod

from langchain_openai import ChatOpenAI

from langchain_core.messages import BaseMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph.message import add_messages


from dataclasses import dataclass
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
class Configuration:
    """
    定义一个基础 Configuration 供 各类 graph 继承
    """
    pass



class BaseAgent():

    def __init__(self, configuration: Configuration):
        self.configuration = configuration

    @abstractmethod
    def get_graph(self) -> CompiledStateGraph:
        pass