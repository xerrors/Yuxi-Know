import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-key")

from yuxi.services.model_provider_service import (
    _DEFAULT_BUILTIN_PROVIDERS,
    DEFAULT_EMBEDDING_MODELS_ENDPOINT,
    DEFAULT_MODELS_ENDPOINT,
    _check_credential_status,
    _normalize_payload,
    _normalize_remote_model,
    fetch_remote_models,
)


def test_normalize_payload_accepts_enabled_chat_model():
    payload = _normalize_payload(
        {
            "provider_id": "openrouter-local",
            "display_name": "OpenRouter Local",
            "base_url": "https://openrouter.ai/api/v1",
            "enabled_models": [{"id": "anthropic/claude-sonnet-4.5", "type": "chat"}],
        }
    )

    assert payload["provider_id"] == "openrouter-local"
    assert payload["provider_type"] == "openai"
    assert payload["models_endpoint"] == DEFAULT_MODELS_ENDPOINT
    assert payload["embedding_models_endpoint"] == DEFAULT_EMBEDDING_MODELS_ENDPOINT
    assert payload["enabled_models"][0]["display_name"] == "anthropic/claude-sonnet-4.5"


def test_normalize_payload_rejects_unknown_enabled_model_type():
    with pytest.raises(ValueError, match="type 必须是"):
        _normalize_payload(
            {
                "provider_id": "openrouter-local",
                "display_name": "OpenRouter Local",
                "base_url": "https://openrouter.ai/api/v1",
                "enabled_models": [{"id": "unknown-model", "type": "unknown"}],
            }
        )


def test_normalize_payload_requires_embedding_dimension():
    with pytest.raises(ValueError, match="dimension"):
        _normalize_payload(
            {
                "provider_id": "embedding-local",
                "display_name": "Embedding Local",
                "base_url": "https://example.com/v1",
                "enabled_models": [{"id": "text-embedding", "type": "embedding"}],
            }
        )


def test_normalize_remote_model_preserves_detailed_model_config():
    model = _normalize_remote_model(
        {
            "id": "xiaomi/mimo-v2-omni",
            "name": "Xiaomi: MiMo-V2-Omni",
            "context_length": 262144,
            "architecture": {
                "input_modalities": ["text", "audio", "image", "video"],
                "output_modalities": ["text"],
            },
            "top_provider": {"max_completion_tokens": 65536},
            "supported_parameters": ["temperature", "tools"],
        }
    )

    assert model["id"] == "xiaomi/mimo-v2-omni"
    assert model["display_name"] == "Xiaomi: MiMo-V2-Omni"
    assert model["type"] == "chat"
    assert model["input_modalities"] == ["text", "audio", "image", "video"]
    assert model["max_completion_tokens"] == 65536
    assert model["raw_metadata"]["supported_parameters"] == ["temperature", "tools"]


def test_normalize_remote_model_uses_endpoint_model_type():
    model = _normalize_remote_model({"id": "BAAI/bge-m3", "object": "model"}, "embedding")

    assert model["id"] == "BAAI/bge-m3"
    assert model["type"] == "embedding"


@pytest.mark.asyncio
async def test_fetch_remote_models_loads_embedding_only_when_capability_enabled(monkeypatch):
    calls = []

    async def fake_fetch(client, provider, headers, endpoint, model_type):
        calls.append((endpoint, model_type))
        return [{"id": f"{model_type}-model", "type": model_type}]

    monkeypatch.setattr("yuxi.services.model_provider_service._fetch_models_from_endpoint", fake_fetch)

    class Provider:
        base_url = "https://example.com/v1"
        api_key = None
        api_key_env = None
        headers_json = {}
        capabilities = ["chat", "embedding", "rerank"]
        models_endpoint = "/models"
        embedding_models_endpoint = "/embeddings/models"
        rerank_models_endpoint = None

    models = await fetch_remote_models(Provider())

    assert calls == [("/models", "chat"), ("/embeddings/models", "embedding")]
    assert [model["type"] for model in models] == ["chat", "embedding"]


def test_builtin_provider_templates_default_to_openai_provider_type():
    assert len(_DEFAULT_BUILTIN_PROVIDERS) >= 20
    provider_types = {
        _normalize_payload(
            {
                "provider_id": provider["provider_id"],
                "display_name": provider["display_name"],
                "base_url": provider["base_url"],
                "provider_type": provider.get("provider_type"),
            }
        )["provider_type"]
        for provider in _DEFAULT_BUILTIN_PROVIDERS
    }
    assert provider_types == {"openai"}


def test_builtin_siliconflow_provider_includes_default_runnable_models():
    provider = next(item for item in _DEFAULT_BUILTIN_PROVIDERS if item["provider_id"] == "siliconflow-cn")
    models = {model["id"]: model for model in provider["enabled_models"]}

    assert provider["capabilities"] == ["chat", "embedding", "rerank"]
    assert provider["embedding_base_url"] == "https://api.siliconflow.cn/v1/embeddings"
    assert provider["rerank_base_url"] == "https://api.siliconflow.cn/v1/rerank"
    assert models["Pro/BAAI/bge-m3"]["type"] == "embedding"
    assert models["Pro/BAAI/bge-m3"]["dimension"] == 1024
    assert "base_url_override" not in models["Pro/BAAI/bge-m3"]
    assert models["Pro/BAAI/bge-reranker-v2-m3"]["type"] == "rerank"
    assert "base_url_override" not in models["Pro/BAAI/bge-reranker-v2-m3"]


def test_check_credential_status_disabled_provider_always_ok():
    """未启用的 provider 无论凭证如何配置，状态始终为 ok。"""
    class Provider:
        is_enabled = False
        api_key = None
        api_key_env = None

    assert _check_credential_status(Provider()) == "ok"


def test_check_credential_status_direct_api_key_ok():
    """直接配置了 api_key 的启用 provider 状态为 ok。"""
    class Provider:
        is_enabled = True
        api_key = "sk-test"
        api_key_env = None

    assert _check_credential_status(Provider()) == "ok"


def test_check_credential_status_env_key_exists_ok(monkeypatch):
    """api_key_env 对应的环境变量存在时状态为 ok。"""
    monkeypatch.setenv("TEST_API_KEY", "exists")

    class Provider:
        is_enabled = True
        api_key = None
        api_key_env = "TEST_API_KEY"

    assert _check_credential_status(Provider()) == "ok"


def test_check_credential_status_env_key_missing_warning(monkeypatch):
    """api_key_env 对应的环境变量不存在时状态为 warning。"""
    monkeypatch.delenv("MISSING_KEY", raising=False)

    class Provider:
        is_enabled = True
        api_key = None
        api_key_env = "MISSING_KEY"

    assert _check_credential_status(Provider()) == "warning"


def test_check_credential_status_both_empty_warning():
    """api_key 和 api_key_env 都未配置时状态为 warning。"""
    class Provider:
        is_enabled = True
        api_key = None
        api_key_env = None

    assert _check_credential_status(Provider()) == "warning"
