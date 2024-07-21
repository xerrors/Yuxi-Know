import os
from FlagEmbedding import FlagModel, FlagReranker

from utils.logging_config import setup_logger


logger = setup_logger("EmbeddingModel")

SUPPORT_LIST = {
    "bge-large-zh-v1.5": "BAAI/bge-large-zh-v1.5",
    "zhipu": "embedding-2",
}

RERANKER_LIST = {
    "bge-reranker-v2-m3": "BAAI/bge-reranker-v2-m3",
}

QUERY_INSTRUCTION = {
    "bge-large-zh-v1.5": "为这个句子生成表示以用于检索相关文章：",
}

class EmbeddingModel(FlagModel):
    def __init__(self, config, **kwargs):

        assert config.embed_model in SUPPORT_LIST.keys(), f"Unsupported embed model: {config.embed_model}, only support {SUPPORT_LIST}"

        model_name_or_path = config.model_local_paths.get(config.embed_model, SUPPORT_LIST[config.embed_model])
        logger.info(f"Loading embedding model {config.embed_model} from {model_name_or_path}")

        super().__init__(model_name_or_path,
                query_instruction_for_retrieval=QUERY_INSTRUCTION[config.embed_model],
                use_fp16=False, **kwargs)

        logger.info(f"Embedding model {config.embed_model} loaded")


class Reranker(FlagReranker):
    def __init__(self, config, **kwargs):

        assert config.reranker in RERANKER_LIST.keys(), f"Unsupported Reranker: {config.reranker}, only support {RERANKER_LIST.keys()}"

        model_name_or_path = config.model_local_paths.get(config.reranker, RERANKER_LIST[config.reranker])
        logger.info(f"Loading Reranker model {config.reranker} from {model_name_or_path}")

        super().__init__(model_name_or_path, use_fp16=True, **kwargs)
        logger.info(f"Reranker model {config.reranker} loaded")


from zhipuai import ZhipuAI

class ZhipuEmbedding:

    def __init__(self, config) -> None:
        self.config = config
        self.client = ZhipuAI(api_key=os.getenv("ZHIPUAPI"))
        logger.info("Zhipu Embedding model loaded")
        self.query_instruction_for_retrieval = "为这个句子生成表示以用于检索相关文章："

    def predict(self, message):
        response = self.client.embeddings.create(
            model=SUPPORT_LIST[self.config.embed_model],
            input=message
        )
        return [a["embedding"] for a in response["data"]]

    def encode(self, message):
        return self.predict(message)

    def encode_queries(self, queries):
        # queries = [self.query_instruction_for_retrieval + query for query in queries]
        return self.predict(queries)


def get_embedding_model(config):
    if config.embed_model == "zhipu":
        return ZhipuEmbedding(config)
    else:
        return EmbeddingModel(config)