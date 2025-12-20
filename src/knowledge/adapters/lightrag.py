import logging
from typing import Any

from .base import GraphAdapter

logger = logging.getLogger(__name__)


class LightRAGGraphAdapter(GraphAdapter):
    """LightRAG图谱适配器 (LightRAG Graph Adapter)"""

    def __init__(self, lightrag_instance: Any, config: dict[str, Any] = None):
        self.config = config or {
            "node_label_field": "labels",
            "id_field": "id",
            "type_field": "entity_type",
            "relation_prefix": "HAS_",
        }
        self.lightrag = lightrag_instance

    async def query_nodes(self, keyword: str, **kwargs) -> dict[str, Any]:
        # Map keyword to node_label
        # If keyword is empty or "*", query all (or sample)
        node_label = keyword if keyword and keyword != "*" else "*"

        max_depth = kwargs.get("max_depth", 2)
        max_nodes = kwargs.get("max_nodes", 100)

        # lightrag.get_knowledge_graph is async
        # Note: if node_label is "*", LightRAG might return a large graph or sample depending on implementation
        raw_graph = await self.lightrag.get_knowledge_graph(
            node_label=node_label, max_depth=max_depth, max_nodes=max_nodes
        )

        return self._convert_lightrag_graph(raw_graph)

    async def add_entity(self, triples: list[dict], **kwargs) -> bool:
        """
        LightRAG typically builds graph from text.
        Direct triple injection might not be supported or requires different API.
        """
        logger.warning("add_entity is not fully supported for LightRAG adapter yet.")
        return False

    async def get_sample_nodes(self, num: int = 50, **kwargs) -> dict[str, list]:
        # Use query_nodes with wildcard to get a subgraph
        return await self.query_nodes("*", max_nodes=num, **kwargs)

    def normalize_node(self, raw_node: Any) -> dict[str, Any]:
        # Handle LightRAG Node object
        raw_node_id = getattr(raw_node, "id", None)
        if raw_node_id is None:
            raw_node_id = raw_node.get("id")

        labels = getattr(raw_node, "labels", [])
        if not labels and hasattr(raw_node, "get"):
            labels = raw_node.get("labels", [])

        properties = getattr(raw_node, "properties", {})
        if not properties and hasattr(raw_node, "get"):
            properties = raw_node.get("properties", {})

        # LightRAG stores entity name in entity_id property
        # Use entity_id as BOTH the node ID AND display name for consistent edge matching
        # (edges reference nodes by entity name, not by Neo4j element ID)
        name = properties.get("entity_id", raw_node_id)
        
        # Use entity name as node_id so edges can correctly reference it
        # (LightRAG edges use entity names as source/target)
        node_id = name  # This ensures edge source_id/target_id matches node id

        # 尝试从 properties 获取 entity_type，或者从 labels 中推断（排除 kb_ 前缀的 label）
        entity_type = properties.get("entity_type", "unknown")
        if entity_type == "unknown" and labels:
            for label in labels:
                if not label.startswith("kb_"):
                    entity_type = label
                    break

        return self._create_standard_node(
            node_id=node_id, name=name, entity_type=entity_type, labels=labels, properties=properties, source="lightrag"
        )

    def normalize_edge(self, raw_edge: Any) -> dict[str, Any]:
        # Handle LightRAG Edge object
        edge_id = getattr(raw_edge, "id", None)
        if edge_id is None:
            edge_id = raw_edge.get("id")

        source = getattr(raw_edge, "source", None)
        if source is None:
            source = raw_edge.get("source")

        target = getattr(raw_edge, "target", None)
        if target is None:
            target = raw_edge.get("target")

        edge_type = getattr(raw_edge, "type", None)
        if edge_type is None:
            edge_type = raw_edge.get("type")

        properties = getattr(raw_edge, "properties", {})
        if not properties and hasattr(raw_edge, "get"):
            properties = raw_edge.get("properties", {})

        # 优化边的显示类型
        # LightRAG 的边类型通常是 "DIRECTED"，具体含义在 keywords 或 description 中
        display_type = edge_type
        if edge_type == "DIRECTED":
            keywords = properties.get("keywords", [])
            if keywords and isinstance(keywords, list) and len(keywords) > 0:
                display_type = keywords[0]
            elif properties.get("description"):
                # 如果没有 keywords，尝试从 description 截取（太长就算了）
                desc = properties.get("description", "")
                if len(desc) < 20:
                    display_type = desc
                else:
                    display_type = "related"  # fallback

        return self._create_standard_edge(
            edge_id=edge_id, source_id=source, target_id=target, edge_type=display_type, properties=properties
        )

    async def get_labels(self) -> list[str]:
        return await self.lightrag.get_graph_labels()

    def _convert_lightrag_graph(self, raw_graph) -> dict[str, Any]:
        nodes = []
        edges = []

        # Build a mapping from Neo4j numeric ID to entity name
        # This is needed because edges reference nodes by Neo4j ID,
        # but we use entity names as node IDs for frontend display
        neo4j_id_to_entity_name = {}

        # raw_graph has .nodes and .edges lists
        if hasattr(raw_graph, "nodes"):
            for node in raw_graph.nodes:
                raw_node_id = getattr(node, "id", None)
                props = getattr(node, "properties", {}) or {}
                entity_name = props.get("entity_id", raw_node_id)
                
                # Map Neo4j ID to entity name
                if raw_node_id is not None:
                    neo4j_id_to_entity_name[str(raw_node_id)] = entity_name
                
                nodes.append(self.normalize_node(node))

        if hasattr(raw_graph, "edges"):
            for edge in raw_graph.edges:
                # Convert edge source/target from Neo4j IDs to entity names
                raw_source = getattr(edge, "source", None)
                raw_target = getattr(edge, "target", None)
                
                # Look up entity names using the mapping
                source_name = neo4j_id_to_entity_name.get(str(raw_source), raw_source)
                target_name = neo4j_id_to_entity_name.get(str(raw_target), raw_target)
                
                # Create edge with entity names instead of Neo4j IDs
                normalized_edge = self._normalize_edge_with_names(edge, source_name, target_name)
                edges.append(normalized_edge)

        result = {"nodes": nodes, "edges": edges}

        # Add metadata if available
        if hasattr(raw_graph, "is_truncated"):
            result["is_truncated"] = raw_graph.is_truncated

        result["total_nodes"] = len(nodes)
        result["total_edges"] = len(edges)

        return result

    def _normalize_edge_with_names(self, raw_edge: Any, source_name: str, target_name: str) -> dict[str, Any]:
        """Normalize edge with pre-resolved source and target entity names."""
        edge_id = getattr(raw_edge, "id", None)
        if edge_id is None:
            edge_id = raw_edge.get("id") if hasattr(raw_edge, "get") else None

        edge_type = getattr(raw_edge, "type", None)
        if edge_type is None:
            edge_type = raw_edge.get("type") if hasattr(raw_edge, "get") else None

        properties = getattr(raw_edge, "properties", {})
        if not properties and hasattr(raw_edge, "get"):
            properties = raw_edge.get("properties", {})

        # Optimize edge display type
        display_type = edge_type
        if edge_type == "DIRECTED":
            keywords = properties.get("keywords", [])
            if keywords and isinstance(keywords, list) and len(keywords) > 0:
                display_type = keywords[0]
            elif properties.get("description"):
                desc = properties.get("description", "")
                if len(desc) < 20:
                    display_type = desc
                else:
                    display_type = "related"

        return self._create_standard_edge(
            edge_id=edge_id, source_id=source_name, target_id=target_name, edge_type=display_type, properties=properties
        )

