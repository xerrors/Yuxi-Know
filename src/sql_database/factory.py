from src.utils import logger
from src.sql_database.base import DBNotFoundError, DBOperationError
from src.sql_database.base import ConnectorBase



class DBConnectorBaseFactory:
    """知识库工厂类，负责创建不同类型的知识库实例"""

    # 注册的知识库类型映射 {kb_type: kb_class}
    _db_types: dict[str, type[ConnectorBase]] = {}

    # 每种类型的默认配置
    _default_configs: dict[str, dict] = {}

    @classmethod
    def register(cls, db_type: str, db_class: type[ConnectorBase], default_config: dict = None):
        """
        注册知识库类型

        Args:
            kb_type: 知识库类型标识
            kb_class: 知识库类
            default_config: 默认配置
        """
        if not issubclass(db_class, ConnectorBase):
            raise ValueError("Knowledge base class must inherit from KnowledgeBase")

        cls._db_types[db_type] = db_class
        cls._default_configs[db_type] = default_config or {}
        # logger.info(f"Registered knowledge base type: {kb_type}")

    @classmethod
    def create(cls, db_type: str, work_dir: str, **kwargs) -> ConnectorBase:
        """
        创建知识库实例

        Args:
            kb_type: 知识库类型
            work_dir: 工作目录
            **kwargs: 其他初始化参数

        Returns:
            知识库实例

        Raises:
            KBNotFoundError: 未知的知识库类型
        """
        if db_type not in cls._db_types:
            available_types = list(cls._db_types.keys())
            raise DBNotFoundError(f"Unknown knowledge base type: {db_type}. Available types: {available_types}")

        db_class = cls._db_types[db_type]

        # 合并默认配置和用户配置
        config = cls._default_configs[db_type].copy()
        config.update(kwargs)

        try:
            # 创建实例
            instance = db_class(work_dir, **config)
            logger.info(f"Created {db_type} knowledge base instance at {work_dir}")
            return instance
        except Exception as e:
            logger.error(f"Failed to create {db_type} knowledge base: {e}")
            raise

    @classmethod
    def get_available_types(cls) -> dict[str, dict]:
        """
        获取所有可用的知识库类型

        Returns:
            知识库类型信息字典
        """
        result = {}
        for db_type, kb_class in cls._db_types.items():
            result[db_type] = {
                "class_name": kb_class.__name__,
                "description": kb_class.__doc__ or "",
                "default_config": cls._default_configs[db_type],
            }
        return result

    @classmethod
    def is_type_supported(cls, kb_type: str) -> bool:
        """
        检查是否支持指定的知识库类型

        Args:
            kb_type: 知识库类型

        Returns:
            是否支持
        """
        return kb_type in cls._db_types

    @classmethod
    def get_default_config(cls, kb_type: str) -> dict:
        """
        获取指定类型的默认配置

        Args:
            kb_type: 知识库类型

        Returns:
            默认配置字典
        """
        return cls._default_configs.get(kb_type, {}).copy()
