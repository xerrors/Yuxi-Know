import os
import json
from neo4j import GraphDatabase as GD
from plugins import pdf2txt, OneKE

class GraphDatabase:
    def __init__(self, config):
        self.config = config
        self.driver = None
        self.files = []
        self.status = "closed"

    def start(self):
        uri = os.environ.get("NEO4J_URI")
        username = os.environ.get("NEO4J_USERNAME")
        password = os.environ.get("NEO4J_PASSWORD")
        self.driver = GD.driver(uri, auth=(username, password))
        self.status = "open"

    def close(self):
        """关闭数据库连接"""
        self.driver.close()

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
            entity_count = tx.run("MATCH (n:Entity) RETURN count(n) AS count").single()["count"]
            relationship_count = tx.run("MATCH ()-[r]->() RETURN count(r) AS count").single()["count"]
            triples_count = tx.run("MATCH (n)-[r]->(m) RETURN count(n) AS count").single()["count"]
            return {
                "database_name": db_name,
                "entity_count": entity_count,
                "relationship_count": relationship_count,
                "triples_count": triples_count,
                "status": self.status
            }

        with self.driver.session() as session:
            return session.execute_read(query)

    def use_database(self, kgdb_name):
        """切换到指定数据库"""
        self.driver = GD.driver(f"{os.environ.get('NEO4J_URI')}/{kgdb_name}", auth=(os.environ.get('NEO4J_USERNAME'), os.environ.get('NEO4J_PASSWORD')))

    def txt_add_entity(self, triples, kgdb_name):
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

    def file_add_entity(self, file_path, output_path,kgdb_name):
        self.use_database(kgdb_name)  # 切换到指定数据库
        text_path = pdf2txt(file_path)
        oneke = OneKE()
        triples_path = oneke.processing_text_to_kg(text_path, output_path)
        def read_triples(file_path):
            with open(file_path, 'r', encoding='utf-8') as file:
                for line in file:
                    item = json.loads(line.strip())
                    yield [item]
        for trio in read_triples(triples_path):
            self.txt_add_entity(trio, kgdb_name)
        pass

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

    def query_all_nodes_and_relationships(self, kgdb_name, hops = 2):
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

    def query_specific_entity(self, entity_name, kgdb_name, hops = 2):
        """查询指定实体三元组信息"""
        self.use_database(kgdb_name)
        def query(tx, entity_name, hops):
            result = tx.run(f"""
            MATCH (n {{name: $entity_name}})-[r*1..{hops}]->(m)
            RETURN n, r, m
            """, entity_name=entity_name)
            return result.values()

        with self.driver.session() as session:
            return session.execute_read(query, entity_name, hops)

    def query_by_relationship_type(self, relationship_type, kgdb_name, hops = 2):
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

    def query_entity_like(self, keyword, kgdb_name, hops = 2):
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

    def query_node_info(self, node_name, kgdb_name, hops = 2):
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



if __name__ == "__main__":
    config = None
    # 初始化知识图谱数据库
    kgdb = GraphDatabase(config)
    kgdb_name = "neo4j"

    # 创建新的数据库
    # kgdb.create_graph_database("db2")

    # 返回指定数据库信息
    # info = kgdb.get_database_info(kgdb_name)
    # print(info)

    # 通过文本添加三元组数据
    # triples = [
    #         {
    #             "h": "莲子",
    #             "t": "生吃微甜，一煮就酥，食之软糯清香",
    #             "r": "用途"
    #         },
    #         {
    #             "h": "食用菌类",
    #             "t": "蔬菜",
    #             "r": "用途"
    #         },
    #         {
    #             "h": "野生蕈",
    #             "t": "食用菌",
    #             "r": "作用或食用效果"
    #         },
    #         {
    #             "h": "大白菜",
    #             "t": "选择耐贮的晚熟品种，如小青口、核桃纹、抱头青、拧心青等",
    #             "r": "贮存方法"
    #         },
    #         {
    #             "h": "大白菜",
    #             "t": "刚买回来的白菜，水分大，须晾晒三五天，白菜外叶失去部分水分发时，再撕去黄叶，堆码",
    #             "r": "贮存方法"
    #         }
    #         ]
    # kgdb.txt_add_entity(triples, kgdb_name)
    # print("Extend the Graph data base")

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
    # results = kgdb.query_specific_entity("三七提取物", kgdb_name)
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
