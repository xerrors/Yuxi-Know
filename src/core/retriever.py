class Retriever:

    def __init__(self, config):
        self.config = config

    def retrieval(self, query):

        refs = {}

        # TODO: 查询分类、查询重写、查询分解、查询伪文档生成（HyDE）)
        # NOTE：2024-07-14 暂时禁用知识检索

        return refs

    def construct_query(self, query, refs):
        # TODO：Reranking

        if len(refs) == 0:
            return query

        external = ""

        kb_res = refs.get("knowledge_base")
        if kb_res:
            kb_text = "\n".join([f"{r['id']}: {r['entity']['text']}" for r in kb_res])
            external += f"知识库信息: \n\n{kb_text}"

        if len(external) > 0:
            query = f"以下是参考资料：\n\n\n{external}\n\n\n请根据前面的知识回答：{query}"

        return query

    def query_classification(self, query):
        """判断是否需要查询
        - 对于完全基于用户给定信息的任务，称之为“足够”“sufficient”，不需要检索；
        - 否则，称之为“不足”“insufficient”，可能需要检索，
        """
        raise NotImplementedError

    def rewrite_query(self, query):
        """重写查询"""
        raise NotImplementedError

    def __call__(self, query):
        refs = self.retrieval(query)
        query = self.construct_query(query, refs)
        return query, refs