import os
import traceback
from datetime import datetime

from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc, setup_logger
from lightrag.kg.shared_storage import initialize_pipeline_status
from pymilvus import connections, utility
from neo4j import GraphDatabase

from src.knowledge.knowledge_base import KnowledgeBase
from src.knowledge.indexing import process_url_to_markdown, process_file_to_markdown
from src.knowledge.kb_utils import prepare_item_metadata, get_embedding_config
from src.utils import logger, hashstr


LIGHTRAG_LLM_PROVIDER = os.getenv("LIGHTRAG_LLM_PROVIDER", "siliconflow")
LIGHTRAG_LLM_NAME = os.getenv("LIGHTRAG_LLM_NAME", "zai-org/GLM-4.5-Air")


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
        setup_logger("lightrag", log_file_path=os.path.join(
            log_dir, f"lightrag_{datetime.now().strftime('%Y-%m-%d')}.log"))

        logger.info("LightRagKB initialized")

    @property
    def kb_type(self) -> str:
        """知识库类型标识"""
        return "lightrag"

    def delete_database(self, db_id: str) -> dict:
        """删除数据库，同时清除Milvus和Neo4j中的数据"""
        # Drop Milvus collection
        try:
            milvus_uri = os.getenv('MILVUS_URI', 'http://localhost:19530')
            milvus_token = os.getenv('MILVUS_TOKEN', '')
            connection_alias = f"lightrag_{hashstr(db_id, 6)}"

            connections.connect(
                alias=connection_alias,
                uri=milvus_uri,
                token=milvus_token
            )

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
        neo4j_uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
        neo4j_username = os.getenv('NEO4J_USERNAME', 'neo4j')
        neo4j_password = os.getenv('NEO4J_PASSWORD', '0123456789')

        try:
            driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_username, neo4j_password))
            with driver.session() as session:
                # 删除带有特定 db_id 标签的节点和关系
                session.run("""
                    MATCH (n:`""" + db_id + """`)
                    DETACH DELETE n
                """)

                logger.info(f"Deleted Neo4j nodes and relationships for workspace {db_id}")
        except Exception as e:
            logger.error(f"Failed to delete Neo4j data for {db_id}: {e}")
        finally:
            if 'driver' in locals():
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
        addon_params.setdefault("language", os.getenv("SUMMARY_LANGUAGE", "English"))

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
        if llm_info and llm_info.get("provider") and llm_info.get("model_name"):
            provider = llm_info["provider"]
            model_name = llm_info["model_name"]
            logger.info(f"Using user-selected LLM: {provider}/{model_name}")
        else:
            provider = LIGHTRAG_LLM_PROVIDER
            model_name = LIGHTRAG_LLM_NAME
            logger.info(f"Using default LLM from environment: {provider}/{model_name}")

        model = select_model(provider, model_name)

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

        return EmbeddingFunc(
            embedding_dim=config_dict["dimension"],
            max_token_size=4096,
            func=lambda texts: openai_embed(
                texts=texts,
                model=config_dict["model"],
                api_key=config_dict["api_key"],
                base_url=config_dict["base_url"].replace("/embeddings", ""),
            ),
        )

    async def add_content(self, db_id: str, items: list[str],
                         params: dict | None = None) -> list[dict]:
        """添加内容（文件/URL）"""
        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        rag = await self._get_lightrag_instance(db_id)
        if not rag:
            raise ValueError(f"Failed to get LightRAG instance for {db_id}")

        content_type = params.get('content_type', 'file') if params else 'file'
        processed_items_info = []

        for item in items:
            # 准备文件元数据
            metadata = prepare_item_metadata(item, content_type, db_id)
            file_id = metadata["file_id"]
            item_path = metadata["path"]

            # 添加文件记录
            file_record = metadata.copy()
            self.files_meta[file_id] = file_record
            self._save_metadata()

            self._add_to_processing_queue(file_id)
            try:
                # 根据内容类型处理内容
                if content_type == "file":
                    markdown_content = await process_file_to_markdown(item, params=params)
                    markdown_content_lines = markdown_content[:100].replace('\n', ' ')
                    logger.info(f"Markdown content: {markdown_content_lines}...")
                else:  # URL
                    markdown_content = await process_url_to_markdown(item, params=params)

                # 使用 LightRAG 插入内容
                await rag.ainsert(
                    input=markdown_content,
                    ids=file_id,
                    file_paths=item_path
                )

                logger.info(f"Inserted {content_type} {item} into LightRAG. Done.")

                # 更新状态为完成
                self.files_meta[file_id]["status"] = "done"
                self._save_metadata()
                file_record['status'] = "done"

            except Exception as e:
                error_msg = str(e)
                logger.error(f"处理{content_type} {item} 失败: {error_msg}, {traceback.format_exc()}")
                self.files_meta[file_id]["status"] = "failed"
                self.files_meta[file_id]["error"] = error_msg
                self._save_metadata()
                file_record['status'] = "failed"
                file_record['error'] = error_msg
            finally:
                self._remove_from_processing_queue(file_id)

            processed_items_info.append(file_record)

        return processed_items_info

    async def aquery(self, query_text: str, db_id: str, **kwargs) -> str:
        """异步查询知识库"""
        rag = await self._get_lightrag_instance(db_id)
        if not rag:
            raise ValueError(f"Database {db_id} not found")

        try:
            # 设置查询参数
            params_dict = {
                "mode": "mix",
                "only_need_context": True,
                "top_k": 10,
            } | kwargs
            param = QueryParam(**params_dict)

            # 执行查询
            response = await rag.aquery(query_text, param)
            logger.debug(f"Query response: {response}")

            return response

        except Exception as e:
            logger.error(f"Query error: {e}, {traceback.format_exc()}")
            return ""

    async def delete_file(self, db_id: str, file_id: str) -> None:
        """删除文件"""
        rag = await self._get_lightrag_instance(db_id)
        if rag:
            try:
                # 使用 LightRAG 删除文档
                await rag.adelete_by_doc_id(file_id)
            except Exception as e:
                logger.error(f"Error deleting file {file_id} from LightRAG: {e}")

        # 删除文件记录
        if file_id in self.files_meta:
            del self.files_meta[file_id]
            self._save_metadata()

    async def get_file_info(self, db_id: str, file_id: str) -> dict:
        """获取文件信息和chunks"""
        if file_id not in self.files_meta:
            raise Exception(f"File not found: {file_id}")

        # 使用 LightRAG 获取 chunks
        rag = await self._get_lightrag_instance(db_id)
        if rag:
            try:
                # 获取文档的所有 chunks
                assert hasattr(rag.text_chunks, 'get_all'), "text_chunks does not have get_all method"
                all_chunks = await rag.text_chunks.get_all()  # type: ignore

                # 筛选属于该文档的 chunks
                doc_chunks = []
                for chunk_id, chunk_data in all_chunks.items():
                    if isinstance(chunk_data, dict) and chunk_data.get("full_doc_id") == file_id:
                        chunk_data["id"] = chunk_id
                        chunk_data["content_vector"] = []
                        doc_chunks.append(chunk_data)

                # 按 chunk_order_index 排序
                doc_chunks.sort(key=lambda x: x.get("chunk_order_index", 0))
                return {"lines": doc_chunks}

            except Exception as e:
                logger.error(f"Error getting chunks for file {file_id}: {e}")

        return {"lines": []}

    async def export_data(self, db_id: str, format: str = 'csv', **kwargs) -> str:
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
