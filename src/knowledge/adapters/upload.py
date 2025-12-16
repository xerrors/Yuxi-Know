from typing import Any

from src.knowledge.graph import GraphDatabase

from .base import GraphAdapter


class UploadGraphAdapter(GraphAdapter):
    """Upload图谱适配器 (Upload Graph Adapter)"""

    def __init__(self, graph_db_instance: GraphDatabase, config: dict[str, Any] = None):
        self.config = config or {
            "node_label": "Entity:Upload",
            "id_field": "name",
            "relation_label": "RELATION",
            "default_tags": ["upload", "user_generated"],
        }
        self.graph_db = graph_db_instance

    async def query_nodes(self, keyword: str, **kwargs) -> dict[str, Any]:
        params = self._normalize_query_params(keyword, kwargs)

        # 如果关键词是 "*" 或者为空，则执行采样查询
        if not params["keyword"] or params["keyword"] == "*":
            # 映射 max_nodes 到 num
            num = kwargs.get("max_nodes", 100)
            raw_results = self.graph_db.get_sample_nodes(kgdb_name=params.get("kgdb_name", "neo4j"), num=num)
        else:
            # 否则执行关键词搜索
            # graph_db.query_node is sync
            raw_results = self.graph_db.query_node(
                keyword=params["keyword"],
                threshold=params.get("threshold", 0.9),
                kgdb_name=params.get("kgdb_name", "neo4j"),
                hops=params.get("hops", 2),
                return_format="graph",
            )

        return self._format_results(raw_results)

    async def add_entity(self, triples: list[dict], **kwargs) -> bool:
        kgdb_name = kwargs.get("kgdb_name", "neo4j")
        # txt_add_vector_entity is async
        await self.graph_db.txt_add_vector_entity(triples, kgdb_name=kgdb_name)
        return True

    async def get_sample_nodes(self, num: int = 50, **kwargs) -> dict[str, list]:
        kgdb_name = kwargs.get("kgdb_name", "neo4j")
        # get_sample_nodes is sync
        raw_results = self.graph_db.get_sample_nodes(kgdb_name=kgdb_name, num=num)
        return self._format_results(raw_results)

    def normalize_node(self, raw_node: Any) -> dict[str, Any]:
        """
        raw_node expected format: {id: str, name: str, ...}
        """
        node_id = raw_node.get("id")
        name = raw_node.get("name")

        return self._create_standard_node(
            node_id=node_id,
            name=name,
            entity_type="entity",
            labels=["Entity", "Upload"],
            properties=raw_node,
            source="upload",
        )

    def normalize_edge(self, raw_edge: Any) -> dict[str, Any]:
        """
        raw_edge expected format: {type: str, source_id: str, target_id: str, ...}
        """
        # Generate an ID if not present (Upload graph edges might not have explicit ID in simple dict return)
        edge_id = raw_edge.get("id")
        if not edge_id:
            edge_id = f"{raw_edge.get('source_id')}_{raw_edge.get('type')}_{raw_edge.get('target_id')}"

        return self._create_standard_edge(
            edge_id=edge_id,
            source_id=raw_edge.get("source_id"),
            target_id=raw_edge.get("target_id"),
            edge_type=raw_edge.get("type"),
            properties=raw_edge,
        )

    async def get_labels(self) -> list[str]:
        kgdb_name = self.config.get("kgdb_name", "neo4j")
        info = self.graph_db.get_graph_info(graph_name=kgdb_name)
        return info.get("labels", []) if info else []

    def _normalize_query_params(self, keyword: str, kwargs: dict) -> dict[str, Any]:
        # Map max_depth to hops if present
        hops = kwargs.get("hops")
        if hops is None:
            hops = kwargs.get("max_depth", 2)

        return {
            "keyword": keyword,
            "threshold": kwargs.get("threshold", 0.9),
            "kgdb_name": kwargs.get("kgdb_name", "neo4j"),
            "hops": hops,
            "filters": kwargs.get("filters", {}),
            "context": kwargs.get("context", {}),
        }

    def _format_results(self, raw_results: dict[str, list]) -> dict[str, list]:
        nodes = [self.normalize_node(n) for n in raw_results.get("nodes", [])]
        edges = [self.normalize_edge(e) for e in raw_results.get("edges", [])]
        return {"nodes": nodes, "edges": edges}
