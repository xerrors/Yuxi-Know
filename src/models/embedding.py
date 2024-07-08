from FlagEmbedding import FlagModel

from utils.logging_config import setup_logger


logger = setup_logger("EmbeddingModel")

SUPPORT_LIST = {
    "bge-large-zh": "BAAI/bge-large-zh-v1.5",
}

QUERY_INSTRUCTION = {
    "bge-large-zh": "为这个句子生成表示以用于检索相关文章：",
}

class EmbeddingModel(FlagModel):
    def __init__(self, config, **kwargs):

        assert config.embed_model in SUPPORT_LIST.keys(), f"Unsupported embed model: {config.embed_model}, only support {SUPPORT_LIST.keys()}"

        if config.embed_model in config.model_local_paths.keys():
            model_name_or_path = config.model_local_paths[config.embed_model]
        else:
            model_name_or_path = SUPPORT_LIST[config.embed_model]

        logger.info(f"Loading embedding model {config.embed_model} from {model_name_or_path}")

        super().__init__(model_name_or_path,
                query_instruction_for_retrieval=QUERY_INSTRUCTION[config.embed_model],
                use_fp16=False, **kwargs)

        logger.info(f"Embedding model {config.embed_model} loaded")