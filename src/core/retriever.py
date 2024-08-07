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

        refs = {}
        refs["meta"] = meta
        refs["rewritten_query"] = self.rewrite_query(query, history, refs)
        refs["entities"] = self.reco_entities(query, history, refs)
        refs["knowledge_base"] = self.query_knowledgebase(query, history, refs)
        refs["graph_base"] = self.query_graph(query, history, refs)

        return refs

    def construct_query(self, query, refs, meta):
        if len(refs) == 0:
            return query

        external = ""

        # 解析知识库的结果
        kb_res = refs.get("knowledge_base").get("results", [])
        if len(kb_res) > 0:
            kb_text = "\n".join([f"{r['id']}: {r['entity']['text']}" for r in kb_res])
            external += f"知识库信息: \n\n{kb_text}"

        # 解析图数据库的结果
        db_res = refs.get("graph_base").get("results", [])
        if len(db_res["nodes"]) > 0:
            db_text = '\n'.join([f"{edge['source_name']}和{edge['target_name']}的关系是{edge['type']}" for edge in db_res['edges']])
            external += f"图数据库信息: \n\n{db_text}"

        # 构造查询
        if len(external) > 0:
            query = f"以下是参考资料：\n\n\n{external}\n\n\n请根据前面的知识回答：{query}"

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
        query = refs.get("rewritten_query", query)

        kb_res = []
        final_res = []
        if refs["meta"].get("db_name") and self.config.enable_knowledge_base:
            db_name = refs["meta"]["db_name"]
            kb = self.dbm.metaname2db[refs["meta"]["db_name"]]
            limit = refs["meta"].get("queryCount", 10)
            kb_res = self.dbm.knowledge_base.search(query, db_name, limit=limit)
            for r in kb_res:
                r["file"] = kb.id2file(r["entity"]["file_id"])

            if self.config.enable_reranker:
                for r in kb_res:
                    r["rerank_score"] = self.reranker.compute_score([query, r["entity"]["text"]], normalize=True)
                kb_res.sort(key=lambda x: x["rerank_score"], reverse=True)
                final_res = [_res for _res in kb_res if _res["rerank_score"] > 0.1]
            else:
                final_res = kb_res[:5]

        return {"results": final_res, "all_results": kb_res}

    def rewrite_query(self, query, history, refs):
        """重写查询"""
        if refs["meta"].get("rewrite_query") is None or history == []:
            rewritten_query = query
        else:
            from src.utils.prompts import rewritten_query_prompt_template
            rewritten_query_prompt = rewritten_query_prompt_template.format(history=[entry['content'] for entry in history if entry['role'] == 'user'], query=query)
            rewritten_query = self.model.predict(rewritten_query_prompt).content

        return rewritten_query

    def reco_entities(self, query, history, refs):
        """识别句子中的实体"""
        query = refs.get("rewritten_query", query)

        entities = []
        if refs["meta"].get("use_graph"):
            from src.utils.prompts import entity_extraction_prompt_template
            entity_extraction_prompt = entity_extraction_prompt_template.format(text=query)
            entities = self.model.predict(entity_extraction_prompt).content.split(",")
            entities = [entity for entity in entities if all(char.isalnum() or char in '汉字' for char in entity)]

        return entities

    def format_query_results(self, results):
        formatted_results = {"nodes": [], "edges": []}

        node_dict = {}

        for item in results:
            if not isinstance(item[1], list) or len(item[1]) == 0:
                continue

            relationship = item[1][0]
            rel_id = relationship.element_id
            nodes = relationship.nodes
            if len(nodes) != 2:
                continue

            source, target = nodes

            source_id = source.element_id
            target_id = target.element_id
            source_name = item[0]
            target_name = item[2] if len(item) > 2 else 'unknown'

            if source_id not in node_dict:
                node_dict[source_id] = {"id": source_id, "name": source_name}
            if target_id not in node_dict:
                node_dict[target_id] = {"id": target_id, "name": target_name}

            relationship_type = relationship._properties.get('type', 'unknown')
            if relationship_type == 'unknown':
                relationship_type = relationship.type

            formatted_results["edges"].append({
                "id": rel_id,
                "type": relationship_type,
                "source_id": source_id,
                "target_id": target_id,
                "source_name": source_name,
                "target_name": target_name
            })

        formatted_results["nodes"] = list(node_dict.values())

        return formatted_results

    def __call__(self, query, history, meta):
        refs = self.retrieval(query, history, meta)
        query = self.construct_query(query, refs, meta)
        return query, refs