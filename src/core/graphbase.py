import os
import json
import torch
from neo4j import GraphDatabase as GD
# from src.plugins import pdf2txt, OneKE
from transformers import AutoTokenizer, AutoModel
from FlagEmbedding import FlagModel, FlagReranker
import warnings

from src.plugins import pdf2txt
from src.plugins.oneke import OneKE
from src.utils import setup_logger

logger = setup_logger("server-graphbase")

warnings.filterwarnings("ignore", category=UserWarning)


UIE_MODEL = None

class GraphDatabase:
    def __init__(self, config, embed_model=None, kgdb_name="neo4j"):
        self.config = config
        self.driver = None
        self.files = []
        self.status = "closed"
        self.kgdb_name = kgdb_name
        assert embed_model, "embed_model=None"
        self.embed_model = embed_model

    def start(self):
        uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        username = os.environ.get("NEO4J_USERNAME", "neo4j")
        password = os.environ.get("NEO4J_PASSWORD", "0123456789")
        logger.info(f"Connecting to Neo4j at {uri}/{self.kgdb_name}")
        try:
            self.driver = GD.driver(f"{uri}/{self.kgdb_name}", auth=(username, password))
            self.status = "open"
            logger.info(f"Connected to Neo4j at {uri}/{self.kgdb_name}, {self.get_database_info()}")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}, {uri}, {self.kgdb_name}, {username}, {password}")
            self.config.enable_knowledge_graph = False


    def close(self):
        """关闭数据库连接"""
        self.driver.close()

    def get_sample_nodes(self, kgdb_name='neo4j', num=50):
        """获取指定数据库的 num 个节点信息"""
        self.use_database(kgdb_name)
        def query(tx, num):
            result = tx.run("MATCH (n)-[r]->(m) RETURN n, r, m LIMIT $num", num=int(num))
            return result.values()

        with self.driver.session() as session:
            return session.execute_read(query, num)

    def create_graph_database(self, kgdb_name):
        """创建新的数据库，如果已存在则返回已有数据库的名称"""
        with self.driver.session() as session:
            existing_databases = session.run("SHOW DATABASES")
            existing_db_names = [db['name'] for db in existing_databases]

            if existing_db_names:
                print(f"已存在数据库: {existing_db_names[0]}")
                return existing_db_names[0]  # 返回所有已有数据库名称

            session.run(f"CREATE DATABASE {kgdb_name}")
            print(f"数据库 '{kgdb_name}' 创建成功.")
            return kgdb_name  # 返回创建的数据库名称

    def get_database_info(self, db_name="neo4j"):
        """获取指定数据库的信息"""
        self.use_database(db_name)
        def query(tx):
            entity_count = tx.run("MATCH (n) RETURN count(n) AS count").single()["count"]
            relationship_count = tx.run("MATCH ()-[r]->() RETURN count(r) AS count").single()["count"]
            triples_count = tx.run("MATCH (n)-[r]->(m) RETURN count(n) AS count").single()["count"]

            # 获取所有标签
            labels = tx.run("CALL db.labels() YIELD label RETURN collect(label) AS labels").single()["labels"]

            return {
                "database_name": db_name,
                "entity_count": entity_count,
                "relationship_count": relationship_count,
                "triples_count": triples_count,
                "labels": labels,
                "status": self.status
            }

        with self.driver.session() as session:
            return session.execute_read(query)

    def use_database(self, kgdb_name="neo4j"):
        """切换到指定数据库"""
        assert kgdb_name == self.kgdb_name, f"传入的数据库名称 '{kgdb_name}' 与当前实例的数据库名称 '{self.kgdb_name}' 不一致"
        if self.status == "closed":
            self.start()

    def txt_add_entity(self, triples, kgdb_name='neo4j'):
        """添加实体三元组"""
        self.use_database(kgdb_name)
        def create(tx, triples):
            for triple in triples:
                h = triple['h']
                t = triple['t']
                r = triple['r']
                query = (
                    "MERGE (a:Entity {name: $h}) "
                    "MERGE (b:Entity {name: $t}) "
                    "MERGE (a)-[:" + r.replace(" ", "_") + "]->(b)"
                )
                tx.run(query, h=h, t=t)

        with self.driver.session() as session:
            session.execute_write(create, triples)

    def pdf_file_add_entity(self, file_path, output_path, kgdb_name='neo4j'):
        self.use_database(kgdb_name)  # 切换到指定数据库
        text_path = pdf2txt(file_path)
        global UIE_MODEL
        if UIE_MODEL is None:
            UIE_MODEL = OneKE()
        triples_path = UIE_MODEL.processing_text_to_kg(text_path, output_path)
        self.jsonl_file_add_entity(triples_path)
        return kgdb_name

    def txt_add_vector_entity(self, triples, kgdb_name='neo4j'):
        """添加实体三元组"""
        self.use_database(kgdb_name)
        def _index_exists(tx, index_name):
            result = tx.run("SHOW INDEXES")
            for record in result:
                if record["name"] == index_name:
                    return True
            return False
        def _create_graph(tx, data):
            for entry in data:
                tx.run("""
                MERGE (h:Entity {name: $h})
                MERGE (t:Entity {name: $t})
                MERGE (h)-[r:RELATION {type: $r}]->(t)
                """, h=entry['h'], t=entry['t'], r=entry['r'])
        def _create_vector_index(tx, dim):
            index_name = "entityEmbeddings"
            if not _index_exists(tx, index_name):
                tx.run(f"""
                CREATE VECTOR INDEX {index_name}
                FOR (n: Entity) ON (n.embedding)
                OPTIONS {{indexConfig: {{
                `vector.dimensions`: {dim},
                `vector.similarity_function`: 'cosine'
                }} }};
                """)

        from src.config import EMBED_MODEL_INFO
        embed_info = EMBED_MODEL_INFO[self.config.embed_model]
        with self.driver.session() as session:
            session.execute_write(_create_graph, triples)
            session.execute_write(_create_vector_index, embed_info.get('dimension'))
            for i, entry in enumerate(triples):
                logger.info(f"Adding entity {i+1}/{len(triples)}")
                embedding_h = self.get_embedding(entry['h'])
                session.execute_write(self.set_embedding, entry['h'], embedding_h)

                embedding_t = self.get_embedding(entry['t'])
                session.execute_write(self.set_embedding, entry['t'], embedding_t)

    def jsonl_file_add_entity(self, file_path, kgdb_name='neo4j'):
        self.status = "processing"
        kgdb_name = kgdb_name or 'neo4j'
        self.use_database(kgdb_name)  # 切换到指定数据库

        def read_triples(file_path):
            with open(file_path, 'r', encoding='utf-8') as file:
                for line in file:
                    yield json.loads(line.strip())

        triples = list(read_triples(file_path))

        self.txt_add_vector_entity(triples, kgdb_name)

        self.status = "open"
        return kgdb_name

    def delete_entity(self, entity_name=None, kgdb_name="neo4j"):
        """删除数据库中的指定实体三元组, 参数entity_name为空则删除全部实体"""
        self.use_database(kgdb_name)
        with self.driver.session() as session:
            if entity_name:
                session.execute_write(self._delete_specific_entity, entity_name)
            else:
                session.execute_write(self._delete_all_entities)

    def _delete_specific_entity(self, tx, entity_name):
        query = """
        MATCH (n {name: $entity_name})
        DETACH DELETE n
        """
        tx.run(query, entity_name=entity_name)

    def _delete_all_entities(self, tx):
        query = """
        MATCH (n)
        DETACH DELETE n
        """
        tx.run(query)

    def query_node(self, entity_name, hops=2, **kwargs):
        # TODO 添加判断节点数量为 0 停止检索
        if kwargs.get("exact_match"):
            raise NotImplemented("not implement for `exact_match`")
        else:
            return self.query_by_vector(entity_name=entity_name, **kwargs)

    def query_by_vector(self, entity_name, threshold=0.9, kgdb_name='neo4j', hops=2, num_of_res=5):
        results = self.query_by_vector_tep(entity_name=entity_name)

        # 筛选出分数高于阈值的实体
        qualified_entities = [result[0] for result in results[:num_of_res] if result[1] > threshold]

        # 对每个合格的实体进行查询
        all_query_results = []
        for entity in qualified_entities:
            query_result = self.query_specific_entity(entity_name=entity, hops=hops, kgdb_name=kgdb_name)
            all_query_results.extend(query_result)

        return all_query_results

    def query_by_vector_tep(self, entity_name, kgdb_name='neo4j'):
        """向量查询"""
        self.use_database(kgdb_name)
        def query(tx, text):
            embedding = self.get_embedding(text)
            result = tx.run("""
            CALL db.index.vector.queryNodes('entityEmbeddings', 10, $embedding)
            YIELD node AS similarEntity, score
            RETURN similarEntity.name AS name, score
            """, embedding=embedding)
            return result.values()

        with self.driver.session() as session:
            return session.execute_read(query, entity_name)

    def query_specific_entity(self, entity_name, kgdb_name='neo4j', hops=2):
        """查询指定实体三元组信息"""
        self.use_database(kgdb_name)
        def query(tx, entity_name, hops):
            result = tx.run(f"""
            MATCH (n {{name: $entity_name}})-[r*1..{hops}]->(m)
            RETURN n.name AS node_name, r, m.name AS neighbor_name
            """, entity_name=entity_name)
            return result.values()

        with self.driver.session() as session:
            return session.execute_read(query, entity_name, hops)

    def query_all_nodes_and_relationships(self, kgdb_name='neo4j', hops = 2):
        """查询图数据库中所有三元组信息"""
        self.use_database(kgdb_name)
        def query(tx, hops):
            result = tx.run(f"""
            MATCH (n)-[r*1..{hops}]->(m)
            RETURN n, r, m
            """)
            return result.values()

        with self.driver.session() as session:
            return session.execute_read(query, hops)

    def query_by_relationship_type(self, relationship_type, kgdb_name='neo4j', hops = 2):
        """查询指定关系三元组信息"""
        self.use_database(kgdb_name)
        def query(tx, relationship_type, hops):
            result = tx.run(f"""
            MATCH (n)-[r:`{relationship_type}`*1..{hops}]->(m)
            RETURN n, r, m
            """)
            return result.values()

        with self.driver.session() as session:
            return session.execute_read(query, relationship_type, hops)

    def query_entity_like(self, keyword, kgdb_name='neo4j', hops = 2):
        """模糊查询"""
        self.use_database(kgdb_name)
        def query(tx, keyword, hops):
            result = tx.run(f"""
            MATCH (n:Entity)
            WHERE n.name CONTAINS $keyword
            MATCH (n)-[r*1..{hops}]->(m)
            RETURN n, r, m
            """, keyword=keyword)
            return result.values()

        with self.driver.session() as session:
            return session.execute_read(query, keyword, hops)

    def query_node_info(self, node_name, kgdb_name='neo4j', hops = 2):
        """查询指定节点的详细信息返回信息"""
        self.use_database(kgdb_name)  # 切换到指定数据库
        def query(tx, node_name, hops):
            result = tx.run(f"""
            MATCH (n {{name: $node_name}})
            OPTIONAL MATCH (n)-[r*1..{hops}]->(m)
            RETURN n, r, m
            """, node_name=node_name)
            return result.values()

        with self.driver.session() as session:
            return session.execute_read(query, node_name, hops)

    def get_embedding(self, text):
        inputs = [text]
        with torch.no_grad():
            outputs = self.embed_model.encode(inputs)
        embeddings = outputs[0] # 假设取平均作为文本的嵌入向量
        return embeddings

    def set_embedding(self, tx, entity_name, embedding):
        tx.run("""
        MATCH (e:Entity {name: $name})
        CALL db.create.setNodeVectorProperty(e, 'embedding', $embedding)
        """, name=entity_name, embedding=embedding)

    # def format_query_results(self, results):
    #     formatted_results = []
    #     for row in results:
    #         n, rs, m = row
    #         entity_a = n['name']
    #         entity_b = m['name']
    #         for rel in rs:
    #             relationship = rel.type
    #             formatted_results.append(f"实体 {entity_a} 和 实体 {entity_b} 的关系是 {relationship}")
    #     return formatted_results



