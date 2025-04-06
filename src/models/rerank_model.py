import os
import json
import requests
import numpy as np
from FlagEmbedding import FlagReranker

from src import config
from src.utils.logging_config import logger


class LocalReranker(FlagReranker):
    def __init__(self, config, **kwargs):
        model_info = config.reranker_names[config.reranker]
        model_name_or_path = config.model_local_paths.get(model_info["name"], model_info.get("local_path"))
        model_name_or_path = model_name_or_path or model_info["name"]
        logger.info(f"Loading Reranker model {config.reranker} from {model_name_or_path}")

        super().__init__(model_name_or_path, use_fp16=True, device=config.device, **kwargs)
        logger.info(f"Reranker model {config.reranker} loaded")


def sigmoid(x):
    return 1 / (1 + np.exp(-x))

class SiliconFlowReranker():
    def __init__(self, config, **kwargs):
        self.url = "https://api.siliconflow.cn/v1/rerank"
        self.model = config.reranker_names[config.reranker]["name"]

        api_key = os.getenv("SILICONFLOW_API_KEY")
        assert api_key, "SILICONFLOW_API_KEY is required"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def compute_score(self, sentence_pairs, batch_size = 256, max_length = 512, normalize = False):
        # TODO 还没实现 batch_size
        query, sentences = sentence_pairs[0], sentence_pairs[1]
        payload = self.build_payload(query, sentences, max_length)
        response = requests.request("POST", self.url, json=payload, headers=self.headers)
        response = json.loads(response.text)
        # logger.debug(f"SiliconFlow Reranker response: {response}")

        results = sorted(response["results"], key=lambda x: x["index"])
        all_scores = [result["relevance_score"] for result in results]

        if normalize:
            all_scores = [sigmoid(score) for score in all_scores]

        return all_scores

    def build_payload(self, query, sentences, max_length = 512):
        return {
            "model": self.model,
            "query": query,
            "documents": sentences,
            "max_chunks_per_doc": max_length,
        }

def get_reranker(config):
    assert config.reranker in config.reranker_names.keys(), f"Unsupported Reranker: {config.reranker}, only support {config.reranker_names.keys()}"
    provider, model_name = config.reranker.split('/', 1)
    if provider == "local":
        return LocalReranker(config)
    elif provider == "siliconflow":
        return SiliconFlowReranker(config)
    else:
        raise ValueError(f"Unsupported Reranker: {config.reranker}, only support {config.reranker_names.keys()}")

