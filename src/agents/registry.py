from __future__ import annotations

import os
import yaml
import uuid
from pathlib import Path
from typing import Annotated, TypedDict, Optional, Any
from abc import abstractmethod
from dataclasses import dataclass, fields, field

from pydantic import BaseModel, Field
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

    thread_id: str = field(
        default_factory=lambda: str(uuid.uuid4()),
        metadata={
            "name": "线程ID",
            "configurable": False,
            "description": "用来描述智能体的角色和行为"
        },
    )

    user_id: str = field(
        default_factory=lambda: str(uuid.uuid4()),
        metadata={
            "name": "用户ID",
            "configurable": False,
            "description": "用来描述智能体的角色和行为"
        },
    )

    @classmethod
    def from_runnable_config(
        cls, config: RunnableConfig | None = None, module_name: str | None = None
    ) -> Configuration:
        """Create a Configuration instance from a RunnableConfig object.

        Args:
            config: RunnableConfig object with highest priority
            module_name: Name of the agent to load config file for

        Returns:
            Configuration instance with merged config values
        """
        # 获取类默认配置：创建一个实例获取所有默认值
        instance = cls()
        _fields = {f.name for f in fields(cls) if f.init}

        # 尝试加载文件配置(中等优先级)
        file_config = {}
        if module_name:
            file_config = cls.from_file(module_name)

        # 获取运行时配置(最高优先级)
        configurable = (config.get("configurable") or {}) if config else {}

        # 合并三级配置，注意优先级
        merged_config = {}
        for config_field in _fields:
            # 1. 默认使用类默认值
            if hasattr(instance, config_field):
                merged_config[config_field] = getattr(instance, config_field)

            # 2. 如果文件配置中有此字段，则覆盖
            if config_field in file_config:
                merged_config[config_field] = file_config[config_field]

            # 3. 如果运行时配置中有此字段，则覆盖
            if config_field in configurable:
                merged_config[config_field] = configurable[config_field]

        # 创建并返回配置实例
        # logger.debug(f"合并配置: {merged_config}")
        return cls(**merged_config)

    @classmethod
    def from_file(cls, module_name: str) -> Configuration:
        """从文件加载配置"""
        config_file_path = Path(f"src/agents/{module_name}/config.private.yaml")
        file_config = {}
        if os.path.exists(config_file_path):
            try:
                with open(config_file_path, encoding='utf-8') as f:
                    file_config = yaml.safe_load(f) or {}
                    # logger.info(f"从文件加载智能体 {module_name} 配置: {file_config}")
            except Exception as e:
                logger.error(f"加载智能体配置文件出错: {e}")

        return file_config

    @classmethod
    def save_to_file(cls, config: dict, module_name: str) -> bool:
        """Save configuration to a YAML file

        Args:
            config: Configuration dictionary to save
            module_name: Name of the agent to save config for

        Returns:
            True if saving was successful, False otherwise
        """
        try:
            config_file_path = Path(f"src/agents/{module_name}/config.private.yaml")
            # 确保目录存在
            os.makedirs(os.path.dirname(config_file_path), exist_ok=True)
            with open(config_file_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, indent=2, allow_unicode=True)

            # logger.info(f"智能体 {module_name} 配置已保存到 {config_file_path}")
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

                if f.metadata.get("configurable", True):
                    configurable_items[f.name] = {
                        "type": f.type.__name__,
                        "name": f.metadata.get("name", f.name),
                        "options": f.metadata.get("options", []),
                        "default": f.default,
                        "description": f.metadata.get("description", ""),
                    }
        confs["configurable_items"] = configurable_items
        return confs



