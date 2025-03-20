import os
import json
import requests
from FlagEmbedding import FlagModel
from zhipuai import ZhipuAI

from src import config
from src.config import EMBED_MODEL_INFO
from src.utils import hashstr, logger, get_docker_safe_url


class BaseEmbeddingModel:
    embed_state = {}

    def get_dimension(self):
        if hasattr(self, "dimension"):
            return self.dimension

        if hasattr("embed_model_fullname"):
            return EMBED_MODEL_INFO[self.embed_model_fullname].get("dimension", None)

        return EMBED_MODEL_INFO[self.model].get("dimension", None)

    def encode(self, message):
        return self.predict(message)

    def encode_queries(self, queries):
        return self.predict(queries)

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
            response = self.encode(group_msg)
            logger.debug(f"Response: {len(response)=}, {len(group_msg)=}, {len(response[0])=}")
            data.extend(response)

        if len(messages) > batch_size:
            self.embed_state[task_id]['progress'] = len(messages)
            self.embed_state[task_id]['status'] = 'completed'

        return data

class LocalEmbeddingModel(FlagModel, BaseEmbeddingModel):
    def __init__(self, config, **kwargs):
        info = EMBED_MODEL_INFO[config.embed_model]

        self.model = config.model_local_paths.get(info["name"], info.get("local_path"))
        self.model = self.model or info["name"]
        self.dimension = info["dimension"]
        self.embed_model_fullname = config.embed_model

        if os.path.exists(_path := os.path.join(os.getenv("MODEL_DIR"), self.model)):
            self.model = _path

        logger.info(f"Loading local model `{info['name']}` from `{self.model}` with device `{config.device}`")

        super().__init__(self.model,
                query_instruction_for_retrieval=info.get("query_instruction", None),
                use_fp16=False,
                device=config.device,
                **kwargs)

        logger.info(f"Embedding model {info['name']} loaded")


class ZhipuEmbedding(BaseEmbeddingModel):

    def __init__(self, config) -> None:
        self.config = config
        self.model = EMBED_MODEL_INFO[config.embed_model]["name"]
        self.dimension = EMBED_MODEL_INFO[config.embed_model]["dimension"]
        self.client = ZhipuAI(api_key=os.getenv("ZHIPUAI_API_KEY"))
        self.embed_model_fullname = config.embed_model

    def predict(self, message):
        response = self.client.embeddings.create(
            model=self.model,
            input=message,
        )
        data = [a.embedding for a in response.data]
        return data


class OllamaEmbedding(BaseEmbeddingModel):
    def __init__(self, config) -> None:
        self.info = EMBED_MODEL_INFO[config.embed_model]
        self.model = self.info["name"]
        self.url = self.info.get("url", "http://localhost:11434/api/embed")
        self.url = get_docker_safe_url(self.url)
        self.dimension = self.info.get("dimension", None)
        self.embed_model_fullname = config.embed_model

    def predict(self, message: list[str] | str):
        if isinstance(message, str):
            message = [message]

        payload = {
            "model": self.model,
            "input": message,
        }
        response = requests.request("POST", self.url, json=payload)
        response = json.loads(response.text)
        assert response.get("embeddings"), f"Ollama Embedding failed: {response}"
        return response["embeddings"]


class OtherEmbedding(BaseEmbeddingModel):

    def __init__(self, config) -> None:
        self.info = EMBED_MODEL_INFO[config.embed_model]
        self.embed_model_fullname = config.embed_model
        self.dimension = self.info.get("dimension", None)
        self.model = self.info["name"]
        self.api_key = os.getenv(self.info["api_key"], None)
        self.url = get_docker_safe_url(self.info["url"])
        assert self.url and self.model, f"URL and model are required. Cur embed model: {config.embed_model}"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def predict(self, message):
        payload = self.build_payload(message)
        response = requests.request("POST", self.url, json=payload, headers=self.headers)
        response = json.loads(response.text)
        assert response["data"], f"Other Embedding failed: {response}"
        data = [a["embedding"] for a in response["data"]]
        return data

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

    elif provider == "zhipu":
        model = ZhipuEmbedding(config)

    elif provider == "ollama":
        model = OllamaEmbedding(config)

    else:
        model = OtherEmbedding(config)

    return model

def handle_local_model(paths, model_name, default_path):
    model_path = paths.get(model_name, default_path)
    return model_path