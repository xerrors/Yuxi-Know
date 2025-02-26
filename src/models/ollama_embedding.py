import os
import requests
import numpy as np
from typing import List, Union, Dict

from src.models.embedding import RemoteEmbeddingModel
from src.utils.logging_config import setup_logger

logger = setup_logger("OllamaEmbedding")

class OllamaEmbedding(RemoteEmbeddingModel):
    """
    使用 Ollama API 进行文本嵌入的类
    """
    def __init__(self, model_info: Dict, config) -> None:
        """
        初始化 Ollama Embedding 模型

        Args:
            model_info: 模型信息字典
            config: 配置对象
        """
        self.config = config
        self.model_info = model_info
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model_name = model_info.get("name", "nomic-embed-text")
        self.query_instruction_for_retrieval = "为这个句子生成表示以用于检索相关文章："
        logger.info(f"Ollama Embedding model {self.model_name} initialized")

    def _get_embedding(self, text: str) -> List[float]:
        """
        获取单个文本的嵌入向量

        Args:
            text: 输入文本

        Returns:
            嵌入向量
        """
        url = f"{self.base_url}/api/embeddings"
        try:
            response = requests.post(url, json={
                "model": self.model_name,
                "prompt": text
            })
            response.raise_for_status()
            return response.json()["embedding"]
        except Exception as e:
            logger.error(f"Error getting embedding: {str(e)}")
            raise

    def predict(self, messages: List[str]) -> List[List[float]]:
        """
        批量获取文本嵌入向量

        Args:
            messages: 文本列表

        Returns:
            嵌入向量列表
        """
        embeddings = []
        batch_size = 20

        for i in range(0, len(messages), batch_size):
            batch = messages[i:i + batch_size]
            logger.info(f"Processing batch {i//batch_size + 1}, size: {len(batch)}")

            batch_embeddings = []
            for text in batch:
                embedding = self._get_embedding(text)
                batch_embeddings.append(embedding)

            embeddings.extend(batch_embeddings)

        return embeddings

    def encode(self, messages: Union[str, List[str]]) -> List[List[float]]:
        """
        编码文本

        Args:
            messages: 单个文本或文本列表

        Returns:
            嵌入向量列表
        """
        if isinstance(messages, str):
            messages = [messages]
        return self.predict(messages)

    def encode_queries(self, queries: List[str]) -> List[List[float]]:
        """
        编码查询文本

        Args:
            queries: 查询文本列表

        Returns:
            查询文本的嵌入向量列表
        """
        return self.predict(queries)


class OllamaReranker:
    """
    使用 Ollama API 进行文本重排序的类
    """
    def __init__(self, config) -> None:
        """
        初始化 Ollama Reranker

        Args:
            config: 配置对象
        """
        self.config = config
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model_name = config.reranker
        logger.info(f"Ollama Reranker model {self.model_name} initialized")

    def compute_score(self, query: str, passage: str) -> float:
        """
        计算查询和文本段落之间的相关性分数

        Args:
            query: 查询文本
            passage: 段落文本

        Returns:
            相关性分数
        """
        prompt = f"Query: {query}\nPassage: {passage}\nRate the relevance of the passage to the query on a scale of 0 to 1:"

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False
                }
            )
            response.raise_for_status()

            # 提取生成的数字作为分数
            result = response.json()["response"].strip()
            try:
                score = float(result)
                return min(max(score, 0), 1)  # 确保分数在 0-1 之间
            except ValueError:
                logger.warning(f"Could not parse score from response: {result}")
                return 0.0

        except Exception as e:
            logger.error(f"Error computing rerank score: {str(e)}")
            return 0.0

    def rerank(self, query: str, passages: List[str], top_n: int = None) -> List[Dict]:
        """
        重新排序文本段落

        Args:
            query: 查询文本
            passages: 段落文本列表
            top_n: 返回前 n 个结果

        Returns:
            排序后的结果列表，每个元素包含索引和分数
        """
        scores = []
        for i, passage in enumerate(passages):
            score = self.compute_score(query, passage)
            scores.append({"index": i, "score": score})

        # 按分数降序排序
        sorted_results = sorted(scores, key=lambda x: x["score"], reverse=True)

        if top_n:
            sorted_results = sorted_results[:top_n]

        return sorted_results