if __name__ == "__main__":
    config = None

    kgdb_name = "neo4j"

    class EmbeddingModel(FlagModel):
        def __init__(self, config, **kwargs):

            model_name_or_path = "/data2024/yyyl/model/BAAI/bge-large-zh-v1.5/"

            super().__init__(model_name_or_path, use_fp16=False, **kwargs)


    model = EmbeddingModel(config)
    # 初始化知识图谱数据库
    kgdb = GraphDatabase(config, model)
    # 创建新的数据库
    # kgdb.create_graph_database("db2")

    # 返回指定数据库信息
    # info = kgdb.get_database_info(kgdb_name)
    # print(info)

    # triples = [
    #         {
    #             "h": "CCC",
    #             "t": "EE",
    #             "r": "同学"
    #         },
    #         {
    #             "h": "EE",
    #             "t": "RR",
    #             "r": "同事"
    #         }
    #         ]

    # kgdb.query_by_vector("z")
    # def format_query_results(results):
    #     formatted_results = {"nodes": [], "edges": []}

    #     # 用于存储所有唯一的节点信息
    #     node_dict = {}

    #     for item in results:
    #         # 确保item[1]是一个非空的列表
    #         if isinstance(item[1], list) and len(item[1]) > 0:
    #             relationship = item[1][0]
    #             rel_id = relationship.element_id
    #             nodes = relationship.nodes
    #             if len(nodes) == 2:
    #                 node1, node2 = nodes

    #                 # 提取源节点和目标节点信息
    #                 node1_id = node1.element_id
    #                 node2_id = node2.element_id
    #                 node1_name = item[0]  # 假设节点名称和列表中的第一个元素相同
    #                 node2_name = item[2] if len(item) > 2 else 'unknown'

    #                 # 记录节点信息
    #                 if node1_id not in node_dict:
    #                     node_dict[node1_id] = {"id": node1_id, "name": node1_name}
    #                 if node2_id not in node_dict:
    #                     node_dict[node2_id] = {"id": node2_id, "name": node2_name}

    #                 # 确定关系类型

    #                 relationship_type = relationship._properties.get('type', 'unknown')
    #                 if relationship_type == 'unknown':
    #                     relationship_type = relationship.type

    #                 # 记录边的信息
    #                 formatted_results["edges"].append({
    #                     "id": rel_id,
    #                     "type": relationship_type,
    #                     "source_id": node1_id,
    #                     "target_id": node2_id,
    #                     "source_name": node1_name,
    #                     "target_name": node2_name
    #                 })

    #     # 将唯一的节点信息添加到结果中
    #     formatted_results["nodes"] = list(node_dict.values())

    #     return formatted_results

    # entities = ['jqy', '维c']
    # results = []
    # for entitie in entities:
    #     result = kgdb.query_by_vector(entitie)
    #     if result != []:
    #         results.extend(result)
    # print(format_query_results(results))


    # kgdb.txt_add_vector_entity(triples, model)
    # print("Extend the Graph data base")

    # kgdb.jsonl_file_add_entity("/data2024/yyyl/ProjectAthena/tep.jsonl", kgdb_name)
    # print("Extend the Graph data base")

    # triples_path = "output.jsonl"
    # def read_triples(file_path):
    #     with open(file_path, 'r', encoding='utf-8') as file:
    #         for line in file:
    #             item = json.loads(line.strip())
    #             yield [item]
    # for trio in read_triples(triples_path):
    #     kgdb.txt_add_entity(trio)

    # 通过文件添加三元组数据
    # kgdb.file_add_entity("/data2024/yyyl/ProjectAthena/test.pdf", "/data2024/yyyl/ProjectAthena/output.jsonl", kgdb_name)
    # print("Extend the Graph data base")

    # 删除数据库信息
    # kgdb.delete_entity()
    # print("Clear the Graph data base")

    # 查询所有节点和关系
    # results = kgdb.query_all_nodes_and_relationships(kgdb_name)
    # print(results)

    # 查询特定实体及其关系
    # results = kgdb.query_specific_entity("kllll", kgdb_name)
    # print(results)

    # 查询特定实体及其关系
    # results = kgdb.query_by_vector_tep("z", model, tokenizer)
    # print(results)

    # 查询特定关系类型的所有节点
    # results = kgdb.query_by_relationship_type("作用或食用效果", kgdb_name)
    # print(results)

    # 模糊查询
    # results = kgdb.query_entity_like("三七", kgdb_name)
    # print(results)

    # 查询节点信息
    # results = kgdb.query_entity_like("三七提取物", kgdb_name)
    # print(results)

    # 关闭数据库连接
    kgdb.close()

