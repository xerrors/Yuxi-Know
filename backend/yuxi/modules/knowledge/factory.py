from yuxi.infrastructure.observability.logging import logger
from yuxi.modules.knowledge.base import KBNotFoundError, KnowledgeExecutor


class KnowledgeBaseFactory:
    """知识库工厂类，负责创建不同类型的知识库实例"""

    # 注册的知识库类型映射 {kb_type: kb_class}
    _kb_types: dict[str, type[KnowledgeExecutor]] = {}

    @classmethod
    def register(cls, kb_class: type[KnowledgeExecutor]):
        """
        注册知识库类型

        Args:
            kb_class: 知识库类
        """
        if not issubclass(kb_class, KnowledgeExecutor):
            raise ValueError("Knowledge base class must inherit from KnowledgeExecutor")
        if not kb_class.kb_type:
            raise ValueError("Knowledge base class must define kb_type")

        cls._kb_types[kb_class.kb_type] = kb_class
        # logger.info(f"Registered knowledge base type: {kb_class.kb_type}")

    @classmethod
    def create(cls, kb_type: str, work_dir: str, **kwargs) -> KnowledgeExecutor:
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
        if kb_type not in cls._kb_types:
            available_types = list(cls._kb_types.keys())
            raise KBNotFoundError(f"Unknown knowledge base type: {kb_type}. Available types: {available_types}")

        kb_class = cls._kb_types[kb_type]

        try:
            # 创建实例
            instance = kb_class(work_dir, **kwargs)
            logger.info(f"Created {kb_type} knowledge base instance at {work_dir}")
            return instance
        except Exception as e:
            logger.error(f"Failed to create {kb_type} knowledge base: {e}")
            raise

    @classmethod
    def get_available_types(cls) -> dict[str, dict]:
        """
        获取所有可用的知识库类型

        Returns:
            知识库类型信息字典
        """
        result = {}
        for kb_type, kb_class in cls._kb_types.items():
            result[kb_type] = {
                "name": kb_class.name,
                "description": kb_class.description,
                "requires_embedding_model": kb_class.requires_embedding_model,
                "supports_documents": kb_class.supports_documents,
                "supports_document_read": kb_class.supports_document_read,
                "create_params": kb_class.get_create_params_config(),
            }
        return result

    @classmethod
    def get_kb_class(cls, kb_type: str) -> type[KnowledgeExecutor]:
        """
        获取指定类型的知识库类。

        Args:
            kb_type: 知识库类型

        Returns:
            知识库类
        """
        if kb_type not in cls._kb_types:
            available_types = list(cls._kb_types.keys())
            raise KBNotFoundError(f"Unknown knowledge base type: {kb_type}. Available types: {available_types}")
        return cls._kb_types[kb_type]

    @classmethod
    def is_type_supported(cls, kb_type: str) -> bool:
        """
        检查是否支持指定的知识库类型

        Args:
            kb_type: 知识库类型

        Returns:
            是否支持
        """
        return kb_type in cls._kb_types
