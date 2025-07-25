import os
import json
import requests
import asyncio
from abc import abstractmethod
from langchain_huggingface import HuggingFaceEmbeddings

from src import config
from src.utils import hashstr, logger, get_docker_safe_url


class BaseEmbeddingModel:
    embed_state = {}

    def __init__(self, model=None, name=None, dimension=None, url=None, base_url=None, api_key=None):
        """
        Args:
            model: 模型名称，冗余设计，同name
            name: 模型名称，冗余设计，同model
            dimension: 维度
            url: 请求URL，冗余设计，同base_url
            base_url: 基础URL，请求URL，冗余设计，同url
            api_key: 请求API密钥
        """
        base_url = base_url or url
        self.model = model or name
        self.dimension = dimension
        self.base_url = get_docker_safe_url(base_url)
        self.api_key = os.getenv(api_key, api_key)

    @abstractmethod
    def predict(self, message):
        raise NotImplementedError("Subclasses must implement this method")

    def encode(self, message):
        return self.predict(message)

    def encode_queries(self, queries):
        return self.predict(queries)

    async def aencode(self, message):
        return await asyncio.to_thread(self.encode, message)

    async def aencode_queries(self, queries):
        return await asyncio.to_thread(self.encode_queries, queries)

    async def abatch_encode(self, messages, batch_size=40):
        return await asyncio.to_thread(self.batch_encode, messages, batch_size)

    def batch_encode(self, messages, batch_size=40):
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
            # logger.debug(f"Response: {len(response)=}, {len(group_msg)=}, {len(response[0])=}")
            data.extend(response)

        if len(messages) > batch_size:
            self.embed_state[task_id]['progress'] = len(messages)
            self.embed_state[task_id]['status'] = 'completed'

        return data

class OllamaEmbedding(BaseEmbeddingModel):
    """
    Ollama Embedding Model
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.base_url = self.base_url or get_docker_safe_url("http://localhost:11434/api/embed")

    def predict(self, message: list[str] | str):
        if isinstance(message, str):
            message = [message]

        payload = {
            "model": self.model,
            "input": message,
        }
        response = requests.request("POST", self.base_url, json=payload)
        response = json.loads(response.text)
        assert response.get("embeddings"), f"Ollama Embedding failed: {response}"
        return response["embeddings"]


class OtherEmbedding(BaseEmbeddingModel):

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def predict(self, message):
        payload = self.build_payload(message)
        response = requests.request("POST", self.base_url, json=payload, headers=self.headers)
        response = json.loads(response.text)
        assert response["data"], f"Other Embedding failed: {response}"
        data = [a["embedding"] for a in response["data"]]
        return data

    def build_payload(self, message):
        return {
            "model": self.model,
            "input": message,
        }
