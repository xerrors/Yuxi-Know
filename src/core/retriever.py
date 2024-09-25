from src.models.embedding import Reranker
from src.utils.logging_config import setup_logger

logger = setup_logger("server-common")


class Retriever:

    def __init__(self, config, dbm, model):
        self.config = config
        self.dbm = dbm
        self.model = model

        if self.config.enable_reranker:
            self.reranker = Reranker(config)

    def retrieval(self, query, history, meta):

        refs = {"query": query, "history": history, "meta": meta}
        refs["model_name"] = self.config.model_name
        refs["entities"] = self.reco_entities(query, history, refs)
        refs["knowledge_base"] = self.query_knowledgebase(query, history, refs)
        refs["graph_base"] = self.query_graph(query, history, refs)

        return refs

    def construct_query(self, query, refs, meta):
        if not refs or len(refs) == 0:
            return query

        external_parts = []

        # 解析知识库的结果
        kb_res = refs.get("knowledge_base", {}).get("results", [])
        if kb_res:
            kb_text = "\n".join(f"{r['id']}: {r['entity']['text']}" for r in kb_res)
            external_parts.extend(["知识库信息:", kb_text])

        # 解析图数据库的结果
        db_res = refs.get("graph_base", {}).get("results", {})
        if db_res.get("nodes") and len(db_res["nodes"]) > 0:
            db_text = "\n".join(
                [f"{edge['source_name']}和{edge['target_name']}的关系是{edge['type']}" for edge in db_res.get("edges", [])]
            )
            external_parts.extend(["图数据库信息:", db_text])

        # 构造查询
        from src.utils.prompts import knowbase_qa_template
        if external_parts and len(external_parts) > 0:
            external = "\n\n".join(external_parts)
            query = knowbase_qa_template.format(external=external, query=query)

        return query

    def query_classification(self, query):
        """判断是否需要查询
        - 对于完全基于用户给定信息的任务，称之为“足够”“sufficient”，不需要检索；
        - 否则，称之为“不足”“insufficient”，可能需要检索，
        """
        raise NotImplementedError

    def query_graph(self, query, history, refs):
        # res = model.predict("qiansdgsa, dasdh ashdsakjdk ak ").content

        results = []
        if refs["meta"].get("use_graph") and self.config.enable_knowledge_base:
            for entity in refs["entities"]:
                result = self.dbm.graph_base.query_by_vector(entity)
                if result != []:
                    results.extend(result)
        return {"results": self.format_query_results(results)}

    def query_knowledgebase(self, query, history, refs):
        """查询知识库"""

        kb_res = []
        final_res = []

        db_name = refs["meta"].get("db_name")
        if not db_name or not self.config.enable_knowledge_base:
            return {
                "results": final_res,
                "all_results": kb_res,
                "rw_query": query,
                "message": "Knowledge base is disabled",
            }

        rw_query = self.rewrite_query(query, history, refs)

        kb = self.dbm.metaname2db[db_name]
        logger.debug(f"{refs['meta']=}")

        meta = refs["meta"]
        max_query_count = meta.get("maxQueryCount", 10)
        rerank_threshold = meta.get("rerankThreshold", 0.1)
        distance_threshold = meta.get("distanceThreshold", 0)
        top_k = meta.get("topK", 5)

        all_kb_res = self.dbm.knowledge_base.search(rw_query, db_name, limit=max_query_count)
        for r in all_kb_res:
            r["file"] = kb.id2file(r["entity"]["file_id"])

        # use distance threshold to filter results
        if meta.get("mode") == "search":
            kb_res = all_kb_res
        else:
            kb_res = [r for r in all_kb_res if r["distance"] > distance_threshold]

        if self.config.enable_reranker:
            for r in kb_res:
                r["rerank_score"] = self.reranker.compute_score([rw_query, r["entity"]["text"]], normalize=True)[0]
            kb_res.sort(key=lambda x: x["rerank_score"], reverse=True)
            kb_res = [_res for _res in kb_res if _res["rerank_score"] > rerank_threshold]

        kb_res = kb_res[:top_k]

        return {"results": kb_res, "all_results": all_kb_res, "rw_query": rw_query}

    def rewrite_query(self, query, history, refs):
        """重写查询"""
        rewrite_query_span = refs["meta"].get("rewriteQuery", "off")
        if rewrite_query_span == "off":
            rewritten_query = query
        else:
            from src.utils.prompts import rewritten_query_prompt_template

            history_query = [entry["content"] for entry in history if entry["role"] == "user"] if history else ""
            rewritten_query_prompt = rewritten_query_prompt_template.format(history=history_query, query=query)
            rewritten_query = self.model.predict(rewritten_query_prompt).content

        if rewrite_query_span == "hyde":
            hy_doc = self.model.predict(rewritten_query).content
            rewritten_query = f"{rewritten_query} {hy_doc}"

        return rewritten_query

    def reco_entities(self, query, history, refs):
        """识别句子中的实体"""
        query = refs.get("rewritten_query", query)

        entities = []
        if refs["meta"].get("use_graph"):
            from src.utils.prompts import entity_extraction_prompt_template as entity_template
            from src.utils.prompts import keywords_prompt_template as entity_template

            entity_extraction_prompt = entity_template.format(text=query)
            entities = self.model.predict(entity_extraction_prompt).content.split("<->")
            # entities = [entity for entity in entities if all(char.isalnum() or char in "汉字" for char in entity)]

        return entities

    def _extract_relationship_info(self, relationship, source_name, target_name):
        """
        提取关系信息并返回格式化的节点和边信息
        """
        rel_id = relationship.element_id
        nodes = relationship.nodes
        if len(nodes) != 2:
            return None, None

        source, target = nodes
        source_id = source.element_id
        target_id = target.element_id

        relationship_type = relationship._properties.get("type", "unknown")
        if relationship_type == "unknown":
            relationship_type = relationship.type

        edge_info = {
            "id": rel_id,
            "type": relationship_type,
            "source_id": source_id,
            "target_id": target_id,
            "source_name": source_name,
            "target_name": target_name,
        }

        node_info = [
            {"id": source_id, "name": source_name},
            {"id": target_id, "name": target_name},
        ]

        return node_info, edge_info

    def format_general_results(self, results):
        formatted_results = {"nodes": [], "edges": []}

        for item in results:
            relationship = item[1]
            source_name = item[0]._properties.get("name", "unknown")
            target_name = item[2]._properties.get("name", "unknown") if len(item) > 2 else "unknown"

            node_info, edge_info = self._extract_relationship_info(relationship, source_name, target_name)
            if node_info is None or edge_info is None:
                continue

            for node in node_info:
                if node["id"] not in [n["id"] for n in formatted_results["nodes"]]:
                    formatted_results["nodes"].append(node)

            formatted_results["edges"].append(edge_info)

        return formatted_results

    def format_query_results(self, results):
        formatted_results = {"nodes": [], "edges": []}
        node_dict = {}

        for item in results:
            if not isinstance(item[1], list) or not item[1]:
                continue

            relationship = item[1][0]
            source_name = item[0]
            target_name = item[2] if len(item) > 2 else "unknown"

            node_info, edge_info = self._extract_relationship_info(relationship, source_name, target_name)
            if node_info is None or edge_info is None:
                continue

            node_dict.update({node["id"]: node for node in node_info})
            formatted_results["edges"].append(edge_info)

        formatted_results["nodes"] = list(node_dict.values())

        return formatted_results

    def __call__(self, query, history, meta):
        refs = self.retrieval(query, history, meta)
        query = self.construct_query(query, refs, meta)
        return query, refs
