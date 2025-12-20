from .base import GraphAdapter
from .lightrag import LightRAGGraphAdapter
from .upload import UploadGraphAdapter


class GraphAdapterFactory:
    """图谱适配器工厂 (Graph Adapter Factory)"""

    _registry: dict[str, type[GraphAdapter]] = {
        "upload": UploadGraphAdapter,
        "lightrag": LightRAGGraphAdapter,
    }

    @classmethod
    def register(cls, graph_type: str, adapter_class: type[GraphAdapter]):
        """注册适配器类 (Register adapter class)"""
        cls._registry[graph_type] = adapter_class

    @classmethod
    def create_adapter(cls, graph_type: str, **kwargs) -> GraphAdapter:
        """创建适配器实例 (Create adapter instance)"""
        adapter_class = cls._registry.get(graph_type)
        if not adapter_class:
            raise ValueError(f"Unknown graph type: {graph_type}")

        return adapter_class(**kwargs)

    @classmethod
    def get_supported_types(cls) -> dict[str, str]:
        """获取支持的图谱类型及其描述"""
        return {
            "upload": "上传文件图谱 - 支持embedding和阈值查询",
            "lightrag": "LightRAG知识图谱 - 基于kb_id标签的图谱",
        }

    @classmethod
    def detect_graph_type(cls, db_id: str, knowledge_base_manager=None) -> str:
        """
        自动检测图谱类型

        Args:
            db_id: 数据库ID
            knowledge_base_manager: 知识库管理器实例

        Returns:
            图谱类型: "lightrag" (LightRAG) 或 "upload"
        """
        # 1. 首先检查是否是 LightRAG 数据库 (通过知识库管理器)
        if knowledge_base_manager:
            db_info = knowledge_base_manager.get_database_info(db_id)
            if db_info:  # 有信息表示是 LightRAG 数据库
                return "lightrag"

        # 2. 检查 kb_ 前缀作为备用方案
        if db_id.startswith("kb_"):
            return "lightrag"

        # 3. 默认为 Upload 类型
        return "upload"

    @classmethod
    def create_adapter_by_db_id(cls, db_id: str, knowledge_base_manager=None, graph_db_instance=None) -> GraphAdapter:
        """
        根据数据库ID自动创建对应的适配器

        Args:
            db_id: 数据库ID
            knowledge_base_manager: 知识库管理器实例
            graph_db_instance: 图数据库实例 (用于Upload类型)

        Returns:
            对应的图谱适配器
        """
        graph_type = cls.detect_graph_type(db_id, knowledge_base_manager)

        if graph_type == "lightrag":
            # LightRAG 类型，使用 kb_id 作为配置
            return cls.create_adapter("lightrag", config={"kb_id": db_id})
        else:
            # Upload 类型，使用 kgdb_name 作为配置
            return cls.create_adapter("upload", graph_db_instance=graph_db_instance, config={"kgdb_name": db_id})

    @classmethod
    def create_adapter_for_db_id(cls, db_id: str, knowledge_base_manager=None, graph_db_instance=None) -> GraphAdapter:
        """
        兼容性方法，调用 create_adapter_by_db_id
        """
        return cls.create_adapter_by_db_id(db_id, knowledge_base_manager, graph_db_instance)
