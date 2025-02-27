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
from src.utils import logger

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
        self.embed_model_name = None
        self.work_dir = os.path.join(config.save_dir, "knowledge_graph", kgdb_name)
        os.makedirs(self.work_dir, exist_ok=True)

        # 尝试加载已保存的图数据库信息
        if self.load_graph_info():
            logger.info(f"已加载图数据库信息：{self.kgdb_name}")
        else:
            logger.info(f"未找到已保存的图数据库信息，将创建新的配置")

        self.start()

    def start(self):
        uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        username = os.environ.get("NEO4J_USERNAME", "neo4j")
        password = os.environ.get("NEO4J_PASSWORD", "0123456789")
        logger.info(f"Connecting to Neo4j at {uri}/{self.kgdb_name}")
        try:
            self.driver = GD.driver(f"{uri}/{self.kgdb_name}", auth=(username, password))
            self.status = "open"
            logger.info(f"Connected to Neo4j at {uri}/{self.kgdb_name}, {self.get_database_info()}")
            # 连接成功后保存图数据库信息
            self.save_graph_info()
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
                "status": self.status,
                "embed_model_name": self.embed_model_name
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

    # def pdf_file_add_entity(self, file_path, output_path, kgdb_name='neo4j'):
    #     self.use_database(kgdb_name)  # 切换到指定数据库
    #     text_path = pdf2txt(file_path)
    #     global UIE_MODEL
    #     if UIE_MODEL is None:
    #         UIE_MODEL = OneKE()
    #     triples_path = UIE_MODEL.processing_text_to_kg(text_path, output_path)
    #     self.jsonl_file_add_entity(triples_path)
    #     return kgdb_name

    def txt_add_vector_entity(self, triples, kgdb_name='neo4j'):
        """添加实体三元组"""
        self.use_database(kgdb_name)
        def _index_exists(tx, index_name):
            """检查索引是否存在"""
            result = tx.run("SHOW INDEXES")
            for record in result:
                if record["name"] == index_name:
                    return True
            return False

        def _create_graph(tx, data):
            """添加一个三元组"""
            for entry in data:
                tx.run("""
                MERGE (h:Entity {name: $h})
                MERGE (t:Entity {name: $t})
                MERGE (h)-[r:RELATION {type: $r}]->(t)
                """, h=entry['h'], t=entry['t'], r=entry['r'])

        def _create_vector_index(tx, dim):
            """创建向量索引"""
            # NOTE 这里是否是会重复构建索引？
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

        # 判断模型名称是否匹配
        from src.config import EMBED_MODEL_INFO
        cur_embed_info = EMBED_MODEL_INFO[self.config.embed_model]
        self.embed_model_name = self.embed_model_name or cur_embed_info.get('name')
        assert self.embed_model_name == cur_embed_info.get('name') or self.embed_model_name is None, \
            f"embed_model_name={self.embed_model_name}, {cur_embed_info.get('name')=}"

        with self.driver.session() as session:
            logger.info(f"Adding entity to {kgdb_name}")
            session.execute_write(_create_graph, triples)
            logger.info(f"Creating vector index for {kgdb_name} with {self.config.embed_model}")
            session.execute_write(_create_vector_index, cur_embed_info['dimension'])
            # NOTE 这里需要异步处理
            for i, entry in enumerate(triples):
                logger.debug(f"Adding entity {i+1}/{len(triples)}")
                embedding_h = self.get_embedding(entry['h'])
                embedding_t = self.get_embedding(entry['t'])
                session.execute_write(self.set_embedding, entry['h'], embedding_h)
                session.execute_write(self.set_embedding, entry['t'], embedding_t)

            # 数据添加完成后保存图信息
            self.save_graph_info()

    def jsonl_file_add_entity(self, file_path, kgdb_name='neo4j'):
        self.status = "processing"
        kgdb_name = kgdb_name or 'neo4j'
        self.use_database(kgdb_name)  # 切换到指定数据库
        logger.info(f"Start adding entity to {kgdb_name} with {file_path}")

        def read_triples(file_path):
            with open(file_path, 'r', encoding='utf-8') as file:
                for line in file:
                    yield json.loads(line.strip())

        triples = list(read_triples(file_path))

        self.txt_add_vector_entity(triples, kgdb_name)

        self.status = "open"
        # 更新并保存图数据库信息
        self.save_graph_info()
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

        logger.debug(f"Query graph node {entity_name} with {hops=}")
        if kwargs.get("exact_match"):
            raise NotImplemented("not implement for `exact_match`")
        else:
            return self.query_by_vector(entity_name=entity_name, **kwargs)

    def query_by_vector(self, entity_name, threshold=0.9, kgdb_name='neo4j', hops=2, num_of_res=5):
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
            results = session.execute_read(query, entity_name)


        # 筛选出分数高于阈值的实体
        qualified_entities = [result[0] for result in results[:num_of_res] if result[1] > threshold]
        logger.debug(f"Graph Query Entities: {entity_name}, {qualified_entities=}")

        # 对每个合格的实体进行查询
        all_query_results = []
        for entity in qualified_entities:
            query_result = self.query_specific_entity(entity_name=entity, hops=hops, kgdb_name=kgdb_name)
            all_query_results.extend(query_result)

        return all_query_results

    def query_specific_entity(self, entity_name, kgdb_name='neo4j', hops=2):
        """查询指定实体三元组信息（无向关系）"""
        self.use_database(kgdb_name)
        def query(tx, entity_name, hops):
            result = tx.run(f"""
            MATCH (n {{name: $entity_name}})-[r*1..{hops}]-(m)
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
        with torch.no_grad():
            outputs = self.embed_model.encode([text])[0]
            return outputs

    def set_embedding(self, tx, entity_name, embedding):
        tx.run("""
        MATCH (e:Entity {name: $name})
        CALL db.create.setNodeVectorProperty(e, 'embedding', $embedding)
        """, name=entity_name, embedding=embedding)

    def save_graph_info(self):
        """
        将图数据库的基本信息保存到工作目录中的JSON文件
        保存的信息包括：数据库名称、状态、嵌入模型名称等
        """
        try:
            # 获取数据库信息
            db_info = None
            if self.status == "open" and self.driver:
                try:
                    db_info = self.get_database_info(self.kgdb_name)
                except Exception as e:
                    logger.warning(f"无法获取数据库信息：{e}")

            # 构建要保存的信息字典
            graph_info = {
                "kgdb_name": self.kgdb_name,
                "status": self.status,
                "embed_model_name": self.embed_model_name,
                "last_updated": None,  # 这里可以添加时间戳
                "database_info": db_info
            }

            # 添加时间戳
            from datetime import datetime
            graph_info["last_updated"] = datetime.now().isoformat()

            # 保存到JSON文件
            info_file_path = os.path.join(self.work_dir, "graph_info.json")
            with open(info_file_path, 'w', encoding='utf-8') as f:
                json.dump(graph_info, f, ensure_ascii=False, indent=2)

            logger.info(f"图数据库信息已保存到：{info_file_path}")
            return True
        except Exception as e:
            logger.error(f"保存图数据库信息失败：{e}")
            return False

    def load_graph_info(self):
        """
        从工作目录中的JSON文件加载图数据库的基本信息
        返回True表示加载成功，False表示加载失败
        """
        try:
            info_file_path = os.path.join(self.work_dir, "graph_info.json")
            if not os.path.exists(info_file_path):
                logger.warning(f"图数据库信息文件不存在：{info_file_path}")
                return False

            with open(info_file_path, 'r', encoding='utf-8') as f:
                graph_info = json.load(f)

            # 更新对象属性
            if graph_info.get("embed_model_name"):
                self.embed_model_name = graph_info["embed_model_name"]

            # 如果需要，可以加载更多信息
            # 注意：这里不更新self.kgdb_name，因为它是在初始化时设置的

            logger.info(f"已加载图数据库信息，最后更新时间：{graph_info.get('last_updated')}")
            return True
        except Exception as e:
            logger.error(f"加载图数据库信息失败：{e}")
            return False


if __name__ == "__main__":
    pass