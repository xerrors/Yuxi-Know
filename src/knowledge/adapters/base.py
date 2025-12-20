from abc import ABC, abstractmethod
from typing import Any


class GraphAdapter(ABC):
    """图谱适配器基类 (Base Graph Adapter)"""

    @abstractmethod
    async def query_nodes(self, keyword: str, **kwargs) -> dict[str, Any]:
        """查询节点 (Query nodes)"""
        pass

    @abstractmethod
    async def add_entity(self, triples: list[dict], **kwargs) -> bool:
        """添加实体三元组 (Add entity triples)"""
        pass

    @abstractmethod
    async def get_sample_nodes(self, num: int = 50, **kwargs) -> dict[str, list]:
        """获取样本节点 (Get sample nodes)"""
        pass

    @abstractmethod
    def normalize_node(self, raw_node: Any) -> dict[str, Any]:
        """标准化节点格式 (Normalize node format)"""
        pass

    @abstractmethod
    def normalize_edge(self, raw_edge: Any) -> dict[str, Any]:
        """标准化边格式 (Normalize edge format)"""
        pass

    @abstractmethod
    async def get_labels(self) -> list[str]:
        """获取所有标签 (Get all labels)"""
        pass

    def _create_standard_node(
        self,
        node_id: str,
        name: str,
        entity_type: str,
        labels: list[str],
        properties: dict[str, Any],
        source: str,
    ) -> dict[str, Any]:
        """
        Helper to create a standardized node dictionary.
        """
        return {
            "id": node_id,
            "name": name,
            "original_id": node_id,
            "type": entity_type,
            "labels": labels,
            "properties": properties,
            "normalized": {
                "name": name,
                "type": entity_type,
                "source": source,
            },
            "graph_type": source,
        }

    def _create_standard_edge(
        self,
        edge_id: str,
        source_id: str,
        target_id: str,
        edge_type: str,
        properties: dict[str, Any],
        direction: str = "directed",
    ) -> dict[str, Any]:
        """
        Helper to create a standardized edge dictionary.
        """
        return {
            "id": edge_id,
            "source_id": source_id,
            "target_id": target_id,
            # Add source/target aliases for frontend compatibility
            # (frontend expects edge.source and edge.target)
            "source": source_id,
            "target": target_id,
            "type": edge_type,
            "properties": properties,
            "normalized": {
                "type": edge_type,
                "direction": direction,
            },
        }
