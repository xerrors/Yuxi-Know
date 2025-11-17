import asyncio
import os
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from typing import Any

import aiohttp
import numpy as np

from src import config
from src.utils import get_docker_safe_url, logger


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


class BaseReranker(ABC):
    def __init__(self, model_name, api_key, base_url, **kwargs):
        self.url = get_docker_safe_url(base_url)
        self.model = model_name
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self.session: aiohttp.ClientSession | None = None
        self.timeout = aiohttp.ClientTimeout(total=30)
        self.parameters: dict[str, Any] = dict(kwargs.get("parameters", {}))

    async def _ensure_session(self) -> None:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers, timeout=self.timeout)

    @abstractmethod
    def _build_payload(self, query: str, documents: list[str], max_length: int) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def _extract_results(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def acompute_score(
        self,
        sentence_pairs: Sequence[Sequence[str]],
        batch_size: int = 32,
        max_length: int = 512,
        normalize: bool = True,
    ) -> list[float]:
        if not sentence_pairs or len(sentence_pairs) < 2:
            return []

        query, sentences = sentence_pairs[0], sentence_pairs[1]
        documents = [sentences] if isinstance(sentences, str) else list(sentences)

        if not documents:
            return []

        await self._ensure_session()

        all_scores: list[float] = []
        batch_size = max(1, int(batch_size))
        total_batches = (len(documents) + batch_size - 1) // batch_size

        for batch_no, start in enumerate(range(0, len(documents), batch_size), start=1):
            batch = documents[start : start + batch_size]
            try:
                scores = await self._batch_rerank(query, batch, max_length=max_length)
                all_scores.extend(scores)
                logger.debug(f"Reranking batch {batch_no}/{total_batches} completed")
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Reranking batch {batch_no} failed: {exc}")
                all_scores.extend([0.5] * len(batch))

        if normalize:
            all_scores = [float(sigmoid(score)) for score in all_scores]

        return all_scores

    async def _batch_rerank(self, query: str, documents: Iterable[str], max_length: int) -> list[float]:
        docs = list(documents)
        if not docs:
            return []

        payload = self._build_payload(query, docs, max_length)

        await self._ensure_session()
        assert self.session is not None

        try:
            async with self.session.post(self.url, json=payload) as response:
                response.raise_for_status()
                result: dict[str, Any] = await response.json()
        except TimeoutError as exc:
            total_timeout = self.timeout.total if self.timeout else 0.0
            logger.error(f"Reranking request timeout after {total_timeout:.1f}s")
            raise exc
        except aiohttp.ClientError as exc:
            logger.error(f"Reranking request failed: {exc}")
            raise exc

        processed = sorted(self._extract_results(result), key=lambda item: item.get("index", 0))
        return [float(entry.get("relevance_score", 0.0)) for entry in processed]

    def compute_score(self, sentence_pairs, batch_size=256, max_length=512, normalize=False):
        try:
            _ = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.acompute_score(sentence_pairs, batch_size, max_length, normalize))
        raise RuntimeError("compute_score cannot be used while an event loop is running. Use acompute_score instead.")

    async def aclose(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()

    def __del__(self) -> None:
        if self.session and not self.session.closed:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                asyncio.run(self.aclose())
                return

            if loop.is_closed():
                asyncio.run(self.aclose())
            elif not loop.is_running():
                loop.run_until_complete(self.aclose())


class OpenAIReranker(BaseReranker):
    def _build_payload(self, query: str, documents: list[str], max_length: int) -> dict[str, Any]:
        return {
            "model": self.model,
            "query": query,
            "documents": documents,
            "max_chunks_per_doc": max_length,
        }

    def _extract_results(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        return list(result.get("results", []))


class DashscopeReranker(BaseReranker):
    def _build_payload(self, query: str, documents: list[str], max_length: int) -> dict[str, Any]:
        params = {"top_n": len(documents), "return_documents": False}
        instruct = self.parameters.get("instruct")
        if instruct:
            params["instruct"] = instruct
        return {
            "model": self.model,
            "input": {"query": query, "documents": documents},
            "parameters": params,
        }

    def _extract_results(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        return list(result.get("output", {}).get("results", []))


def get_reranker(model_id, **kwargs):
    support_rerankers = config.reranker_names.keys()
    assert model_id in support_rerankers, f"Unsupported Reranker: {model_id}, only support {support_rerankers}"

    model_info = config.reranker_names[model_id]
    base_url = model_info.base_url
    api_key = os.getenv(model_info.api_key) or model_info.api_key
    assert api_key, f"{model_info.name} api_key is required"
    provider = model_id.split("/", maxsplit=1)[0] if "/" in model_id else ""
    if provider in {"siliconflow", "vllm"}:
        return OpenAIReranker(model_name=model_info.name, api_key=api_key, base_url=base_url, **kwargs)
    if provider == "dashscope":
        return DashscopeReranker(model_name=model_info.name, api_key=api_key, base_url=base_url, **kwargs)
    return OpenAIReranker(model_name=model_info.name, api_key=api_key, base_url=base_url, **kwargs)
