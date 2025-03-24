from src.models.rerank_model import get_reranker
from src.utils.logging_config import logger


class Retriever:

    def __init__(self, config, dbm, model):
        self.config = config
        self.dbm = dbm
        self.model = model

        if self.config.enable_reranker:
            self.reranker = get_reranker(config)

        if self.config.enable_web_search:
            from src.utils.web_search import WebSearcher
            self.web_searcher = WebSearcher()

    def retrieval(self, query, history, meta):
        refs = {"query": query, "history": history, "meta": meta}
        refs["model_name"] = self.config.model_name
        refs["entities"] = self.reco_entities(query, history, refs)
        refs["knowledge_base"] = self.query_knowledgebase(query, history, refs)
        refs["graph_base"] = self.query_graph(query, history, refs)
        refs["web_search"] = self.query_web(query, history, refs)

        return refs

    def construct_query(self, query, refs, meta):
        logger.debug(f"{refs=}")
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

        # 解析网络搜索的结果
        web_res = refs.get("web_search", {}).get("results", [])
        if web_res:
            web_text = "\n".join(f"{r['title']}: {r['content']}" for r in web_res)
            external_parts.extend(["网络搜索信息:", web_text])

        # 构造查询
        from src.utils.prompts import knowbase_qa_template
        if external_parts and len(external_parts) > 0:
            external = "\n\n".join(external_parts)
            query = knowbase_qa_template.format(external=external, query=query)

        return query

    def query_classification(self, query):
        """判断是否需要查询
        - 对于完全基于用户给定信息的任务，称之为"足够""sufficient"，不需要检索；
        - 否则，称之为"不足""insufficient"，可能需要检索，
        """
        raise NotImplementedError

    def query_graph(self, query, history, refs):
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

        # 检索
        all_kb_res = self.dbm.knowledge_base.search(rw_query, db_name, limit=max_query_count)
        for r in all_kb_res:
            r["file"] = kb.id2file(r["entity"]["file_id"])

        kb_res = [r for r in all_kb_res if r["distance"] > distance_threshold]

        # 重排序
        if self.config.enable_reranker and len(kb_res) > 0:
            texts = [r["entity"]["text"] for r in kb_res]
            rerank_scores = self.reranker.compute_score([rw_query, texts], normalize=True)
            for i, r in enumerate(kb_res):
                r["rerank_score"] = rerank_scores[i]
            kb_res.sort(key=lambda x: x["rerank_score"], reverse=True)
            kb_res = [_res for _res in kb_res if _res["rerank_score"] > rerank_threshold]

        kb_res = kb_res[:top_k]

        return {"results": kb_res, "all_results": all_kb_res, "rw_query": rw_query}

    def query_web(self, query, history, refs):
        """查询网络"""

        if not (refs["meta"].get("use_web") and self.config.enable_web_search):
            return {"results": [], "message": "Web search is disabled"}

        try:
            search_results = self.web_searcher.search(query, max_results=5)
        except Exception as e:
            logger.error(f"Web search error: {str(e)}")
            return {"results": [], "message": "Web search error"}

        return {"results": search_results}

    def rewrite_query(self, query, history, refs):
        """重写查询"""
        if refs["meta"].get("mode") == "search":  # 如果是搜索模式，就使用 meta 的配置，否则就使用全局的配置
            rewrite_query_span = refs["meta"].get("use_rewrite_query", "off")
        else:
            rewrite_query_span = self.config.use_rewrite_query

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

    def _extract_relationship_info(self, relationship, source_name=None, target_name=None, node_dict=None):
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

        source_name = node_dict[source_id]["name"] if source_name is None else source_name
        target_name = node_dict[target_id]["name"] if target_name is None else target_name

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
        logger.debug(f"Graph Query Results: {results}")
        formatted_results = {"nodes": [], "edges": []}
        node_dict = {}

        for item in results:
            # 检查数据格式
            if len(item) < 2 or not isinstance(item[1], list):
                continue

            node_dict[item[0].element_id] = dict(id=item[0].element_id, name=item[0]._properties.get("name", "Unknown"))
            node_dict[item[2].element_id] = dict(id=item[2].element_id, name=item[2]._properties.get("name", "Unknown"))

            # 处理关系列表中的每个关系
            for i, relationship in enumerate(item[1]):
                try:
                    # 提取关系信息
                    node_info, edge_info = self._extract_relationship_info(relationship, node_dict=node_dict)
                    if node_info is None or edge_info is None:
                        continue

                    # 添加边
                    formatted_results["edges"].append(edge_info)
                except Exception as e:
                    logger.error(f"处理关系时出错: {e}, 关系: {relationship}")
                    continue

        # 将节点字典转换为列表
        formatted_results["nodes"] = list(node_dict.values())

        return formatted_results

    def __call__(self, query, history, meta):
        refs = self.retrieval(query, history, meta)
        query = self.construct_query(query, refs, meta)
        return query, refs
