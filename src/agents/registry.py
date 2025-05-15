from __future__ import annotations

import os
import yaml
from pathlib import Path
from typing import Type, Annotated, Optional, TypedDict
from enum import Enum
from abc import abstractmethod
from dataclasses import dataclass, fields, field

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import BaseMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph.message import add_messages

from src.utils import logger

class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


@dataclass(kw_only=True)
class Configuration(dict):
    """
    定义一个基础 Configuration 供 各类 graph 继承

    配置优先级:
    1. 运行时配置(RunnableConfig)：最高优先级，直接从函数参数传入
    2. 文件配置(config.private.yaml)：中等优先级，从文件加载
    3. 类默认配置：最低优先级，类中定义的默认值
    """

    @classmethod
    def from_runnable_config(
        cls, config: Optional[RunnableConfig] = None, agent_name: str = None
    ) -> Configuration:
        """Create a Configuration instance from a RunnableConfig object.

        Args:
            config: RunnableConfig object with highest priority
            agent_name: Name of the agent to load config file for

        Returns:
            Configuration instance with merged config values
        """
        # 获取类默认配置：创建一个实例获取所有默认值
        instance = cls()
        _fields = {f.name for f in fields(cls) if f.init}

        # 尝试加载文件配置(中等优先级)
        file_config = {}
        if agent_name:
            file_config = cls.from_file(agent_name)

        # 获取运行时配置(最高优先级)
        configurable = (config.get("configurable") or {}) if config else {}

        # 合并三级配置，注意优先级
        merged_config = {}
        for field in _fields:
            # 1. 默认使用类默认值
            if hasattr(instance, field):
                merged_config[field] = getattr(instance, field)

            # 2. 如果文件配置中有此字段，则覆盖
            if field in file_config:
                merged_config[field] = file_config[field]

            # 3. 如果运行时配置中有此字段，则覆盖
            if field in configurable:
                merged_config[field] = configurable[field]

        # 创建并返回配置实例
        # logger.debug(f"合并配置: {merged_config}")
        return cls(**merged_config)

    @classmethod
    def from_file(cls, agent_name: str) -> Configuration:
        """从文件加载配置"""
        config_file_path = Path(f"src/agents/{agent_name}/config.private.yaml")
        file_config = {}
        if os.path.exists(config_file_path):
            try:
                with open(config_file_path, 'r', encoding='utf-8') as f:
                    file_config = yaml.safe_load(f) or {}
                    # logger.info(f"从文件加载智能体 {agent_name} 配置: {file_config}")
            except Exception as e:
                logger.error(f"加载智能体配置文件出错: {e}")

        return file_config

    @classmethod
    def save_to_file(cls, config: dict, agent_name: str) -> bool:
        """Save configuration to a YAML file

        Args:
            config: Configuration dictionary to save
            agent_name: Name of the agent to save config for

        Returns:
            True if saving was successful, False otherwise
        """
        try:
            config_file_path = Path(f"src/agents/{agent_name}/config.private.yaml")
            # 确保目录存在
            os.makedirs(os.path.dirname(config_file_path), exist_ok=True)
            with open(config_file_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, indent=2, allow_unicode=True)

            # logger.info(f"智能体 {agent_name} 配置已保存到 {config_file_path}")
            return True
        except Exception as e:
            logger.error(f"保存智能体配置文件出错: {e}")
            return False

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
        logger.debug(f"stream_values: {config_schema}")
        for event in graph.stream({"messages": messages}, stream_mode="values", config=config_schema):
            yield event["messages"]

    def stream_messages(self, messages: list[str], config_schema: RunnableConfig = None, **kwargs):
        graph = self.get_graph(config_schema=config_schema, **kwargs)
        logger.debug(f"stream_messages: {config_schema}")

        for msg, metadata in graph.stream({"messages": messages}, stream_mode="messages", config=config_schema):
            yield msg, metadata

    def get_history(self, user_id, thread_id) -> list[dict]:
        """获取历史消息"""
        # 获取LangGraph应用实例
        app = self.get_graph()
        # 构建配置信息
        config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}
        # 获取状态
        state = app.get_state(config)
        # logger.debug(f"获取历史消息: {state}")

        result = []
        if state:
            messages = state.values.get('messages', [])
            for msg in messages:
                if hasattr(msg, 'model_dump'):
                    msg_dict = msg.model_dump()  # 转换成字典
                else:
                    # 如果消息没有model_dump方法，尝试转成dict
                    msg_dict = dict(msg) if hasattr(msg, '__dict__') else {"content": str(msg)}
                result.append(msg_dict)

        return result

    @abstractmethod
    def get_graph(self, **kwargs) -> CompiledStateGraph:
        pass