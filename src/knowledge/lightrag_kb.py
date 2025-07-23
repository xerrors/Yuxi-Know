import os
import time
import traceback
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime

from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc, setup_logger
from lightrag.kg.shared_storage import initialize_pipeline_status

from src.knowledge.knowledge_base import KnowledgeBase
from src.knowledge.kb_utils import split_text_into_chunks, prepare_item_metadata, get_embedding_config
from src import config
from src.utils import logger, hashstr, get_docker_safe_url


LIGHTRAG_LLM_PROVIDER = os.getenv("LIGHTRAG_LLM_PROVIDER", "openai")
LIGHTRAG_LLM_NAME = os.getenv("LIGHTRAG_LLM_NAME", "gpt-4.1-mini")


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
        self.instances: Dict[str, LightRAG] = {}

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

    async def _create_kb_instance(self, db_id: str, config: Dict) -> LightRAG:
        """创建 LightRAG 实例"""
        logger.info(f"Creating LightRAG instance for {db_id}")

        if db_id not in self.databases_meta:
            raise ValueError(f"Database {db_id} not found")

        llm_info = self.databases_meta[db_id].get("llm_info", {})
        embed_info = self.databases_meta[db_id].get("embed_info", {})

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
        )

        return rag

    async def _initialize_kb_instance(self, instance: LightRAG) -> None:
        """初始化 LightRAG 实例"""
        logger.info(f"Initializing LightRAG instance for {instance.working_dir}")
        await instance.initialize_storages()
        await initialize_pipeline_status()

    async def _get_lightrag_instance(self, db_id: str) -> Optional[LightRAG]:
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

    def _get_llm_func(self, llm_info: Dict):
        """获取 LLM 函数"""
        from src.models import select_model
        model = select_model(LIGHTRAG_LLM_PROVIDER, LIGHTRAG_LLM_NAME)

        async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
            return await openai_complete_if_cache(
                model=model.model_name,
                prompt=prompt,
                system_prompt=system_prompt,
                history_messages=history_messages,
                api_key=model.api_key,
                base_url=model.base_url,
                extra_body={"enable_thinking": False},
                **kwargs,
            )
        return llm_model_func

    def _get_embedding_func(self, embed_info: Dict):
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

    async def add_content(self, db_id: str, items: List[str],
                         params: Optional[Dict] = None) -> List[Dict]:
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
            filename = metadata["filename"]
            item_path = metadata["path"]

            # 添加文件记录
            file_record = metadata.copy()
            self.files_meta[file_id] = file_record
            self._save_metadata()

            try:
                # 根据内容类型处理内容
                if content_type == "file":
                    markdown_content = await self._process_file_to_markdown(item, params=params)
                    markdown_content_lines = markdown_content[:100].replace('\n', ' ')
                    logger.info(f"Markdown content: {markdown_content_lines}...")
                else:  # URL
                    markdown_content = await self._process_url_to_markdown(item, params=params)

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

    async def get_file_info(self, db_id: str, file_id: str) -> Dict:
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