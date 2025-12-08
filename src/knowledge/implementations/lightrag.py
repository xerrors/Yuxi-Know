import os
import traceback

from lightrag import LightRAG, QueryParam
from lightrag.kg.shared_storage import initialize_pipeline_status
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc, setup_logger
from neo4j import GraphDatabase
from pymilvus import connections, utility

from src import config
from src.knowledge.base import KnowledgeBase
from src.knowledge.indexing import process_file_to_markdown
from src.knowledge.utils.kb_utils import get_embedding_config, prepare_item_metadata
from src.utils import hashstr, logger
from src.utils.datetime_utils import shanghai_now


class LightRagKB(KnowledgeBase):
    """基于 LightRAG 的知识库实现"""

    def __init__(self, work_dir: str, **kwargs):
        """
        初始化 LightRAG 知识库

        Args:
            work_dir: 工作目录
            **kwargs: 其他配置参数
        """
        super().__init__(work_dir)

        # 存储 LightRAG 实例映射 {db_id: LightRAG}
        self.instances: dict[str, LightRAG] = {}

        # 设置 LightRAG 日志
        log_dir = os.path.join(work_dir, "logs", "lightrag")
        os.makedirs(log_dir, exist_ok=True)
        setup_logger(
            "lightrag",
            log_file_path=os.path.join(log_dir, f"lightrag_{shanghai_now().strftime('%Y-%m-%d')}.log"),
        )

        logger.info("LightRagKB initialized")

    @property
    def kb_type(self) -> str:
        """知识库类型标识"""
        return "lightrag"

    def delete_database(self, db_id: str) -> dict:
        """删除数据库，同时清除Milvus和Neo4j中的数据"""
        # Drop Milvus collection
        try:
            milvus_uri = os.getenv("MILVUS_URI") or "http://localhost:19530"
            milvus_token = os.getenv("MILVUS_TOKEN") or ""
            connection_alias = f"lightrag_{hashstr(db_id, 6)}"

            connections.connect(alias=connection_alias, uri=milvus_uri, token=milvus_token)

            # 删除 LightRAG 创建的三个集合
            collection_names = [f"{db_id}_chunks", f"{db_id}_relationships", f"{db_id}_entities"]
            for collection_name in collection_names:
                if utility.has_collection(collection_name, using=connection_alias):
                    utility.drop_collection(collection_name, using=connection_alias)
                    logger.info(f"Dropped Milvus collection {collection_name}")
                else:
                    logger.info(f"Milvus collection {collection_name} does not exist, skipping")

            connections.disconnect(connection_alias)
        except Exception as e:
            logger.error(f"Failed to drop Milvus collection {db_id}: {e}")

        # Delete Neo4j data
        neo4j_uri = os.getenv("NEO4J_URI") or "bolt://localhost:7687"
        neo4j_username = os.getenv("NEO4J_USERNAME") or "neo4j"
        neo4j_password = os.getenv("NEO4J_PASSWORD") or "0123456789"

        try:
            driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_username, neo4j_password))
            with driver.session() as session:
                # 删除带有特定 db_id 标签的节点和关系
                session.run(
                    """
                    MATCH (n:`"""
                    + db_id
                    + """`)
                    DETACH DELETE n
                """
                )

                logger.info(f"Deleted Neo4j nodes and relationships for workspace {db_id}")
        except Exception as e:
            logger.error(f"Failed to delete Neo4j data for {db_id}: {e}")
        finally:
            if "driver" in locals():
                driver.close()

        # Delete local files and metadata
        return super().delete_database(db_id)

    async def _create_kb_instance(self, db_id: str, kb_config: dict) -> LightRAG:
        """创建 LightRAG 实例"""
        logger.info(f"Creating LightRAG instance for {db_id}")

        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        llm_info = self.databases_meta[db_id].get("llm_info", {})
        embed_info = self.databases_meta[db_id].get("embed_info", {})
        # 读取在创建数据库时透传的附加参数（包括语言）
        metadata = self.databases_meta[db_id].get("metadata", {}) or {}
        addon_params = {}
        if isinstance(metadata.get("addon_params"), dict):
            addon_params.update(metadata.get("addon_params", {}))
        # 兼容直接放在 metadata 下的 language
        if isinstance(metadata.get("language"), str) and metadata.get("language"):
            addon_params.setdefault("language", metadata.get("language"))
        # 默认语言从环境变量读取，默认 English
        addon_params.setdefault("language", os.getenv("SUMMARY_LANGUAGE") or "English")

        # 创建工作目录
        working_dir = os.path.join(self.work_dir, db_id)
        os.makedirs(working_dir, exist_ok=True)

        # 创建 LightRAG 实例
        rag = LightRAG(
            working_dir=working_dir,
            workspace=db_id,
            llm_model_func=self._get_llm_func(llm_info),
            embedding_func=self._get_embedding_func(embed_info),
            vector_storage="MilvusVectorDBStorage",
            kv_storage="JsonKVStorage",
            graph_storage="Neo4JStorage",
            doc_status_storage="JsonDocStatusStorage",
            log_file_path=os.path.join(working_dir, "lightrag.log"),
            addon_params=addon_params,
        )

        return rag

    async def _initialize_kb_instance(self, instance: LightRAG) -> None:
        """初始化 LightRAG 实例"""
        logger.info(f"Initializing LightRAG instance for {instance.working_dir}")
        await instance.initialize_storages()
        await initialize_pipeline_status()

    async def _get_lightrag_instance(self, db_id: str) -> LightRAG | None:
        """获取或创建 LightRAG 实例"""
        if db_id in self.instances:
            return self.instances[db_id]

        if db_id not in self.databases_meta:
            return None

        try:
            # 创建实例
            rag = await self._create_kb_instance(db_id, {})

            # 异步初始化存储
            await self._initialize_kb_instance(rag)

            self.instances[db_id] = rag
            return rag

        except Exception as e:
            logger.error(f"Failed to create LightRAG instance for {db_id}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def _get_llm_func(self, llm_info: dict):
        """获取 LLM 函数"""
        from src.models import select_model

        # 如果用户选择了LLM，使用用户选择的；否则使用环境变量默认值
        if llm_info and llm_info.get("model_spec"):
            model_spec = llm_info["model_spec"]
            logger.info(f"Using user-selected LLM spec: {model_spec}")
        elif llm_info and llm_info.get("provider") and llm_info.get("model_name"):
            model_spec = f"{llm_info['provider']}/{llm_info['model_name']}"
            logger.info(f"Using user-selected LLM: {model_spec}")
        else:
            model_spec = config.default_model
            logger.info(f"Using default LLM from environment: {model_spec}")

        model = select_model(model_spec=model_spec)

        async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
            return await openai_complete_if_cache(
                model=model.model_name,
                prompt=prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                api_key=model.api_key,
                base_url=model.base_url,
                **kwargs,
            )

        return llm_model_func

    def _get_embedding_func(self, embed_info: dict):
        """获取 embedding 函数"""
        config_dict = get_embedding_config(embed_info)

        if config_dict["model_id"].startswith("ollama"):
            from lightrag.llm.ollama import ollama_embed

            from src.utils import get_docker_safe_url

            host = get_docker_safe_url(config_dict["base_url"].replace("/api/embed", ""))
            logger.debug(f"Ollama host: {host}")
            return EmbeddingFunc(
                embedding_dim=config_dict["dimension"],
                max_token_size=8192,
                func=lambda texts: ollama_embed(
                    texts=texts,
                    embed_model=config_dict["name"],
                    api_key=config_dict["api_key"],
                    host=host,
                ),
            )

        return EmbeddingFunc(
            embedding_dim=config_dict["dimension"],
            max_token_size=8192,
            func=lambda texts: openai_embed(
                texts=texts,
                model=config_dict["model"],
                api_key=config_dict["api_key"],
                base_url=config_dict["base_url"].replace("/embeddings", ""),
            ),
        )

    async def add_content(self, db_id: str, items: list[str], params: dict | None = None) -> list[dict]:
        """添加内容（文件/URL）"""
        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        rag = await self._get_lightrag_instance(db_id)
        if not rag:
            raise ValueError(f"Failed to get LightRAG instance for {db_id}")

        content_type = params.get("content_type", "file") if params else "file"
        processed_items_info = []

        for item in items:
            # 准备文件元数据
            metadata = await prepare_item_metadata(item, content_type, db_id, params=params)
            file_id = metadata["file_id"]
            item_path = metadata["path"]

            # 添加文件记录
            file_record = metadata.copy()
            self.files_meta[file_id] = file_record
            self._save_metadata()

            self._add_to_processing_queue(file_id)
            try:
                # 确保params中包含db_id（ZIP文件处理需要）
                if params is None:
                    params = {}
                params["db_id"] = db_id

                # 根据内容类型处理内容
                if content_type != "file":
                    raise ValueError("URL 内容解析已禁用")
                markdown_content = await process_file_to_markdown(item, params=params)
                markdown_content_lines = markdown_content[:100].replace("\n", " ")
                logger.info(f"Markdown content: {markdown_content_lines}...")

                # 使用 LightRAG 插入内容
                await rag.ainsert(input=markdown_content, ids=file_id, file_paths=item_path)

                logger.info(f"Inserted {content_type} {item} into LightRAG. Done.")

                # 更新状态为完成
                self.files_meta[file_id]["status"] = "done"
                self._save_metadata()
                file_record["status"] = "done"

            except Exception as e:
                error_msg = str(e)
                logger.error(f"处理{content_type} {item} 失败: {error_msg}, {traceback.format_exc()}")
                self.files_meta[file_id]["status"] = "failed"
                self.files_meta[file_id]["error"] = error_msg
                self._save_metadata()
                file_record["status"] = "failed"
                file_record["error"] = error_msg
            finally:
                self._remove_from_processing_queue(file_id)

            processed_items_info.append(file_record)

        return processed_items_info

    async def update_content(self, db_id: str, file_ids: list[str], params: dict | None = None) -> list[dict]:
        """更新内容 - 根据file_ids重新解析文件并更新向量库"""
        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        rag = await self._get_lightrag_instance(db_id)
        if not rag:
            raise ValueError(f"Failed to get LightRAG instance for {db_id}")

        # 处理默认参数
        if params is None:
            params = {}
        content_type = params.get("content_type", "file")
        processed_items_info = []

        for file_id in file_ids:
            # 从元数据中获取文件信息
            if file_id not in self.files_meta:
                logger.warning(f"File {file_id} not found in metadata, skipping")
                continue

            file_meta = self.files_meta[file_id]
            file_path = file_meta.get("path")

            if not file_path:
                logger.warning(f"File path not found for {file_id}, skipping")
                continue

            # 添加到处理队列
            self._add_to_processing_queue(file_id)

            try:
                # 更新状态为处理中
                self.files_meta[file_id]["processing_params"] = params.copy()
                self.files_meta[file_id]["status"] = "processing"
                self._save_metadata()

                # 重新解析文件为 markdown
                if content_type != "file":
                    raise ValueError("URL 内容解析已禁用")
                markdown_content = await process_file_to_markdown(file_path, params=params)
                markdown_content_lines = markdown_content[:100].replace("\n", " ")
                logger.info(f"Markdown content: {markdown_content_lines}...")

                # 先删除现有的 LightRAG 数据（仅删除chunks，保留元数据）
                await self.delete_file_chunks_only(db_id, file_id)

                # 使用 LightRAG 重新插入内容
                await rag.ainsert(input=markdown_content, ids=file_id, file_paths=file_path)

                logger.info(f"Updated {content_type} {file_path} in LightRAG. Done.")

                # 更新元数据状态
                self.files_meta[file_id]["status"] = "done"
                self._save_metadata()

                # 从处理队列中移除
                self._remove_from_processing_queue(file_id)

                # 返回更新后的文件信息
                updated_file_meta = file_meta.copy()
                updated_file_meta["status"] = "done"
                updated_file_meta["file_id"] = file_id
                processed_items_info.append(updated_file_meta)

            except Exception as e:
                error_msg = str(e)
                logger.error(f"更新{content_type} {file_path} 失败: {error_msg}, {traceback.format_exc()}")
                self.files_meta[file_id]["status"] = "failed"
                self.files_meta[file_id]["error"] = error_msg
                self._save_metadata()

                # 从处理队列中移除
                self._remove_from_processing_queue(file_id)

                # 返回失败的文件信息
                failed_file_meta = file_meta.copy()
                failed_file_meta["status"] = "failed"
                failed_file_meta["file_id"] = file_id
                failed_file_meta["error"] = error_msg
                processed_items_info.append(failed_file_meta)

        return processed_items_info

    async def aquery(self, query_text: str, db_id: str, **kwargs) -> str:
        """异步查询知识库"""
        rag = await self._get_lightrag_instance(db_id)
        if not rag:
            raise ValueError(f"Database {db_id} not found")

        try:
            # QueryParam 支持的参数列表
            valid_params = {
                "mode",
                "only_need_context",
                "only_need_prompt",
                "response_type",
                "stream",
                "top_k",
                "chunk_top_k",
                "max_entity_tokens",
                "max_relation_tokens",
                "max_total_tokens",
                "hl_keywords",
                "ll_keywords",
                "conversation_history",
                "history_turns",
                "model_func",
                "user_prompt",
                "enable_rerank",
                "include_references",
            }

            # 过滤 kwargs，只保留 QueryParam 支持的参数
            filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_params}

            # 设置查询参数
            params_dict = {
                "mode": "mix",
                "only_need_context": True,
                "top_k": 10,
            } | filtered_kwargs
            param = QueryParam(**params_dict)

            # 执行查询
            response = await rag.aquery(query_text, param)
            logger.debug(f"Query response: {response}")

            return response

        except Exception as e:
            logger.error(f"Query error: {e}, {traceback.format_exc()}")
            return ""

    async def delete_file_chunks_only(self, db_id: str, file_id: str) -> None:
        """仅删除文件的chunks数据，保留元数据（用于更新操作）"""
        rag = await self._get_lightrag_instance(db_id)
        if rag:
            try:
                # 使用 LightRAG 删除文档
                await rag.adelete_by_doc_id(file_id)
                logger.info(f"Deleted chunks for file {file_id} from LightRAG")
            except Exception as e:
                logger.error(f"Error deleting file {file_id} from LightRAG: {e}")
        # 注意：这里不删除 files_meta[file_id]，保留元数据用于后续操作

    async def delete_file(self, db_id: str, file_id: str) -> None:
        """删除文件（包括元数据）"""
        # 先删除 LightRAG 中的 chunks 数据
        await self.delete_file_chunks_only(db_id, file_id)

        # 删除文件记录
        if file_id in self.files_meta:
            del self.files_meta[file_id]
            self._save_metadata()

    async def get_file_basic_info(self, db_id: str, file_id: str) -> dict:
        """获取文件基本信息（仅元数据）"""
        if file_id not in self.files_meta:
            raise Exception(f"File not found: {file_id}")

        return {"meta": self.files_meta[file_id]}

    async def get_file_content(self, db_id: str, file_id: str) -> dict:
        """获取文件内容信息（chunks和lines）"""
        if file_id not in self.files_meta:
            raise Exception(f"File not found: {file_id}")

        # 使用 LightRAG 获取 chunks
        content_info = {"lines": []}
        rag = await self._get_lightrag_instance(db_id)
        if rag:
            try:
                # 获取文档的所有 chunks
                # LightRAG v1.4+ 使用 JsonKVStorage，通过 _data 属性访问所有数据
                if hasattr(rag.text_chunks, "_data"):
                    all_chunks = dict(rag.text_chunks._data)
                else:
                    logger.warning("text_chunks does not have _data attribute, cannot get file content")
                    return content_info

                # 筛选属于该文档的 chunks
                doc_chunks = []
                for chunk_id, chunk_data in all_chunks.items():
                    if isinstance(chunk_data, dict) and chunk_data.get("full_doc_id") == file_id:
                        chunk_data["id"] = chunk_id
                        chunk_data["content_vector"] = []
                        doc_chunks.append(chunk_data)

                # 按 chunk_order_index 排序
                doc_chunks.sort(key=lambda x: x.get("chunk_order_index", 0))
                content_info["lines"] = doc_chunks
                return content_info

            except Exception as e:
                logger.error(f"Failed to get file content from LightRAG: {e}")
                content_info["lines"] = []
                return content_info

        return content_info

    async def get_file_info(self, db_id: str, file_id: str) -> dict:
        """获取文件完整信息（基本信息+内容信息）- 保持向后兼容"""
        if file_id not in self.files_meta:
            raise Exception(f"File not found: {file_id}")

        # 合并基本信息和内容信息
        basic_info = await self.get_file_basic_info(db_id, file_id)
        content_info = await self.get_file_content(db_id, file_id)

        return {**basic_info, **content_info}

    async def export_data(self, db_id: str, format: str = "csv", **kwargs) -> str:
        """
        使用 LightRAG 原生功能导出知识库数据。
        [注意] 此功能当前已禁用。
        """
        # TODO: 修复 LightRAG 库与 Milvus 后端不兼容的问题
        # 当前调用 aexport_data 会导致 "'MilvusVectorDBStorage' object has no attribute 'client_storage'" 错误。
        # 在 lightrag 库修复此问题前，暂时禁用此功能。
        raise NotImplementedError("由于 LightRAG 库与 Milvus 后端不兼容，原生导出功能暂不可用。等待上游库修复。")

        # --- 以下为待修复后启用的代码 ---
        # logger.info(f"Exporting data for db_id {db_id} in format {format} with options {kwargs}")

        # rag = await self._get_lightrag_instance(db_id)
        # if not rag:
        #     raise ValueError(f"Failed to get LightRAG instance for {db_id}")

        # export_dir = os.path.join(self.work_dir, db_id, "exports")
        # os.makedirs(export_dir, exist_ok=True)

        # timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        # output_filename = f"export_{db_id}_{timestamp}.{format}"
        # output_filepath = os.path.join(export_dir, output_filename)

        # include_vectors = kwargs.get('include_vectors', False)

        # # 直接调用 lightrag 的异步导出功能
        # # 之前的测试表明 aexport_data 确实存在，并且 to_thread 会导致 loop 问题
        # await rag.aexport_data(
        #     output_path=output_filepath,
        #     file_format=format,
        #     include_vector_data=include_vectors
        # )

        # logger.info(f"Successfully created export file: {output_filepath}")
        # return output_filepath
