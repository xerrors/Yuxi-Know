import os
import uuid
from FlagEmbedding import FlagModel, FlagReranker

from src.config import EMBED_MODEL_INFO, RERANKER_LIST
from src.utils.logging_config import setup_logger
from src.utils import hashstr


logger = setup_logger("EmbeddingModel")

GLOBAL_EMBED_STATE = {}


class EmbeddingModel(FlagModel):
    def __init__(self, model_info, config, **kwargs):
        self.info = model_info
        model_name_or_path = config.model_local_paths.get(model_info.name, model_info.default_path)
        logger.info(f"Loading embedding model {model_info.name} from {model_name_or_path}")

        super().__init__(model_name_or_path,
                query_instruction_for_retrieval=model_info.get("query_instruction", None),
                use_fp16=False, **kwargs)

        logger.info(f"Embedding model {model_info.name} loaded")


class Reranker(FlagReranker):
    def __init__(self, config, **kwargs):

        assert config.reranker in RERANKER_LIST.keys(), f"Unsupported Reranker: {config.reranker}, only support {RERANKER_LIST.keys()}"

        model_name_or_path = config.model_local_paths.get(config.reranker, RERANKER_LIST[config.reranker])
        logger.info(f"Loading Reranker model {config.reranker} from {model_name_or_path}")

        super().__init__(model_name_or_path, use_fp16=True, **kwargs)
        logger.info(f"Reranker model {config.reranker} loaded")


from zhipuai import ZhipuAI

class ZhipuEmbedding:

    def __init__(self, model_info, config) -> None:
        self.config = config
        self.model_info = model_info
        self.client = ZhipuAI(api_key=os.getenv("ZHIPUAPI"))
        logger.info("Zhipu Embedding model loaded")
        self.query_instruction_for_retrieval = "为这个句子生成表示以用于检索相关文章："

    def predict(self, message):
        data = []

        if len(message) > 10:
            global GLOBAL_EMBED_STATE
            task_id = hashstr(message)
            logger.info(f"Creating new state for process {task_id}")
            GLOBAL_EMBED_STATE[task_id] = {
                'status': 'in-progress',
                'total': len(message),
                'progress': 0
            }

        for i in range(0, len(message), 10):
            if len(message) > 10:
                logger.info(f"Encoding {i} to {i+10} with {len(message)} messages")
                GLOBAL_EMBED_STATE[task_id]['progress'] = i

            group_msg = message[i:i+10]
            response = self.client.embeddings.create(
                model=self.model_info.default_path,
                input=group_msg,
            )

            data.extend([a.embedding for a in response.data])

        if len(message) > 10:
            GLOBAL_EMBED_STATE[task_id]['progress'] = len(message)
            GLOBAL_EMBED_STATE[task_id]['status'] = 'completed'

        return data

    def encode(self, message):
        return self.predict(message)

    def encode_queries(self, queries):
        # queries = [self.query_instruction_for_retrieval + query for query in queries]
        return self.predict(queries)


def get_embedding_model(config):
    if not config.enable_knowledge_base:
        return None

    assert config.embed_model in EMBED_MODEL_INFO.keys(), f"Unsupported embed model: {config.embed_model}, only support {EMBED_MODEL_INFO.keys()}"

    if config.embed_model in ["bge-large-zh-v1.5"]:
        model = EmbeddingModel(EMBED_MODEL_INFO[config.embed_model], config)

    if config.embed_model in ["zhipu-embedding-2", "zhipu-embedding-3"]:
        model = ZhipuEmbedding(EMBED_MODEL_INFO[config.embed_model], config)

    return model