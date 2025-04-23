import os
import json
import requests
import asyncio
from FlagEmbedding import FlagModel
from zhipuai import ZhipuAI

from src import config
from src.utils import hashstr, logger, get_docker_safe_url


class BaseEmbeddingModel:
    embed_state = {}

    def get_dimension(self):
        if hasattr(self, "dimension"):
            return self.dimension

        if hasattr(self, "embed_model_fullname"):
            return config.embed_model_names[self.embed_model_fullname].get("dimension", None)

        return config.embed_model_names[self.model].get("dimension", None)

    def encode(self, message):
        return self.predict(message)

    def encode_queries(self, queries):
        return self.predict(queries)

    async def aencode(self, message):
        return await asyncio.to_thread(self.encode, message)

    async def aencode_queries(self, queries):
        return await asyncio.to_thread(self.encode_queries, queries)

    async def abatch_encode(self, messages, batch_size=20):
        return await asyncio.to_thread(self.batch_encode, messages, batch_size)

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
        """
        对于本地模型，也可以在 src/static/models.private.yaml 中配置对应的 local_path 路径

        ```yaml
        EMBED_MODEL_INFO:
            local/BAAI/bge-m3:
                dimension: 1024
                name: BAAI/bge-m3
                local_path: /path/to/bge-m3
        ```

        但是也要确保在 docker-compose 中映射了 MODEL_DIR 到 /models 目录
        """
        info = config.embed_model_names[config.embed_model]

        self.model = config.model_local_paths.get(info["name"], info.get("local_path"))
        self.model = self.model or info["name"]
        self.dimension = info["dimension"]
        self.embed_model_fullname = config.embed_model

        if os.getenv("MODEL_DIR"):
            if os.path.exists(_path := os.path.join(os.getenv("MODEL_DIR"), self.model)):
                self.model = _path
            else:
                logger.warning(f"Local model `{info['name']}` not found in `{self.model}`, using `{info['name']}`")

        logger.info(f"Loading local model `{info['name']}` from `{self.model}` with device `{config.device}`，"
                    f"如果没配置任何路径的话，正常情况下会自动从 Huggingface 下载模型，如果遇到下载失败，可以尝试使用 HF_MIRROR 环境变量；"
                    f"如果还是不行，建议手动下载到某个文件夹比如  /path/to/models/BAAI/bge-m3 目录下；"
                    f"然后配置 src/.env 文件中的 MODEL_DIR 环境变量到 /path/to/models 目录；"
                    f"如果是在 docker 中运行，请确保 docker-compose 文件（line 12 左右）中映射了 MODEL_DIR 到 /models 目录")

        super().__init__(self.model,
                query_instruction_for_retrieval=info.get("query_instruction", None),
                use_fp16=False,
                device=config.device,
                **kwargs)

        logger.info(f"Embedding model {info['name']} loaded")


class ZhipuEmbedding(BaseEmbeddingModel):

    def __init__(self, config) -> None:
        self.config = config
        self.model = config.embed_model_names[config.embed_model]["name"]
        self.dimension = config.embed_model_names[config.embed_model]["dimension"]
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
        self.info = config.embed_model_names[config.embed_model]
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
        self.info = config.embed_model_names[config.embed_model]
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
    assert config.embed_model in config.embed_model_names.keys(), f"Unsupported embed model: {config.embed_model}, only support {config.embed_model_names.keys()}"
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