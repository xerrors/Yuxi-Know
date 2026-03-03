from typing import Any

from src.utils import logger

from .base import BaseNeo4jAdapter, GraphAdapter, GraphMetadata


class LightRAGGraphAdapter(GraphAdapter):
    """LightRAG 图谱适配器 (LightRAG Graph Adapter)"""

    def __init__(self, config: dict[str, Any] = None):
        super().__init__(config)

        # 使用公共的 Neo4j 适配器，而不是 GraphDatabase
        self._db = BaseNeo4jAdapter()

        # 从配置中获取 kb_id
        self.kb_id = self.config.get("kb_id")

    def _get_metadata(self) -> GraphMetadata:
        """获取 LightRAG 图谱元数据"""
        return GraphMetadata(
            graph_type="lightrag",
            id_field="element_id",
            name_field="entity_id",  # LightRAG 使用 entity_id 存储实体名称
            supports_embedding=False,
            supports_threshold=False,
        )

    async def query_nodes(self, keyword: str, **kwargs) -> dict[str, Any]:
        """查询节点 (Query nodes)"""
        kb_id = kwargs.get("kb_id") or self.kb_id
        limit = kwargs.get("max_nodes", kwargs.get("limit", 50))
        max_depth = kwargs.get("max_depth", 1)  # 默认为 1，以返回边

        # 如果 keyword 为 *，强制 max_depth=1 至少
        if keyword == "*":
            max_depth = max(max_depth, 1)

        query = self._build_cypher_query(keyword, kb_id, limit, max_depth)

        try:
            with self._db.driver.session() as session:
                result = session.run(query, keyword=keyword, kb_id=kb_id, limit=limit)
                return self._process_query_result(result, limit=limit)
        except Exception as e:
            logger.error(f"Neo4j query failed: {e}")
            return {"nodes": [], "edges": []}

    async def get_labels(self) -> list[str]:
        """获取所有标签 (Get all labels)"""
        query = "CALL db.labels()"
        try:
            with self._db.driver.session() as session:
                result = session.run(query)
                return [record["label"] for record in result if not record["label"].startswith("kb_")]
        except Exception as e:
            logger.error(f"Failed to get labels: {e}")
            return []

    async def get_stats(self, **kwargs) -> dict[str, Any]:
        """获取统计信息 (Get statistics)"""
        kb_id = kwargs.get("kb_id") or self.kb_id

        # 安全检查
        if kb_id and not all(c.isalnum() or c == "_" for c in kb_id):
            logger.warning(f"Invalid kb_id format: {kb_id}")
            return {"total_nodes": 0, "total_edges": 0, "entity_types": []}

        if not kb_id:
            # 如果没有 kb_id，可能返回全局统计或空
            return {"total_nodes": 0, "total_edges": 0, "entity_types": []}

        try:
            # 统计节点和边
            query = f"""
            MATCH (n:`{kb_id}`)
            WITH count(n) as node_count
            OPTIONAL MATCH (n:`{kb_id}`)-[r]->(m:`{kb_id}`)
            RETURN node_count, count(r) as edge_count
            """

            # 统计标签分布
            label_query = f"""
            MATCH (n:`{kb_id}`)
            UNWIND labels(n) as label
            WITH label, count(*) as count
            WHERE label <> 'Entity' AND NOT label STARTS WITH 'kb_'
            RETURN label, count
            ORDER BY count DESC
            """

            with self._db.driver.session() as session:
                stats = session.run(query).single()
                label_stats = session.run(label_query)

                entity_types_list = [{"type": record["label"], "count": record["count"]} for record in label_stats]

                return {
                    "total_nodes": stats["node_count"],
                    "total_edges": stats["edge_count"],
                    "entity_types": entity_types_list,
                }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {"total_nodes": 0, "total_edges": 0, "entity_types": []}

    def normalize_node(self, raw_node: Any) -> dict[str, Any]:
        """标准化节点格式 (Normalize node format)"""
        if hasattr(raw_node, "element_id"):  # neo4j.graph.Node
            node_id = raw_node.element_id
            labels = list(raw_node.labels)
            properties = dict(raw_node.items())
        elif isinstance(raw_node, dict):
            node_id = raw_node.get("id") or raw_node.get("element_id")
            labels = raw_node.get("labels", [])
            properties = raw_node.get("properties", {})
            if not properties:
                properties = {k: v for k, v in raw_node.items() if k not in ["id", "element_id", "labels"]}
        else:
            return {}

        # 优先使用 entity_id 字段作为 name (LightRAG 风格)，如果不存在则使用 name 字段
        # 很多时候 entity_id 存储了实体名称
        name = properties.get("entity_id", properties.get("name", "Unknown"))

        # 过滤掉 kb_ 开头的标签
        filtered_labels = [label for label in labels if not label.startswith("kb_")]

        # 提取实体类型
        entity_type = "Entity"
        for label in filtered_labels:
            if label != "Entity":
                entity_type = label
                break

        return self._create_standard_node(
            node_id=node_id,
            name=name,
            entity_type=entity_type,
            labels=filtered_labels,
            properties=properties,
            source="neo4j",
        )

    def normalize_edge(self, raw_edge: Any) -> dict[str, Any]:
        """标准化边格式 (Normalize edge format)"""
        logger.info(raw_edge._properties)
        if hasattr(raw_edge, "element_id"):  # neo4j.graph.Relationship
            edge_id = raw_edge.element_id
            edge_type = raw_edge._properties["keywords"] or raw_edge.type
            start_node_id = raw_edge.start_node.element_id if hasattr(raw_edge.start_node, "element_id") else None
            end_node_id = raw_edge.end_node.element_id if hasattr(raw_edge.end_node, "element_id") else None
            properties = dict(raw_edge.items())
        elif isinstance(raw_edge, dict):
            edge_id = raw_edge.get("id")
            edge_type = raw_edge.get("type")
            start_node_id = raw_edge.get("source_id")
            end_node_id = raw_edge.get("target_id")
            properties = raw_edge.get("properties", {})
        else:
            return {}

        return self._create_standard_edge(
            edge_id=edge_id, source_id=start_node_id, target_id=end_node_id, edge_type=edge_type, properties=properties
        )

    def _build_cypher_query(self, keyword: str, kb_id: str = None, limit: int = 50, max_depth: int = 0) -> str:
        """构建 Cypher 查询"""
        # 安全性检查：kb_id 只能包含字母、数字和下划线
        if kb_id:
            if not all(c.isalnum() or c == "_" for c in kb_id):
                logger.warning(f"Invalid kb_id: {kb_id}")
                kb_id = None

        where_clauses = []

        # 确定 MATCH 子句
        if kb_id:
            # 如果提供了 kb_id，直接匹配该标签
            # 这样即使节点没有 Entity 标签也能匹配到
            match_clause = f"MATCH (n:`{kb_id}`)"
        else:
            match_clause = "MATCH (n:Entity)"

        if keyword and keyword != "*":
            # 兼容 LightRAG 格式 (entity_id) 和普通格式 (name)
            where_clauses.append(
                "(toLower(n.name) CONTAINS toLower($keyword) OR toLower(n.entity_id) CONTAINS toLower($keyword))"
            )

        where_str = " AND ".join(where_clauses)
        if where_str:
            where_str = "WHERE " + where_str

        # 如果 max_depth > 0，我们需要扩展查询
        # 为了避免查询过于复杂，我们使用两步法：
        # 1. 找到种子节点
        # 2. 找到这些节点及其周围的关系

        # 步骤 1: 找到种子节点
        # 如果 keyword 是 * 且有 kb_id，我们使用采样逻辑进行随机采样
        # 但这里 query_nodes 主要是为了搜索

        if max_depth > 0:
            # 如果需要扩展，返回子图
            query = f"""
            {match_clause}
            {where_str}
            WITH n LIMIT {limit}

            // 收集种子节点
            WITH collect(n) as seeds

            // 扩展 1 跳 (如果 max_depth >= 1)
            UNWIND seeds as s
            OPTIONAL MATCH (s)-[r1]-(m1)
            // 确保 m1 也在同一个 KB 中 (如果指定了 kb_id)
            {f"WHERE m1:`{kb_id}`" if kb_id else ""}

            WITH seeds, collect(DISTINCT {{h: s, r: r1, t: m1}}) as hop1

            // 扩展 2 跳 (如果 max_depth >= 2)
            // 这里为了简化，只做 1 跳扩展，或者如果需要 2 跳，可以在这里添加
            // 考虑到性能，通常只做 1 跳或者只找种子节点内部的关系

            // 重新整理返回结果
            UNWIND hop1 as triple
            RETURN triple.h as h, triple.r as r, triple.t as t
            LIMIT {limit * 10}
            """

            # 简化版扩展查询：只返回种子节点及其直接连接的边（如果另一端也在 seeds 中，或者不限制）
            # 下面这个查询返回种子节点以及它们之间的关系，加上它们的一跳邻居

            query = f"""
            {match_clause}
            {where_str}
            WITH n LIMIT {limit}

            // 扩展查询：获取 n 和它的邻居
            OPTIONAL MATCH (n)-[r]-(m)
            {f"WHERE m:`{kb_id}`" if kb_id else ""}

            RETURN n, r, m
            """
        else:
            # 仅返回节点
            query = f"""
            {match_clause}
            {where_str}
            RETURN n
            LIMIT {limit}
            """

        return query

    def _build_subgraph_query(self, limit: int, kb_id: str = None) -> str:
        """构建子图查询"""
        # 安全性检查
        if kb_id:
            if not all(c.isalnum() or c == "_" for c in kb_id):
                kb_id = None

        if kb_id:
            match_clause = f"MATCH (n:`{kb_id}`)"
        else:
            match_clause = "MATCH (n:Entity)"

        query = f"""
        {match_clause}
        WITH n LIMIT {limit}
        WITH collect(n) as nodes
        UNWIND nodes as n
        UNWIND nodes as m
        OPTIONAL MATCH (n)-[r]-(m)
        WHERE elementId(n) < elementId(m)
        RETURN n, r, m
        """

        return query

    def _process_query_result(self, result, limit: int = None) -> dict[str, list]:
        """处理查询结果，并限制节点数量不超过 limit"""
        nodes = []
        edges = []
        node_ids = set()
        edge_ids = set()

        for record in result:
            # 检查是否已达到节点限制
            if limit is not None and len(node_ids) >= limit:
                break

            for key in record.keys():
                val = record[key]
                if val is None:
                    continue

                if hasattr(val, "element_id") and hasattr(val, "labels"):  # Node
                    if val.element_id not in node_ids:
                        # 再次检查限制
                        if limit is not None and len(node_ids) >= limit:
                            break
                        nodes.append(self.normalize_node(val))
                        node_ids.add(val.element_id)
                elif hasattr(val, "element_id") and hasattr(val, "start_node"):  # Relationship
                    if val.element_id not in edge_ids:
                        edges.append(self.normalize_edge(val))
                        edge_ids.add(val.element_id)
                elif isinstance(val, list):
                    for item in val:
                        if hasattr(item, "element_id") and hasattr(item, "labels"):
                            if item.element_id not in node_ids:
                                if limit is not None and len(node_ids) >= limit:
                                    break
                                nodes.append(self.normalize_node(item))
                                node_ids.add(item.element_id)

        # 过滤掉引用不存在节点的边
        valid_edges = []
        for edge in edges:
            source_id = edge.get("source_id")
            target_id = edge.get("target_id")
            if source_id in node_ids and target_id in node_ids:
                valid_edges.append(edge)

        return {"nodes": nodes, "edges": valid_edges}
