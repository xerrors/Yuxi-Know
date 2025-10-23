import json
import os
import traceback
import warnings

from neo4j import GraphDatabase as GD

from src import config
from src.models import select_embedding_model
from src.utils import logger
from src.utils.datetime_utils import utc_isoformat

warnings.filterwarnings("ignore", category=UserWarning)


UIE_MODEL = None


class GraphDatabase:
    def __init__(self):
        self.driver = None
        self.files = []
        self.status = "closed"
        self.kgdb_name = "neo4j"
        self.embed_model_name = os.getenv("GRAPH_EMBED_MODEL_NAME") or "siliconflow/BAAI/bge-m3"
        self.embed_model = select_embedding_model(self.embed_model_name)
        self.work_dir = os.path.join(config.save_dir, "knowledge_graph", self.kgdb_name)
        os.makedirs(self.work_dir, exist_ok=True)

        # 尝试加载已保存的图数据库信息
        if not self.load_graph_info():
            logger.debug("创建新的图数据库配置")

        self.start()

    def start(self):
        uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        username = os.environ.get("NEO4J_USERNAME", "neo4j")
        password = os.environ.get("NEO4J_PASSWORD", "0123456789")
        logger.info(f"Connecting to Neo4j: {uri}/{self.kgdb_name}")
        try:
            self.driver = GD.driver(f"{uri}/{self.kgdb_name}", auth=(username, password))
            self.status = "open"
            logger.info(f"Connected to Neo4j: {self.get_graph_info(self.kgdb_name)}")
            # 连接成功后保存图数据库信息
            self.save_graph_info(self.kgdb_name)
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}, {uri}, {self.kgdb_name}, {username}, {password}")

    def close(self):
        """关闭数据库连接"""
        assert self.driver is not None, "Database is not connected"
        self.driver.close()

    def is_running(self):
        """检查图数据库是否正在运行"""
        return self.status == "open" or self.status == "processing"

    def get_sample_nodes(self, kgdb_name="neo4j", num=50):
        """获取指定数据库的 num 个节点信息，优先返回连通的节点子图"""
        assert self.driver is not None, "Database is not connected"
        self.use_database(kgdb_name)

        def query(tx, num):
            """Note: 使用连通性查询获取集中的节点子图"""
            # 首先尝试获取一个连通的子图
            query_str = """
                // 获取高度数节点作为种子节点
                MATCH (seed:Entity)
                WITH seed, COUNT{(seed)-[]->()} + COUNT{(seed)<-[]-()} as degree
                WHERE degree > 0
                ORDER BY degree DESC
                LIMIT 5

                // 为每个种子节点收集更多邻居节点
                UNWIND seed as s
                MATCH (s)-[*1..1]-(neighbor:Entity)
                WITH s, neighbor, COUNT{(s)-[]->()} + COUNT{(s)<-[]-()} as s_degree
                WITH s, s_degree, collect(DISTINCT neighbor) as neighbors
                // 调整限制比例，允许更多的邻居节点
                WITH s, s_degree, neighbors[0..toInteger($num * 0.15)] as limited_neighbors

                // 从邻居节点扩展到二跳节点，形成开枝散叶结构
                UNWIND limited_neighbors as neighbor
                OPTIONAL MATCH (neighbor)-[*1..1]-(second_hop:Entity)
                WHERE second_hop <> s
                // 增加二跳节点的数量
                WITH s, limited_neighbors, neighbor, collect(DISTINCT second_hop)[0..5] as second_hops

                // 收集所有连通节点
                WITH collect(DISTINCT s) as seeds,
                    collect(DISTINCT neighbor) as first_hop_nodes,
                    reduce(acc = [], x IN collect(second_hops) | acc + x) as second_hop_nodes
                WITH seeds + first_hop_nodes + second_hop_nodes as connected_nodes

                // 确保不会超过请求的节点数量
                WITH connected_nodes[0..$num] as final_nodes

                // 获取这些节点之间的关系，避免双向边
                UNWIND final_nodes as n
                OPTIONAL MATCH (n)-[rel]-(m)
                WHERE m IN final_nodes AND elementId(n) < elementId(m)
                RETURN
                    {id: elementId(n), name: n.name} AS h,
                    CASE WHEN rel IS NOT NULL THEN
                        {type: rel.type, source_id: elementId(n), target_id: elementId(m)}
                    ELSE null END AS r,
                    CASE WHEN m IS NOT NULL THEN
                        {id: elementId(m), name: m.name}
                    ELSE null END AS t
                """

            try:
                results = tx.run(query_str, num=int(num))
                formatted_results = {"nodes": [], "edges": []}
                node_ids = set()

                for item in results:
                    h_node = item["h"]

                    # 始终添加头节点
                    if h_node["id"] not in node_ids:
                        formatted_results["nodes"].append(h_node)
                        node_ids.add(h_node["id"])

                    # 只有当边和尾节点都存在时才处理
                    if item["r"] is not None and item["t"] is not None:
                        t_node = item["t"]

                        # 避免重复添加尾节点
                        if t_node["id"] not in node_ids:
                            formatted_results["nodes"].append(t_node)
                            node_ids.add(t_node["id"])

                        formatted_results["edges"].append(item["r"])

                # 如果连通查询返回的节点数不足，补充更多节点
                if len(formatted_results["nodes"]) < num:
                    remaining_count = num - len(formatted_results["nodes"])

                    # 获取额外的节点来补充
                    supplement_query = """
                    MATCH (n:Entity)
                    WHERE NOT elementId(n) IN $existing_ids
                    RETURN {id: elementId(n), name: n.name} AS node
                    LIMIT $count
                    """

                    supplement_results = tx.run(supplement_query, existing_ids=list(node_ids), count=remaining_count)

                    for item in supplement_results:
                        node = item["node"]
                        formatted_results["nodes"].append(node)
                        node_ids.add(node["id"])

                return formatted_results

            except Exception as e:
                # 如果连通查询失败，使用原始查询作为备选
                logger.warning(f"Connected subgraph query failed, falling back to simple query: {e}")
                fallback_query = """
                MATCH (n:Entity)-[r]-(m:Entity)
                WHERE elementId(n) < elementId(m)
                RETURN
                    {id: elementId(n), name: n.name} AS h,
                    {type: r.type, source_id: elementId(n), target_id: elementId(m)} AS r,
                    {id: elementId(m), name: m.name} AS t
                LIMIT $num
                """
                results = tx.run(fallback_query, num=int(num))
                formatted_results = {"nodes": [], "edges": []}
                node_ids = set()

                for item in results:
                    h_node = item["h"]
                    t_node = item["t"]

                    # 避免重复添加节点
                    if h_node["id"] not in node_ids:
                        formatted_results["nodes"].append(h_node)
                        node_ids.add(h_node["id"])
                    if t_node["id"] not in node_ids:
                        formatted_results["nodes"].append(t_node)
                        node_ids.add(t_node["id"])

                    formatted_results["edges"].append(item["r"])

                return formatted_results

        with self.driver.session() as session:
            results = session.execute_read(query, num)
            return results

    def create_graph_database(self, kgdb_name):
        """创建新的数据库，如果已存在则返回已有数据库的名称"""
        assert self.driver is not None, "Database is not connected"
        with self.driver.session() as session:
            existing_databases = session.run("SHOW DATABASES")
            existing_db_names = [db["name"] for db in existing_databases]

            if existing_db_names:
                print(f"已存在数据库: {existing_db_names[0]}")
                return existing_db_names[0]  # 返回所有已有数据库名称

            session.run(f"CREATE DATABASE {kgdb_name}")  # type: ignore
            print(f"数据库 '{kgdb_name}' 创建成功.")
            return kgdb_name  # 返回创建的数据库名称

    def use_database(self, kgdb_name="neo4j"):
        """切换到指定数据库"""
        assert kgdb_name == self.kgdb_name, (
            f"传入的数据库名称 '{kgdb_name}' 与当前实例的数据库名称 '{self.kgdb_name}' 不一致"
        )
        if self.status == "closed":
            self.start()

    async def txt_add_vector_entity(self, triples, kgdb_name="neo4j"):
        """添加实体三元组"""
        assert self.driver is not None, "Database is not connected"
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
                tx.run(
                    """
                MERGE (h:Entity:Upload {name: $h})
                MERGE (t:Entity:Upload {name: $t})
                MERGE (h)-[r:RELATION {type: $r}]->(t)
                """,
                    h=entry["h"],
                    t=entry["t"],
                    r=entry["r"],
                )

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

        def _get_nodes_without_embedding(tx, entity_names):
            """获取没有embedding的节点列表"""
            # 构建参数字典，将列表转换为"param0"、"param1"等键值对形式
            params = {f"param{i}": name for i, name in enumerate(entity_names)}

            # 构建查询参数列表
            param_placeholders = ", ".join([f"${key}" for key in params.keys()])

            # 执行查询
            result = tx.run(
                f"""
            MATCH (n:Entity)
            WHERE n.name IN [{param_placeholders}] AND n.embedding IS NULL
            RETURN n.name AS name
            """,
                params,
            )

            return [record["name"] for record in result]

        def _batch_set_embeddings(tx, entity_embedding_pairs):
            """批量设置实体的嵌入向量"""
            for entity_name, embedding in entity_embedding_pairs:
                tx.run(
                    """
                MATCH (e:Entity {name: $name})
                CALL db.create.setNodeVectorProperty(e, 'embedding', $embedding)
                """,
                    name=entity_name,
                    embedding=embedding,
                )

        # 判断模型名称是否匹配
        self.embed_model_name = self.embed_model_name or config.embed_model
        cur_embed_info = config.embed_model_names.get(self.embed_model_name)
        logger.warning(f"embed_model_name={self.embed_model_name}, {cur_embed_info=}")
        assert self.embed_model_name == config.embed_model or self.embed_model_name is None, (
            f"embed_model_name={self.embed_model_name}, {config.embed_model=}"
        )

        with self.driver.session() as session:
            logger.info(f"Adding entity to {kgdb_name}")
            session.execute_write(_create_graph, triples)
            logger.info(f"Creating vector index for {kgdb_name} with {config.embed_model}")
            session.execute_write(_create_vector_index, getattr(cur_embed_info, "dimension", 1024))

            # 收集所有需要处理的实体名称，去重
            all_entities = []
            for entry in triples:
                if entry["h"] not in all_entities:
                    all_entities.append(entry["h"])
                if entry["t"] not in all_entities:
                    all_entities.append(entry["t"])

            # 筛选出没有embedding的节点
            nodes_without_embedding = session.execute_read(_get_nodes_without_embedding, all_entities)
            if not nodes_without_embedding:
                logger.info("所有实体已有embedding，无需重新计算")
                return

            logger.info(f"需要为{len(nodes_without_embedding)}/{len(all_entities)}个实体计算embedding")

            # 批量处理实体
            max_batch_size = 1024  # 限制此部分的主要是内存大小 1024 * 1024 * 4 / 1024 / 1024 = 4GB
            total_entities = len(nodes_without_embedding)

            for i in range(0, total_entities, max_batch_size):
                batch_entities = nodes_without_embedding[i : i + max_batch_size]
                logger.debug(
                    f"Processing entities batch {i // max_batch_size + 1}/"
                    f"{(total_entities - 1) // max_batch_size + 1} ({len(batch_entities)} entities)"
                )

                # 批量获取嵌入向量
                batch_embeddings = await self.aget_embedding(batch_entities)

                # 将实体名称和嵌入向量配对
                entity_embedding_pairs = list(zip(batch_entities, batch_embeddings))

                # 批量写入数据库
                session.execute_write(_batch_set_embeddings, entity_embedding_pairs)

            # 数据添加完成后保存图信息
            self.save_graph_info()

    async def jsonl_file_add_entity(self, file_path, kgdb_name="neo4j"):
        assert self.driver is not None, "Database is not connected"
        self.status = "processing"
        kgdb_name = kgdb_name or "neo4j"
        self.use_database(kgdb_name)  # 切换到指定数据库
        logger.info(f"Start adding entity to {kgdb_name} with {file_path}")

        def read_triples(file_path):
            with open(file_path, encoding="utf-8") as file:
                for line in file:
                    if line.strip():
                        yield json.loads(line.strip())

        triples = list(read_triples(file_path))

        await self.txt_add_vector_entity(triples, kgdb_name)

        self.status = "open"
        # 更新并保存图数据库信息
        self.save_graph_info()
        return kgdb_name

    def delete_entity(self, entity_name=None, kgdb_name="neo4j"):
        """删除数据库中的指定实体三元组, 参数entity_name为空则删除全部实体"""
        assert self.driver is not None, "Database is not connected"
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

    def query_node(
        self, keyword, threshold=0.9, kgdb_name="neo4j", hops=2, max_entities=8, return_format="graph", **kwargs
    ):
        """知识图谱查询节点的入口:"""
        assert self.driver is not None, "Database is not connected"
        assert self.is_running(), "图数据库未启动"

        self.use_database(kgdb_name)

        # 简单空格分词，OR 聚合
        tokens = [t for t in str(keyword).split(" ") if t]
        if not tokens:
            tokens = [str(keyword)]

        # name -> score 聚合；向量分数累加，模糊命中给予轻权重
        entity_to_score = {}
        for token in tokens:
            # 使用向量索引进行查询
            results_sim = self._query_with_vector_sim(token, kgdb_name, threshold)
            for r in results_sim:
                name = r[0]  # 与下方保持统一的 [0] 取 name 的方式
                score = 0.0
                try:
                    score = float(r["score"])  # neo4j.Record 支持键访问
                except Exception:
                    # 兜底：若无法取到score，给个基础分
                    score = 0.5
                entity_to_score[name] = max(entity_to_score.get(name, 0.0), score)

            # 模糊查询（不区分大小写），命中加一个较小分
            results_fuzzy = self._query_with_fuzzy_match(token, kgdb_name)
            for fr in results_fuzzy:
                # _query_with_fuzzy_match 返回 values()，形如 [name]
                name = fr[0]
                # 给予轻权重，避免覆盖向量高分
                entity_to_score[name] = max(entity_to_score.get(name, 0.0), 0.3)

        # 排序并截断
        qualified_entities = [name for name, _ in sorted(entity_to_score.items(), key=lambda x: x[1], reverse=True)][
            :max_entities
        ]

        logger.debug(f"Graph Query Entities: {keyword}, {qualified_entities=}")

        # 对每个合格的实体进行查询
        all_query_results = {"nodes": [], "edges": [], "triples": []}
        for entity in qualified_entities:
            query_result = self._query_specific_entity(entity_name=entity, kgdb_name=kgdb_name, hops=hops)
            if return_format == "graph":
                all_query_results["nodes"].extend(query_result["nodes"])
                all_query_results["edges"].extend(query_result["edges"])
            elif return_format == "triples":
                all_query_results["triples"].extend(query_result["triples"])
            else:
                raise ValueError(f"Invalid return_format: {return_format}")

        # 基础去重
        if return_format == "graph":
            seen_node_ids = set()
            dedup_nodes = []
            for n in all_query_results["nodes"]:
                nid = n.get("id") if isinstance(n, dict) else n
                if nid not in seen_node_ids:
                    seen_node_ids.add(nid)
                    dedup_nodes.append(n)
            all_query_results["nodes"] = dedup_nodes

            seen_edges = set()
            dedup_edges = []
            for e in all_query_results["edges"]:
                key = (e.get("source_id"), e.get("target_id"), e.get("type"))
                if key not in seen_edges:
                    seen_edges.add(key)
                    dedup_edges.append(e)
            all_query_results["edges"] = dedup_edges

        elif return_format == "triples":
            seen_triples = set()
            dedup_triples = []
            for t in all_query_results["triples"]:
                if t not in seen_triples:
                    seen_triples.add(t)
                    dedup_triples.append(t)
            all_query_results["triples"] = dedup_triples

        return all_query_results

    def _query_with_fuzzy_match(self, keyword, kgdb_name="neo4j"):
        """模糊查询"""
        assert self.driver is not None, "Database is not connected"
        self.use_database(kgdb_name)

        def query_fuzzy_match(tx, keyword):
            result = tx.run(
                """
            MATCH (n:Entity)
            WHERE toLower(n.name) CONTAINS toLower($keyword)
            RETURN DISTINCT n.name AS name
            """,
                keyword=keyword,
            )
            values = result.values()
            logger.debug(f"Fuzzy Query Results: {values}")
            return values

        with self.driver.session() as session:
            return session.execute_read(query_fuzzy_match, keyword)

    def _query_with_vector_sim(self, keyword, kgdb_name="neo4j", threshold=0.9):
        """向量查询"""
        assert self.driver is not None, "Database is not connected"
        self.use_database(kgdb_name)

        def _index_exists(tx, index_name):
            """检查索引是否存在"""
            result = tx.run("SHOW INDEXES")
            for record in result:
                if record["name"] == index_name:
                    return True
            return False

        def query_by_vector(tx, text, threshold):
            # 首先检查索引是否存在
            if not _index_exists(tx, "entityEmbeddings"):
                raise Exception(
                    "向量索引不存在，请先创建索引，或当前图谱中未上传任何三元组（知识库中自动构建的，不会在此处展示和检索）。"
                )

            embedding = self.get_embedding(text)
            result = tx.run(
                """
            CALL db.index.vector.queryNodes('entityEmbeddings', 10, $embedding)
            YIELD node AS similarEntity, score
            RETURN similarEntity.name AS name, score
            """,
                embedding=embedding,
            )
            return [r for r in result if r["score"] > threshold]

        with self.driver.session() as session:
            results = session.execute_read(query_by_vector, keyword, threshold=threshold)
            return results

    def _query_specific_entity(self, entity_name, kgdb_name="neo4j", hops=2, limit=100):
        """查询指定实体三元组信息（无向关系）"""
        assert self.driver is not None, "Database is not connected"
        if not entity_name:
            logger.warning("实体名称为空")
            return []

        self.use_database(kgdb_name)

        def query(tx, entity_name, hops, limit):
            try:
                query_str = """
                WITH [
                    // 1跳出边
                    [(n {name: $entity_name})-[r1]->(m1) |
                     {h: {id: elementId(n), name: n.name},
                      r: {type: r1.type, source_id: elementId(n), target_id: elementId(m1)},
                      t: {id: elementId(m1), name: m1.name}}],
                    // 2跳出边
                    [(n {name: $entity_name})-[r1]->(m1)-[r2]->(m2) |
                     {h: {id: elementId(m1), name: m1.name},
                      r: {type: r2.type, source_id: elementId(m1), target_id: elementId(m2)},
                      t: {id: elementId(m2), name: m2.name}}],
                    // 1跳入边
                    [(m1)-[r1]->(n {name: $entity_name}) |
                     {h: {id: elementId(m1), name: m1.name},
                      r: {type: r1.type, source_id: elementId(m1), target_id: elementId(n)},
                      t: {id: elementId(n), name: n.name}}],
                    // 2跳入边
                    [(m2)-[r2]->(m1)-[r1]->(n {name: $entity_name}) |
                     {h: {id: elementId(m2), name: m2.name},
                      r: {type: r2.type, source_id: elementId(m2), target_id: elementId(m1)},
                      t: {id: elementId(m1), name: m1.name}}]
                ] AS all_results
                UNWIND all_results AS result_list
                UNWIND result_list AS item
                RETURN item.h AS h, item.r AS r, item.t AS t
                LIMIT $limit
                """
                results = tx.run(query_str, entity_name=entity_name, limit=limit)

                if not results:
                    logger.info(f"未找到实体 {entity_name} 的相关信息")
                    return {}

                formatted_results = {"nodes": [], "edges": [], "triples": []}

                for item in results:
                    formatted_results["nodes"].extend([item["h"], item["t"]])
                    formatted_results["edges"].append(item["r"])
                    formatted_results["triples"].append((item["h"]["name"], item["r"]["type"], item["t"]["name"]))

                logger.debug(f"Query Results: {results}")
                return formatted_results

            except Exception as e:
                logger.error(f"查询实体 {entity_name} 失败: {str(e)}")
                return []

        try:
            with self.driver.session() as session:
                return session.execute_read(query, entity_name, hops, limit)

        except Exception as e:
            logger.error(f"数据库会话异常: {str(e)}")
            return []

    async def aget_embedding(self, text):
        if isinstance(text, list):
            outputs = await self.embed_model.abatch_encode(text, batch_size=40)
            return outputs
        else:
            outputs = await self.embed_model.aencode(text)
            return outputs

    def get_embedding(self, text):
        if isinstance(text, list):
            outputs = self.embed_model.batch_encode(text, batch_size=40)
            return outputs
        else:
            outputs = self.embed_model.encode([text])[0]
            return outputs

    def set_embedding(self, tx, entity_name, embedding):
        tx.run(
            """
        MATCH (e:Entity {name: $name})
        CALL db.create.setNodeVectorProperty(e, 'embedding', $embedding)
        """,
            name=entity_name,
            embedding=embedding,
        )

    def get_graph_info(self, graph_name="neo4j"):
        assert self.driver is not None, "Database is not connected"
        self.use_database(graph_name)

        def query(tx):
            # 只统计包含Entity标签的节点
            entity_count = tx.run("MATCH (n:Entity) RETURN count(n) AS count").single()["count"]
            # 只统计包含RELATION标签的关系
            relationship_count = tx.run("MATCH ()-[r:RELATION]->() RETURN count(r) AS count").single()["count"]
            triples_count = tx.run("MATCH (n:Entity)-[r:RELATION]->(m:Entity) RETURN count(n) AS count").single()[
                "count"
            ]

            # 获取所有标签
            labels = tx.run("CALL db.labels() YIELD label RETURN collect(label) AS labels").single()["labels"]

            return {
                "graph_name": graph_name,
                "entity_count": entity_count,
                "relationship_count": relationship_count,
                "triples_count": triples_count,
                "labels": labels,
                "status": self.status,
                "embed_model_name": self.embed_model_name,
                "unindexed_node_count": len(self.query_nodes_without_embedding(graph_name)),
            }

        try:
            if self.is_running():
                # 获取数据库信息
                with self.driver.session() as session:
                    graph_info = session.execute_read(query)

                    # 添加时间戳
                    graph_info["last_updated"] = utc_isoformat()
                    return graph_info
            else:
                logger.warning(f"图数据库未连接或未运行:{self.status=}")
                return None

        except Exception as e:
            logger.error(f"获取图数据库信息失败：{e}, {traceback.format_exc()}")
            return None

    def save_graph_info(self, graph_name="neo4j"):
        """
        将图数据库的基本信息保存到工作目录中的JSON文件
        保存的信息包括：数据库名称、状态、嵌入模型名称等
        """
        try:
            graph_info = self.get_graph_info(graph_name)
            if graph_info is None:
                logger.error("图数据库信息为空，无法保存")
                return False

            info_file_path = os.path.join(self.work_dir, "graph_info.json")
            with open(info_file_path, "w", encoding="utf-8") as f:
                json.dump(graph_info, f, ensure_ascii=False, indent=2)

            # logger.info(f"图数据库信息已保存到：{info_file_path}")
            return True
        except Exception as e:
            logger.error(f"保存图数据库信息失败：{e}")
            return False

    def query_nodes_without_embedding(self, kgdb_name="neo4j"):
        """查询没有嵌入向量的节点

        Returns:
            list: 没有嵌入向量的节点列表
        """
        assert self.driver is not None, "Database is not connected"
        self.use_database(kgdb_name)

        def query(tx):
            result = tx.run("""
            MATCH (n:Entity)
            WHERE n.embedding IS NULL
            RETURN n.name AS name
            """)
            return [record["name"] for record in result]

        with self.driver.session() as session:
            return session.execute_read(query)

    def load_graph_info(self):
        """
        从工作目录中的JSON文件加载图数据库的基本信息
        返回True表示加载成功，False表示加载失败
        """
        try:
            info_file_path = os.path.join(self.work_dir, "graph_info.json")
            if not os.path.exists(info_file_path):
                logger.debug(f"图数据库信息文件不存在：{info_file_path}")
                return False

            with open(info_file_path, encoding="utf-8") as f:
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

    def add_embedding_to_nodes(self, node_names=None, kgdb_name="neo4j"):
        """为节点添加嵌入向量

        Args:
            node_names (list, optional): 要添加嵌入向量的节点名称列表，None表示所有没有嵌入向量的节点
            kgdb_name (str, optional): 图数据库名称，默认为'neo4j'

        Returns:
            int: 成功添加嵌入向量的节点数量
        """
        assert self.driver is not None, "Database is not connected"
        self.use_database(kgdb_name)

        # 如果node_names为None，则获取所有没有嵌入向量的节点
        if node_names is None:
            node_names = self.query_nodes_without_embedding(kgdb_name)

        count = 0
        with self.driver.session() as session:
            for node_name in node_names:
                try:
                    embedding = self.get_embedding(node_name)
                    session.execute_write(self.set_embedding, node_name, embedding)
                    count += 1
                except Exception as e:
                    logger.error(f"为节点 '{node_name}' 添加嵌入向量失败: {e}, {traceback.format_exc()}")

        return count

    def format_general_results(self, results):
        nodes = []
        edges = []

        for item in results:
            nodes.extend([item["h"], item["t"]])
            edges.append(item["r"])

        formatted_results = {"nodes": nodes, "edges": edges}
        return formatted_results

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

        # 如果没有提供 source_name 或 target_name，则需要 node_dict
        if source_name is None or target_name is None:
            assert node_dict is not None, "node_dict is required when source_name or target_name is None"
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


def clean_triples_embedding(triples):
    for item in triples:
        if hasattr(item[0], "_properties"):
            item[0]._properties["embedding"] = None
        if hasattr(item[2], "_properties"):
            item[2]._properties["embedding"] = None
    return triples


if __name__ == "__main__":
    pass
