import os
import json
import httpx
import requests
import asyncio
from abc import abstractmethod, ABC

from src import config
from src.utils import hashstr, logger, get_docker_safe_url


class BaseEmbeddingModel(ABC):

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
        self.embed_state = {}

    @abstractmethod
    def predict(self, message: list[str] | str) -> list[list[float]]:
        """同步编码"""
        raise NotImplementedError("Subclasses must implement this method")

    @abstractmethod
    async def apredict(self, message: list[str] | str) -> list[list[float]]:
        """异步编码"""
        raise NotImplementedError("Subclasses must implement this method")

    def encode(self, message: list[str] | str) -> list[list[float]]:
        """等同于predict"""
        return self.predict(message)

    def encode_queries(self, queries: list[str] | str) -> list[list[float]]:
        """等同于predict"""
        return self.predict(queries)

    async def aencode(self, message: list[str] | str) -> list[list[float]]:
        """等同于apredict"""
        return await self.apredict(message)

    async def aencode_queries(self, queries: list[str] | str) -> list[list[float]]:
        """等同于apredict"""
        return await self.apredict(queries)

    def batch_encode(self, messages: list[str], batch_size: int = 40) -> list[list[float]]:
        # logger.info(f"Batch encoding {len(messages)} messages")
        data = []
        task_id = None
        if len(messages) > batch_size:
            task_id = hashstr(messages)
            self.embed_state[task_id] = {
                'status': 'in-progress',
                'total': len(messages),
                'progress': 0
            }

        for i in range(0, len(messages), batch_size):
            group_msg = messages[i:i+batch_size]
            logger.info(f"Encoding [{i}/{len(messages)}] messages (bsz={batch_size})")
            response = self.encode(group_msg)
            data.extend(response)
            if task_id:
                self.embed_state[task_id]['progress'] = i + len(group_msg)

        if task_id:
            self.embed_state[task_id]['status'] = 'completed'

        return data

    async def abatch_encode(self, messages: list[str], batch_size: int = 40) -> list[list[float]]:
        data = []
        task_id = None
        if len(messages) > batch_size:
            task_id = hashstr(messages)
            self.embed_state[task_id] = {
                'status': 'in-progress',
                'total': len(messages),
                'progress': 0
            }

        tasks = []
        for i in range(0, len(messages), batch_size):
            group_msg = messages[i:i+batch_size]
            tasks.append(self.aencode(group_msg))

        results = await asyncio.gather(*tasks)
        for res in results:
            data.extend(res)

        if task_id:
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

    def predict(self, message: list[str] | str) -> list[list[float]]:
        if isinstance(message, str):
            message = [message]

        payload = {"model": self.model, "input": message}
        try:
            response = requests.post(self.base_url, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()
            if "embeddings" not in result:
                raise ValueError(f"Ollama Embedding failed: Invalid response format {result}")
            return result["embeddings"]
        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.error(f"Ollama Embedding request failed: {e}")
            raise ValueError(f"Ollama Embedding request failed: {e}")

    async def apredict(self, message: list[str] | str) -> list[list[float]]:
        if isinstance(message, str):
            message = [message]

        payload = {"model": self.model, "input": message}
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.base_url, json=payload, timeout=60)
                response.raise_for_status()
                result = response.json()
                if "embeddings" not in result:
                    raise ValueError(f"Ollama Embedding failed: Invalid response format {result}")
                return result["embeddings"]
            except (httpx.RequestError, json.JSONDecodeError) as e:
                logger.error(f"Ollama Embedding async request failed: {e}")
                raise ValueError(f"Ollama Embedding async request failed: {e}")


class OtherEmbedding(BaseEmbeddingModel):

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def build_payload(self, message: list[str] | str) -> dict:
        return {"model": self.model, "input": message}

    def predict(self, message: list[str] | str) -> list[list[float]]:
        payload = self.build_payload(message)
        try:
            response = requests.post(self.base_url, json=payload, headers=self.headers, timeout=60)
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or "data" not in result:
                raise ValueError(f"Other Embedding failed: Invalid response format {result}")
            return [item["embedding"] for item in result["data"]]
        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.error(f"Other Embedding request failed: {e}")
            raise ValueError(f"Other Embedding request failed: {e}")

    async def apredict(self, message: list[str] | str) -> list[list[float]]:
        payload = self.build_payload(message)
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.base_url, json=payload, headers=self.headers, timeout=60)
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, dict) or "data" not in result:
                    raise ValueError(f"Other Embedding failed: Invalid response format {result}")
                return [item["embedding"] for item in result["data"]]
            except (httpx.RequestError, json.JSONDecodeError) as e:
                logger.error(f"Other Embedding async request failed: {e}")
                raise ValueError(f"Other Embedding async request failed: {e}")
