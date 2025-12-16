from .base import GraphAdapter
from .lightrag import LightRAGGraphAdapter
from .upload import UploadGraphAdapter


class GraphAdapterFactory:
    """图谱适配器工厂 (Graph Adapter Factory)"""

    _registry: dict[str, type[GraphAdapter]] = {"upload": UploadGraphAdapter, "lightrag": LightRAGGraphAdapter}

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
