import os
import json
import requests
import numpy as np
from FlagEmbedding import FlagReranker

from src import config
from src.utils import logger, get_docker_safe_url


class LocalReranker(FlagReranker):
    def __init__(self, **kwargs):
        model_info = config.reranker_names[config.reranker]
        model_name_or_path = config.model_local_paths.get(model_info["name"], model_info.get("local_path"))
        model_name_or_path = model_name_or_path or model_info["name"]
        logger.info(f"Loading Reranker model {config.reranker} from {model_name_or_path}")

        super().__init__(model_name_or_path, use_fp16=True, device=config.device, **kwargs)
        logger.info(f"Reranker model {config.reranker} loaded")


def sigmoid(x):
    return 1 / (1 + np.exp(-x))

class OnlineRerank:
    def __init__(self, **kwargs):
        model_info = config.reranker_names[config.reranker]
        self.url = get_docker_safe_url(model_info["base_url"])
        self.model = model_info["name"]

        api_key = os.getenv(model_info["api_key"], model_info["api_key"])
        assert api_key, f"{model_info['name']} api_key is required"
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

def get_reranker():
    support_rerankers = config.reranker_names.keys()
    assert config.reranker in support_rerankers, f"Unsupported Reranker: {config.reranker}, only support {support_rerankers}"
    provider, model_name = config.reranker.split('/', 1)
    if provider == "local":
        logger.warning("[DEPRECATED] Local reranker will be removed in v0.2, please use other reranker")
        return LocalReranker()
    elif provider == "siliconflow":
        return OnlineRerank()
    else:
        raise ValueError(f"Unsupported Reranker: {config.reranker}, only support {config.reranker_names.keys()}")

