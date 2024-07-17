from core.startup import dbm, model
from models.embedding import ReRanker

class Retriever:

    def __init__(self, config):
        self.config = config
        self.reranker = ReRanker(config)

    def retrieval(self, query, history, meta):

        refs = {}

        # TODO: 查询分类、查询重写、查询分解、查询伪文档生成（HyDE）)
        refs["knowledge_base"] = self.query_knowledgebase(query, history, meta)
        refs["graph_base"] = self.query_graph(query, history, meta)


        return refs

    def construct_query(self, query, refs, meta):
        if len(refs) == 0:
            return query

        external = ""

        kb_res = refs.get("knowledge_base").get("results", [])
        if len(kb_res) > 0:
            kb_text = "\n".join([f"{r['id']}: {r['entity']['text']}" for r in kb_res])
            external += f"知识库信息: \n\n{kb_text}"

        db_res = refs.get("graph_base").get("results", [])
        if len(db_res) > 0:
            db_text = "\n".join([f"{r['id']}: {r['entity']['text']}" for r in db_res])
            external += f"图数据库信息: \n\n{db_text}"

        if len(external) > 0:
            query = f"以下是参考资料：\n\n\n{external}\n\n\n请根据前面的知识回答：{query}"

        return query

    def query_classification(self, query):
        """判断是否需要查询
        - 对于完全基于用户给定信息的任务，称之为“足够”“sufficient”，不需要检索；
        - 否则，称之为“不足”“insufficient”，可能需要检索，
        """
        raise NotImplementedError

    def query_graph(self, query, history, meta):
        # res = model.predict("qiansdgsa, dasdh ashdsakjdk ak ").content

        return {}

    def query_knowledgebase(self, query, history, meta):

        kb_res = None
        if meta.get("db_name"):
            kb_res = dbm.knowledge_base.search(query, meta["db_name"], limit=5)
            for r in kb_res:
                r["rerank_score"] = self.reranker.compute_score([query, r["entity"]["text"]], normalize=True)

            kb_res.sort(key=lambda x: x["rerank_score"], reverse=True)

        final_res = [_res for _res in kb_res if _res["rerank_score"] > 0.1]
        return {"results": final_res, "all_results": kb_res}

    def rewrite_query(self, query):
        """重写查询"""
        raise NotImplementedError

    def __call__(self, query, history, meta):
        refs = self.retrieval(query, history, meta)
        query = self.construct_query(query, refs, meta)
        return query, refs