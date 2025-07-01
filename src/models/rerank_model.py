import os
import json
import requests
import numpy as np

from src import config
from src.utils import logger, get_docker_safe_url

def sigmoid(x):
    return 1 / (1 + np.exp(-x))

class OnlineReranker:
    def __init__(self, model_name, api_key, base_url, **kwargs):
        self.url = get_docker_safe_url(base_url)
        self.model = model_name
        self.api_key = api_key
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

def get_reranker(model_id, **kwargs):
    support_rerankers = config.reranker_names.keys()
    assert model_id in support_rerankers, f"Unsupported Reranker: {model_id}, only support {support_rerankers}"

    model_info = config.reranker_names[model_id]
    base_url = model_info["base_url"]
    api_key = os.getenv(model_info["api_key"], model_info["api_key"])
    assert api_key, f"{model_info['name']} api_key is required"
    return OnlineReranker(
        model_name=model_info["name"],
        api_key=api_key,
        base_url=base_url,
        **kwargs
    )
