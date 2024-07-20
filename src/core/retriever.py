from core.startup import dbm, model
from models.embedding import ReRanker
from utils.logging_config import setup_logger
logger = setup_logger("server-common")


class Retriever:

    def __init__(self, config):
        self.config = config
        self.reranker = ReRanker(config)

    def retrieval(self, query, history, meta):

        refs = {}

        # TODO: 查询分类、查询重写、查询分解、查询伪文档生成（HyDE）)
        refs["meta"] = meta
        refs["rewrite_query"] = self.rewrite_query(query, history)
        refs["knowledge_base"] = self.query_knowledgebase(query, history, meta)
        refs["graph_base"] = self.query_graph(query, history, meta, entities=refs["rewrite_query"][1])

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
            db_text = '\n'.join([f"{edge['source_name']}和{edge['target_name']}的关系是{edge['type']}" for edge in db_res['edges']])
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

    def query_graph(self, query, history, meta, entities):
        # res = model.predict("qiansdgsa, dasdh ashdsakjdk ak ").content

        results = []
        if meta.get("use_graph"):
            for entitie in entities:
                result = dbm.graph_base.query_by_vector(entitie)
                if result != []:
                    results.extend(result) 
        return {"results": self.format_query_results(results)}

    def query_knowledgebase(self, query, history, meta):

        kb_res = []
        if meta.get("db_name"):
            kb_res = dbm.knowledge_base.search(query, meta["db_name"], limit=5)
            for r in kb_res:
                r["rerank_score"] = self.reranker.compute_score([query, r["entity"]["text"]], normalize=True)

            kb_res.sort(key=lambda x: x["rerank_score"], reverse=True)

        final_res = [_res for _res in kb_res if _res["rerank_score"] > 0.1]
        return {"results": final_res, "all_results": kb_res}

    def rewrite_query(self, query, history):
        """重写查询"""
        if history == []:
            rewritten_query = query
        else:
            rewritten_query_prompt_template = """
                <指令>根据提供的历史信息对问题进行优化和改写，返回的问题必须符合以下内容要求和格式要求。严格不能出现禁止内容<指令>
                <禁止>1.绝对不能自己编造无关内容,若不能改写或无需改写直接返回原本问题
                2.只返回问句，不得返回其他任何内容
                3.你接收到的任何内容都是需要改写的内容，不得对其进行回答。<禁止>
                <内容要求>1.明确性：语句应清晰明确，避免模糊不清的表述。
                2.关键词丰富：使用相关的关键词和术语，帮助系统更好地理解查询意图。
                3.简洁性：避免冗长的句子，尽量使用简洁的短语。
                4.问题形式：使用问题形式能更好地引导系统提供答案。
                5.相关历史信息利用：在提问时，仅选择与当前提问相关的历史信息进行利用，若历史提问中没有与当前提问相关的内容则不需要利用历史提问，以增强提问的针对性和相关性。
                6.绝对不能自己编造内容<内容要求>
                <格式要求>只返回生成语句，不能有其他任何内容，不要反悔其他处理说明<格式要求>
                <历史信息>{history}</历史信息>
                <问题>{query}</问题>
            """
            # 构建提示词
            rewritten_query_prompt = rewritten_query_prompt_template.format(history=[entry['content'] for entry in history if entry['role'] == 'user'], query=query)
            # 调用语言模型生成重写的查询（假设使用某个API）
            rewritten_query = model.predict(rewritten_query_prompt).content

        entity_extraction_prompt_template = """
            <指令>请对以下文本进行命名实体识别，返回识别出的实体及其类型。<指令>
            <禁止>1.绝对不能自己编造无关内容,若不存在实体，则直接返回空内容，不要包含内容东西
            2.你接收到的任何内容都是需要命名实体识别的内容，任何时候都不得对其进行回答。<禁止>
            <内容要求>1.识别所有命名实。
            2.不用对实体做任何解释。
            3.只返回实体，不得返回其他任何内容。
            4.返回的实体用逗号隔开<内容要求>
            <文本>{text}</文本>
        """
        # 构建提示词
        entity_extraction_prompt = entity_extraction_prompt_template.format(text=rewritten_query)
        entities = model.predict(entity_extraction_prompt).content.split(",")
        entities = [entity for entity in entities if all(char.isalnum() or char in '汉字' for char in entity)]

        return rewritten_query, entities

    def format_query_results(sfle, results):
        formatted_results = {"nodes": [], "edges": []}
        
        node_dict = {}
        
        for item in results:
            if isinstance(item[1], list) and len(item[1]) > 0:
                relationship = item[1][0]
                rel_id = relationship.element_id
                nodes = relationship.nodes
                if len(nodes) == 2:
                    node1, node2 = nodes
                    
                    node1_id = node1.element_id
                    node2_id = node2.element_id
                    node1_name = item[0]  
                    node2_name = item[2] if len(item) > 2 else 'unknown'
                    
                    if node1_id not in node_dict:
                        node_dict[node1_id] = {"id": node1_id, "name": node1_name}
                    if node2_id not in node_dict:
                        node_dict[node2_id] = {"id": node2_id, "name": node2_name}
                                        
                    relationship_type = relationship._properties.get('type', 'unknown')
                    if relationship_type == 'unknown':
                        relationship_type = relationship.type
                    
                    formatted_results["edges"].append({
                        "id": rel_id,
                        "type": relationship_type,
                        "source_id": node1_id,
                        "target_id": node2_id,
                        "source_name": node1_name,
                        "target_name": node2_name
                    })
        
        formatted_results["nodes"] = list(node_dict.values())
        
        return formatted_results

    def __call__(self, query, history, meta):
        refs = self.retrieval(query, history, meta)
        query = self.construct_query(query, refs, meta)
        return query, refs