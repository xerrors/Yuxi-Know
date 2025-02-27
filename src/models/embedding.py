import os
import json
import requests
from FlagEmbedding import FlagModel

from src.config import EMBED_MODEL_INFO
from src.utils import hashstr, logger


class LocalEmbeddingModel(FlagModel):
    def __init__(self, config, **kwargs):
        info = EMBED_MODEL_INFO[config.embed_model]
        model_name_or_path = config.model_local_paths.get(info["name"], info.get("default_path"))
        logger.info(f"Loading embedding model {info['name']} from {model_name_or_path}")

        super().__init__(model_name_or_path,
                query_instruction_for_retrieval=info.get("query_instruction", None),
                use_fp16=False, **kwargs)

        logger.info(f"Embedding model {info['name']} loaded")



from zhipuai import ZhipuAI


class RemoteEmbeddingModel:
    embed_state = {}

    def batch_encode(self, messages, batch_size=20):
        logger.info(f"Batch encoding {len(messages)} messages")
        data = []

        if len(messages) > batch_size:
            task_id = hashstr(messages)
            self.embed_state[task_id] = {
                'status': 'in-progress',
                'total': len(messages),
                'progress': 0
            }

        for i in range(0, len(messages), batch_size):
            group_msg = messages[i:i+batch_size]
            logger.info(f"Encoding {i} to {i+batch_size} with {len(messages)} messages")
            response = self.encode_queries(group_msg)
            data.extend(response)

        if len(messages) > batch_size:
            self.embed_state[task_id]['progress'] = len(messages)
            self.embed_state[task_id]['status'] = 'completed'

        return data

class ZhipuEmbedding(RemoteEmbeddingModel):

    def __init__(self, config) -> None:
        self.config = config
        self.model = EMBED_MODEL_INFO[config.embed_model]["name"]
        self.client = ZhipuAI(api_key=os.getenv("ZHIPUAI_API_KEY"))

    def predict(self, message):
        response = self.client.embeddings.create(
            model=self.model,
            input=message,
        )
        data = [a.embedding for a in response.data]
        return data

    def encode(self, message):
        return self.predict(message)

    def encode_queries(self, queries):
        return self.predict(queries)


class SiliconFlowEmbedding(RemoteEmbeddingModel):

    def __init__(self, config) -> None:
        self.url = "https://api.siliconflow.cn/v1/embeddings"
        self.model = EMBED_MODEL_INFO[config.embed_model]["name"]
        api_key = os.getenv("SILICONFLOW_API_KEY")
        assert api_key, "SILICONFLOW_API_KEY is required"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def encode(self, message):
        payload = self.build_payload(message)
        response = requests.request("POST", self.url, json=payload, headers=self.headers)
        response = json.loads(response.text)
        # logger.debug(f"SiliconFlow Embedding response: {response}")
        assert response["data"], f"SiliconFlow Embedding failed: {response}"
        data = [a["embedding"] for a in response["data"]]
        return data

    def encode_queries(self, queries):
        return self.encode(queries)

    def build_payload(self, message):
        return {
            "model": self.model,
            "input": message,
        }

def get_embedding_model(config):
    if not config.enable_knowledge_base:
        return None

    provider, model_name = config.embed_model.split('/', 1)
    assert config.embed_model in EMBED_MODEL_INFO.keys(), f"Unsupported embed model: {config.embed_model}, only support {EMBED_MODEL_INFO.keys()}"
    logger.debug(f"Loading embedding model {config.embed_model}")
    if provider == "local":
        model = LocalEmbeddingModel(config)

    if provider == "zhipu":
        model = ZhipuEmbedding(config)

    if provider == "siliconflow":
        model = SiliconFlowEmbedding(config)

    return model

def handle_local_model(paths, model_name, default_path):
    model_path = paths.get(model_name, default_path)
    return model_path