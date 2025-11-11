"""Define the configurable parameters for the agent."""

import os
import uuid
from dataclasses import MISSING, dataclass, field, fields
from pathlib import Path
from typing import Annotated, get_args, get_origin

import yaml

from src import config as sys_config
from src.utils import logger


@dataclass(kw_only=True)
class BaseContext:
    """
    定义一个基础 Context 供 各类 graph 继承

    配置优先级:
    1. 运行时配置(RunnableConfig)：最高优先级，直接从函数参数传入
    2. 文件配置(config.private.yaml)：中等优先级，从文件加载
    3. 类默认配置：最低优先级，类中定义的默认值
    """

    def update(self, data: dict):
        """更新配置字段"""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)

    thread_id: str = field(
        default_factory=lambda: str(uuid.uuid4()),
        metadata={"name": "线程ID", "configurable": False, "description": "用来唯一标识一个对话线程"},
    )

    user_id: str = field(
        default_factory=lambda: str(uuid.uuid4()),
        metadata={"name": "用户ID", "configurable": False, "description": "用来唯一标识一个用户"},
    )

    system_prompt: str = field(
        default="You are a helpful assistant.",
        metadata={"name": "系统提示词", "description": "用来描述智能体的角色和行为"},
    )

    model: Annotated[str, {"__template_metadata__": {"kind": "llm"}}] = field(
        default=sys_config.default_model,
        metadata={"name": "智能体模型", "options": [], "description": "智能体的驱动模型"},
    )

    @classmethod
    def from_file(cls, module_name: str, input_context: dict = None) -> "BaseContext":
        """Load configuration from a YAML file. 用于持久化配置"""

        # 从文件加载配置
        context = cls()
        config_file_path = Path(sys_config.save_dir) / "agents" / module_name / "config.yaml"
        if module_name is not None and os.path.exists(config_file_path):
            file_config = {}
            try:
                with open(config_file_path, encoding="utf-8") as f:
                    file_config = yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"加载智能体配置文件出错: {e}")

            context.update(file_config)

        if input_context:
            context.update(input_context)

        return context

    @classmethod
    def save_to_file(cls, config: dict, module_name: str) -> bool:
        """Save configuration to a YAML file 用于持久化配置"""

        configurable_items = cls.get_configurable_items()
        configurable_config = {}
        for k, v in config.items():
            if k in configurable_items:
                configurable_config[k] = v

        try:
            config_file_path = Path(sys_config.save_dir) / "agents" / module_name / "config.yaml"
            # 确保目录存在
            os.makedirs(os.path.dirname(config_file_path), exist_ok=True)
            with open(config_file_path, "w", encoding="utf-8") as f:
                yaml.dump(configurable_config, f, indent=2, allow_unicode=True)

            return True
        except Exception as e:
            logger.error(f"保存智能体配置文件出错: {e}")
            return False

    @classmethod
    def get_configurable_items(cls):
        """实现一个可配置的参数列表，在 UI 上配置时使用"""
        configurable_items = {}
        for f in fields(cls):
            if f.init and not f.metadata.get("hide", False):
                if f.metadata.get("configurable", True):
                    # 处理类型信息
                    field_type = f.type
                    type_name = cls._get_type_name(field_type)

                    # 提取 Annotated 的元数据
                    template_metadata = cls._extract_template_metadata(field_type)

                    configurable_items[f.name] = {
                        "type": type_name,
                        "name": f.metadata.get("name", f.name),
                        "options": f.metadata.get("options", []),
                        "default": f.default
                        if f.default is not MISSING
                        else f.default_factory()
                        if f.default_factory is not MISSING
                        else None,
                        "description": f.metadata.get("description", ""),
                        "template_metadata": template_metadata,  # Annotated 的额外元数据
                    }

        return configurable_items

    @classmethod
    def _get_type_name(cls, field_type) -> str:
        """获取类型名称，处理 Annotated 类型"""
        # 检查是否是 Annotated 类型
        if get_origin(field_type) is not None:
            # 处理泛型类型如 list[str], Annotated[str, {...}]
            origin = get_origin(field_type)
            if hasattr(origin, "__name__"):
                if origin.__name__ == "Annotated":
                    # Annotated 类型，获取真实类型
                    args = get_args(field_type)
                    if args:
                        return cls._get_type_name(args[0])  # 递归处理真实类型
                return origin.__name__
            else:
                return str(origin)
        elif hasattr(field_type, "__name__"):
            return field_type.__name__
        else:
            return str(field_type)

    @classmethod
    def _extract_template_metadata(cls, field_type) -> dict:
        """从 Annotated 类型中提取模板元数据"""
        if get_origin(field_type) is not None:
            origin = get_origin(field_type)
            if hasattr(origin, "__name__") and origin.__name__ == "Annotated":
                args = get_args(field_type)
                if len(args) > 1:
                    # 查找包含 __template_metadata__ 的字典
                    for metadata in args[1:]:
                        if isinstance(metadata, dict) and "__template_metadata__" in metadata:
                            return metadata["__template_metadata__"]
        return {}
