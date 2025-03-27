from neo4j import GraphDatabase
import json

class Neo4jLoader:
    def __init__(self, uri="bolt://localhost:7687", username="neo4j", password="0123456789"):
        self.driver = GraphDatabase.driver(uri, auth=(username, password))

    def close(self):
        self.driver.close()

    def add_relationship(self, head, relation, tail):
        with self.driver.session() as session:
            # 使用 MERGE 而不是 CREATE 来避免重复节点
            cypher_query = (
                "MERGE (h:Node {name: $head}) "
                "MERGE (t:Node {name: $tail}) "
                "MERGE (h)-[r:" + relation + "]->(t)"
            )
            session.run(cypher_query, head=head, tail=tail)

def load_jsonl(file_path, loader):
    with open(file_path, 'r', encoding='utf-8') as f:
        line_number = 0
        for line in f:
            line_number += 1
            line = line.strip()
            if not line:  # 跳过空行
                continue
            try:
                data = json.loads(line)
                loader.add_relationship(data['h'], data['r'], data['t'])
            except json.JSONDecodeError as e:
                print(f"第 {line_number} 行JSON格式错误: {e}")
                print(f"问题行内容: {line}")
            except KeyError as e:
                print(f"第 {line_number} 行缺少必要的键: {e}")
                print(f"问题行内容: {line}")

def main():
    # 连接到Neo4j数据库
    loader = Neo4jLoader()

    try:
        # 加载数据
        load_jsonl('test/data/citys.jsonl', loader)
        print("数据已成功导入Neo4j")
    except Exception as e:
        print(f"导入过程中出现错误: {str(e)}")
    finally:
        loader.close()

if __name__ == "__main__":
    main()