class BaseModelConfiguration(BaseModel):

    thread_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        metadata={
            "title": "线程ID",
            "description": "用来描述智能体的角色和行为",
            "configurable": False,
        },
    )

    user_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        metadata={
            "title": "用户ID",
            "description": "用来描述智能体的角色和行为",
            "configurable": False,
        },
    )

    @classmethod
    def from_runnable_config(
        cls,
        config: RunnableConfig | None = None,
        module_name: str | None = None,
    ) -> BaseModelConfiguration:
        """
        从 RunnableConfig 和 YAML 文件中构建 Configuration 实例
        """
        # 默认配置
        default_instance = cls()
        default_values = default_instance.dict()

        # 文件配置
        file_config = cls.from_file(module_name) if module_name else {}

        # 运行时配置（最高优先级）
        runtime_config = config.get("configurable") if config else {}

        merged_config = {
            **default_values,
            **file_config,
            **runtime_config,
        }

        return cls(**merged_config)

    @classmethod
    def from_file(cls, module_name: str) -> dict[str, Any]:
        """
        从 YAML 文件加载配置
        """
        config_file_path = Path(f"src/agents/{module_name}/config.private.yaml")
        if os.path.exists(config_file_path):
            try:
                with open(config_file_path, encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"加载配置文件失败: {e}")
        return {}

    @classmethod
    def save_to_file(cls, config: dict, module_name: str) -> bool:
        """
        保存配置到 YAML 文件
        """
        try:
            config_file_path = Path(f"src/agents/{module_name}/config.private.yaml")
            os.makedirs(config_file_path.parent, exist_ok=True)
            with open(config_file_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f, indent=2, allow_unicode=True)
            return True
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            return False

    @classmethod
    def to_dict(cls) -> dict[str, Any]:
        """
        提取类字段的默认值与字段元数据，主要用于前端动态生成配置项。
        """
        # 创建实例以获得 default_factory 值
        instance = cls()

        confs: dict[str, Any] = {}
        configurable_items: dict[str, Any] = {}

        for name, _field in cls.model_fields.items():
            value = getattr(instance, name)

            confs[name] = value

            # 安全地处理 Pydantic 字段元数据
            field_metadata = {}
            if hasattr(_field, 'json_schema_extra') and _field.json_schema_extra:
                if isinstance(_field.json_schema_extra, dict):
                    field_metadata = _field.json_schema_extra['metadata']
                elif isinstance(_field.json_schema_extra, list | tuple):
                    # 在 Pydantic v2 中，metadata 可能是列表，合并所有字典项
                    for item in _field.json_schema_extra:
                        if isinstance(item, dict):
                            field_metadata.update(item['metadata'])

            # 检查字段是否应该可配置 - 支持不同的元数据格式
            if field_metadata.get("configurable", True):
                default_type = _field.annotation.__name__ if hasattr(_field.annotation, '__name__') else 'str'
                configurable_items[name] = {
                    "type": field_metadata.get("type", default_type),
                    "name": field_metadata.get("name") or name,
                    "options": field_metadata.get("options") or [],
                    "default": _field.default if _field.default is not None else None,
                    "description": field_metadata.get("description") or "",
                    "x_oap_ui_config": field_metadata.get("x_oap_ui_config", {}),
                }

        confs["configurable_items"] = configurable_items
        return confs

class BaseAgent:

    """
    定义一个基础 Agent 供 各类 graph 继承
    """

    name = "base_agent"
    description = "base_agent"
    config_schema: Configuration = Configuration

    def __init__(self, **kwargs):
        pass

    @property
    def module_name(self) -> str:
        """Get the module name of the agent class."""
        return self.__class__.__module__.split('.')[-2]

    @property
    def id(self) -> str:
        """Get the agent's class name."""
        return self.__class__.__name__

    async def get_info(self):
        return {
            "id": self.id,
            "name": self.name if hasattr(self, "name") else "Unknown",
            "description": self.description if hasattr(self, "description") else "Unknown",
            "config_schema": self.config_schema.to_dict(),
            "all_tools": self.all_tools if hasattr(self, "all_tools") else [],
            "has_checkpointer": await self.check_checkpointer(),
        }



    async def stream_values(self, messages: list[str], config_schema: RunnableConfig = None, **kwargs):
        graph = await self.get_graph()
        logger.debug(f"stream_values: {config_schema}")
        for event in graph.astream({"messages": messages}, stream_mode="values", config=config_schema):
            yield event["messages"]

    async def stream_messages(self, messages: list[str], config_schema: RunnableConfig = None, **kwargs):
        graph = await self.get_graph()
        logger.debug(f"stream_messages: {config_schema}")

        async for msg, metadata in graph.astream({"messages": messages}, stream_mode="messages", config=config_schema):
            yield msg, metadata

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
                messages = state.values.get('messages', [])
                for msg in messages:
                    if hasattr(msg, 'model_dump'):
                        msg_dict = msg.model_dump()  # 转换成字典
                    else:
                        msg_dict = dict(msg) if hasattr(msg, '__dict__') else {"content": str(msg)}
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
