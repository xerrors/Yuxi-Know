import json
import os
import tempfile
import traceback
import warnings
from urllib.parse import urlparse

from src import config
from src.knowledge.adapters.base import Neo4jConnectionManager
from src.models import select_embedding_model
from src.storage.minio.client import get_minio_client
from src.utils import logger
from src.utils.datetime_utils import utc_isoformat

warnings.filterwarnings("ignore", category=UserWarning)


class UploadGraphService:
    """
    Upload 类型图谱业务逻辑服务
    专门处理用户上传文件、实体管理、向量索引等业务逻辑
    """

    def __init__(self, db_manager: Neo4jConnectionManager = None):
        self.connection = db_manager or Neo4jConnectionManager()
        self.files = []
        self.kgdb_name = "neo4j"
        self.embed_model_name = None  # self.load_graph_info() 时加载
        self.embed_model = None  # self.load_graph_info() 时加载
        self.work_dir = os.path.join(config.save_dir, "knowledge_graph", self.kgdb_name)
        os.makedirs(self.work_dir, exist_ok=True)
        self.is_initialized_from_file = False

        # 尝试加载已保存的图数据库信息
        if not self.load_graph_info():
            logger.debug("创建新的图数据库配置")

    @property
    def driver(self):
        """获取数据库驱动"""
        return self.connection.driver

    @property
    def status(self):
        """获取连接状态"""
        return self.connection.status

    def start(self):
        """启动连接"""
        # Neo4jConnectionManager 在初始化时已经自动连接
        if not self.connection.is_running():
            self.connection._connect()
            logger.info(f"Connected to Neo4j: {self.get_graph_info(self.kgdb_name)}")

    def close(self):
        """关闭数据库连接"""
        self.connection.close()

    def is_running(self):
        """检查图数据库是否正在运行"""
        return self.connection.is_running()

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

    async def jsonl_file_add_entity(self, file_path, kgdb_name="neo4j", embed_model_name=None, batch_size=None):
        """从JSONL文件添加实体三元组到Neo4j"""
        assert self.driver is not None, "Database is not connected"
        self.connection.status = "processing"
        kgdb_name = kgdb_name or "neo4j"
        self.use_database(kgdb_name)  # 切换到指定数据库
        logger.info(f"Start adding entity to {kgdb_name} with {file_path}")

        # 检测 file_path 是否是 URL
        parsed_url = urlparse(file_path)

        try:
            if parsed_url.scheme in ("http", "https"):  # 如果是 URL
                logger.info(f"检测到 URL，正在从 MinIO 下载文件: {file_path}")

                # 使用知识库的方式：直接解析 URL 并使用内部 endpoint 下载（避免 HOST_IP 配置问题）
                from src.knowledge.utils.kb_utils import parse_minio_url

                bucket_name, object_name = parse_minio_url(file_path)
                minio_client = get_minio_client()

                # 直接下载文件内容
                file_data = await minio_client.adownload_file(bucket_name, object_name)
                logger.info(f"成功从 MinIO 下载文件: {object_name} ({len(file_data)} bytes)")

                # 创建临时文件
                with tempfile.NamedTemporaryFile(mode="wb", suffix=".jsonl", delete=False) as temp_file:
                    temp_file.write(file_data)
                    actual_file_path = temp_file.name

                try:

                    def read_triples(file_path):
                        with open(file_path, encoding="utf-8") as file:
                            for line in file:
                                if line.strip():
                                    yield json.loads(line.strip())

                    triples = list(read_triples(actual_file_path))
                    await self.txt_add_vector_entity(triples, kgdb_name, embed_model_name, batch_size)
                finally:
                    # 清理临时文件
                    if os.path.exists(actual_file_path):
                        os.unlink(actual_file_path)

            else:
                # 本地文件路径 - 拒绝不安全的本地路径
                raise ValueError("不支持本地文件路径，只允许 MinIO URL。请先通过文件上传接口上传文件。")

        except Exception as e:
            logger.error(f"处理文件失败: {e}")
            raise
        finally:
            self.connection.status = "open"

        # 更新并保存图数据库信息
        self.save_graph_info()
        return kgdb_name

    async def txt_add_vector_entity(self, triples, kgdb_name="neo4j", embed_model_name=None, batch_size=None):
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

        def _parse_node(node_data):
            """解析节点数据，返回 (name, props)"""
            if isinstance(node_data, dict):
                props = node_data.copy()
                name = props.pop("name", "")
                return name, props
            return str(node_data), {}

        def _parse_relation(rel_data):
            """解析关系数据，返回 (type, props)"""
            if isinstance(rel_data, dict):
                props = rel_data.copy()
                rel_type = props.pop("type", "")
                return rel_type, props
            return str(rel_data), {}

        def _create_graph(tx, data):
            """添加一个三元组"""
            for entry in data:
                h_name, h_props = _parse_node(entry.get("h"))
                t_name, t_props = _parse_node(entry.get("t"))
                r_type, r_props = _parse_relation(entry.get("r"))

                if not h_name or not t_name or not r_type:
                    continue

                tx.run(
                    """
                MERGE (h:Entity:Upload {name: $h_name})
                SET h += $h_props
                MERGE (t:Entity:Upload {name: $t_name})
                SET t += $t_props
                MERGE (h)-[r:RELATION {type: $r_type}]->(t)
                SET r += $r_props
                """,
                    h_name=h_name,
                    h_props=h_props,
                    t_name=t_name,
                    t_props=t_props,
                    r_type=r_type,
                    r_props=r_props,
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

            if not params:
                return []

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

        # 检查是否允许更新模型
        if embed_model_name and not self.is_initialized_from_file:
            if embed_model_name != self.embed_model_name:
                logger.info(f"Changing embedding model from {self.embed_model_name} to {embed_model_name}")
                self.embed_model_name = embed_model_name
                self.embed_model = select_embedding_model(self.embed_model_name)

        # 判断模型名称是否匹配
        if not self.embed_model_name:
            self.embed_model_name = config.embed_model

        cur_embed_info = config.embed_model_names.get(self.embed_model_name)
        logger.warning(f"embed_model_name={self.embed_model_name}, {cur_embed_info=}")

        # 允许 self.embed_model_name 与 config.embed_model 不同（用户自定义选择的情况）
        # 但必须在支持的模型列表中
        assert self.embed_model_name in config.embed_model_names, f"Unsupported embed model: {self.embed_model_name}"

        with self.driver.session() as session:
            logger.info(f"Adding entity to {kgdb_name}")
            session.execute_write(_create_graph, triples)
            logger.info(f"Creating vector index for {kgdb_name} with {config.embed_model}")
            session.execute_write(_create_vector_index, getattr(cur_embed_info, "dimension", 1024))

            # 收集所有需要处理的实体名称，去重
            all_entities = set()
            for entry in triples:
                h_name, _ = _parse_node(entry.get("h"))
                t_name, _ = _parse_node(entry.get("t"))
                if h_name:
                    all_entities.add(h_name)
                if t_name:
                    all_entities.add(t_name)

            all_entities_list = list(all_entities)

            # 筛选出没有embedding的节点
            nodes_without_embedding = session.execute_read(_get_nodes_without_embedding, all_entities_list)
            if not nodes_without_embedding:
                logger.info("所有实体已有embedding，无需重新计算")
                return

            logger.info(f"需要为{len(nodes_without_embedding)}/{len(all_entities_list)}个实体计算embedding")

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
                batch_embeddings = await self.aget_embedding(batch_entities, batch_size=batch_size)

                # 将实体名称和嵌入向量配对
                entity_embedding_pairs = list(zip(batch_entities, batch_embeddings))

                # 批量写入数据库
                session.execute_write(_batch_set_embeddings, entity_embedding_pairs)

            # 数据添加完成后保存图信息
            self.save_graph_info()

    async def add_embedding_to_nodes(self, node_names=None, kgdb_name="neo4j", batch_size=None):
        """为节点添加嵌入向量

        Args:
            node_names (list, optional): 要添加嵌入向量的节点名称列表，None表示所有没有嵌入向量的节点
            kgdb_name (str, optional): 图数据库名称，默认为'neo4j'
            batch_size (int, optional): 嵌入批次大小

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
                    embedding = await self.aget_embedding(node_name, batch_size=batch_size)
                    session.execute_write(self.set_embedding, node_name, embedding)
                    count += 1
                except Exception as e:
                    logger.error(f"为节点 '{node_name}' 添加嵌入向量失败: {e}, {traceback.format_exc()}")

        return count

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
                "embed_model_configurable": not self.is_initialized_from_file,
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
            # 保存成功后，标记为从文件初始化（锁定配置）
            self.is_initialized_from_file = True
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
                logger.debug(f"图数据库信息文件不存在：{info_file_path}")
                return False

            with open(info_file_path, encoding="utf-8") as f:
                graph_info = json.load(f)

            # 更新对象属性
            if graph_info.get("embed_model_name"):
                self.embed_model_name = graph_info["embed_model_name"]

            # 重新选择embedding model
            if self.embed_model_name:
                self.embed_model = select_embedding_model(self.embed_model_name)

            # 如果需要，可以加载更多信息
            # 注意：这里不更新self.kgdb_name，因为它是在初始化时设置的

            self.is_initialized_from_file = True
            logger.info(f"已加载图数据库信息，最后更新时间：{graph_info.get('last_updated')}")
            return True
        except Exception as e:
            logger.error(f"加载图数据库信息失败：{e}")
            return False

    async def aget_embedding(self, text, batch_size=40):
        if isinstance(text, list):
            outputs = await self.embed_model.abatch_encode(text, batch_size=batch_size)
            return outputs
        else:
            outputs = await self.embed_model.aencode(text)
            return outputs

    def get_embedding(self, text, batch_size=40):
        if isinstance(text, list):
            outputs = self.embed_model.batch_encode(text, batch_size=batch_size)
            return outputs
        else:
            outputs = self.embed_model.encode([text])[0]
            return outputs

    def set_embedding(self, tx, entity_name, embedding):
        """为单个实体设置嵌入向量"""
        tx.run(
            """
        MATCH (e:Entity {name: $name})
        CALL db.create.setNodeVectorProperty(e, 'embedding', $embedding)
        """,
            name=entity_name,
            embedding=embedding,
        )

    def query_node(
        self, keyword, threshold=0.9, kgdb_name="neo4j", hops=2, max_entities=8, return_format="graph", **kwargs
    ):
        """知识图谱查询节点的入口"""
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
        sorted_entity_to_score = sorted(entity_to_score.items(), key=lambda x: x[1], reverse=True)
        qualified_entities = [name for name, _ in sorted_entity_to_score][:max_entities]

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
            MATCH (n:Upload)
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
            WHERE 'Upload' IN labels(similarEntity)
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

        def _process_record_props(record):
            """处理记录中的属性：扁平化 properties 并移除 embedding"""
            if record is None:
                return None

            # 复制一份以避免修改原字典
            data = dict(record)
            props = data.pop("properties", {}) or {}

            # 移除 embedding
            if "embedding" in props:
                del props["embedding"]

            # 合并属性（优先保留原字典中的 id, name, type 等核心字段）
            return {**props, **data}

        def query(tx, entity_name, hops, limit):
            try:
                query_str = """
                WITH [
                    // 1跳出边
                    [(n:Upload {name: $entity_name})-[r1]->(m1) |
                     {h: {id: elementId(n), name: n.name, properties: properties(n)},
                      r: {
                        id: elementId(r1),
                        type: r1.type,
                        source_id: elementId(n),
                        target_id: elementId(m1),
                        properties: properties(r1)
                      },
                      t: {id: elementId(m1), name: m1.name, properties: properties(m1)}}],
                    // 2跳出边
                    [(n:Upload {name: $entity_name})-[r1]->(m1)-[r2]->(m2) |
                     {h: {id: elementId(m1), name: m1.name, properties: properties(m1)},
                      r: {
                        id: elementId(r2),
                        type: r2.type,
                        source_id: elementId(m1),
                        target_id: elementId(m2),
                        properties: properties(r2)
                      },
                      t: {id: elementId(m2), name: m2.name, properties: properties(m2)}}],
                    // 1跳入边
                    [(m1)-[r1]->(n:Upload {name: $entity_name}) |
                     {h: {id: elementId(m1), name: m1.name, properties: properties(m1)},
                      r: {
                        id: elementId(r1),
                        type: r1.type,
                        source_id: elementId(m1),
                        target_id: elementId(n),
                        properties: properties(r1)
                      },
                      t: {id: elementId(n), name: n.name, properties: properties(n)}}],
                    // 2跳入边
                    [(m2)-[r2]->(m1)-[r1]->(n:Upload {name: $entity_name}) |
                     {h: {id: elementId(m2), name: m2.name, properties: properties(m2)},
                      r: {
                        id: elementId(r2),
                        type: r2.type,
                        source_id: elementId(m2),
                        target_id: elementId(m1),
                        properties: properties(r2)
                      },
                      t: {id: elementId(m1), name: m1.name, properties: properties(m1)}}]
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
                    h = _process_record_props(item["h"])
                    r = _process_record_props(item["r"])
                    t = _process_record_props(item["t"])

                    formatted_results["nodes"].extend([h, t])
                    formatted_results["edges"].append(r)
                    formatted_results["triples"].append((h["name"], r["type"], t["name"]))

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
