# ruff: noqa: E501

import asyncio
import os
import re
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from yuxi.repositories.model_provider_repository import (
    create_model_provider,
    delete_model_provider,
    get_model_provider,
    list_model_providers,
    update_model_provider,
)
from yuxi.storage.postgres.models_business import ModelProvider

VALID_MODEL_TYPES = {"chat", "embedding", "rerank"}
VALID_MODEL_SOURCES = {"manual", "remote"}
VALID_PROVIDER_TYPES = {"openai", "anthropic", "gemini", "ollama", "openrouter", "lmstudio"}
_PROVIDER_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{1,99}$")
DEFAULT_MODELS_ENDPOINT = ""
DEFAULT_EMBEDDING_MODELS_ENDPOINT = ""

_DEFAULT_BUILTIN_PROVIDERS: list[dict[str, Any]] = [
    {
        "provider_id": "openai",
        "display_name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "models_endpoint": "https://api.openai.com/v1/models",
    },
    {
        "provider_id": "anthropic",
        "display_name": "Anthropic",
        "base_url": "https://api.anthropic.com",
        "api_key_env": "ANTHROPIC_API_KEY",
        "models_endpoint": "https://api.anthropic.com/models",
    },
    {
        "provider_id": "google",
        "display_name": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com",
        "api_key_env": "GEMINI_API_KEY",
        "models_endpoint": "https://generativelanguage.googleapis.com/v1beta/models",
    },
    {
        "provider_id": "ollama-cloud",
        "display_name": "Ollama",
        "base_url": "http://localhost:11434",
        "models_endpoint": "http://localhost:11434/api/tags",
    },
    {
        "provider_id": "lmstudio",
        "display_name": "LM Studio",
        "base_url": "http://localhost:1234/v1",
        "models_endpoint": "http://localhost:1234/v1/models",
    },
    {
        "provider_id": "deepseek",
        "display_name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "models_endpoint": "https://api.deepseek.com/models",
    },
    {
        "provider_id": "alibaba",
        "display_name": "DashScope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
        "models_endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/models",
    },
    {
        "provider_id": "alibaba-coding-plan-cn",
        "display_name": "Aliyun Coding Plan",
        "base_url": "https://coding.dashscope.aliyuncs.com/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
        "models_endpoint": "https://coding.dashscope.aliyuncs.com/v1/models",
    },
    {
        "provider_id": "alibaba-coding-plan",
        "display_name": "Aliyun Coding Plan (International)",
        "base_url": "https://coding-intl.dashscope.aliyuncs.com/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
        "models_endpoint": "https://coding-intl.dashscope.aliyuncs.com/v1/models",
    },
    {
        "provider_id": "zhipuai",
        "display_name": "Zhipu (BigModel)",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_env": "ZHIPUAI_API_KEY",
        "models_endpoint": "https://open.bigmodel.cn/api/paas/v4/models",
    },
    {
        "provider_id": "zhipuai-coding-plan",
        "display_name": "Zhipu Coding Plan (BigModel)",
        "base_url": "https://open.bigmodel.cn/api/coding/paas/v4",
        "api_key_env": "ZHIPUAI_API_KEY",
        "models_endpoint": "https://open.bigmodel.cn/api/coding/paas/v4/models",
    },
    {
        "provider_id": "zai",
        "display_name": "Zhipu (Z.AI)",
        "base_url": "https://api.z.ai/api/paas/v4",
        "api_key_env": "ZAI_API_KEY",
        "models_endpoint": "https://api.z.ai/api/paas/v4/models",
    },
    {
        "provider_id": "zai-coding-plan",
        "display_name": "Zhipu Coding Plan (Z.AI)",
        "base_url": "https://api.z.ai/api/coding/paas/v4",
        "api_key_env": "ZAI_API_KEY",
        "models_endpoint": "https://api.z.ai/api/coding/paas/v4/models",
    },
    {
        "provider_id": "moonshotai-cn",
        "display_name": "Moonshot",
        "base_url": "https://api.moonshot.cn/v1",
        "api_key_env": "MOONSHOT_API_KEY",
        "models_endpoint": "https://api.moonshot.cn/v1/models",
    },
    {
        "provider_id": "moonshotai",
        "display_name": "Moonshot (International)",
        "base_url": "https://api.moonshot.ai/v1",
        "api_key_env": "MOONSHOT_API_KEY",
        "models_endpoint": "https://api.moonshot.ai/v1/models",
    },
    {
        "provider_id": "minimax-cn",
        "display_name": "MiniMax",
        "base_url": "https://api.minimaxi.com/v1",
        "api_key_env": "MINIMAX_API_KEY",
        "models_endpoint": "https://api.minimaxi.com/v1/models",
    },
    {
        "provider_id": "minimax",
        "display_name": "MiniMax (International)",
        "base_url": "https://api.minimax.io/v1",
        "api_key_env": "MINIMAX_API_KEY",
        "models_endpoint": "https://api.minimax.io/v1/models",
    },
    {
        "provider_id": "openrouter",
        "display_name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "capabilities": ["chat", "embedding"],
        "embedding_base_url": "https://openrouter.ai/api/v1/embeddings",
        "models_endpoint": "https://openrouter.ai/api/v1/models",
        "embedding_models_endpoint": "https://openrouter.ai/api/v1/embeddings/models",
    },
    {
        "provider_id": "modelscope",
        "display_name": "ModelScope",
        "base_url": "https://api-inference.modelscope.cn/v1",
        "api_key_env": "MODELSCOPE_ACCESS_TOKEN",
        "models_endpoint": "https://api-inference.modelscope.cn/v1/models",
    },
    {
        "provider_id": "opencode",
        "display_name": "OpenCode",
        "base_url": "https://opencode.ai/zen/v1",
        "models_endpoint": "https://opencode.ai/zen/v1/models",
    },
    {
        "provider_id": "siliconflow-cn",
        "display_name": "SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "embedding_base_url": "https://api.siliconflow.cn/v1/embeddings",
        "rerank_base_url": "https://api.siliconflow.cn/v1/rerank",
        "api_key_env": "SILICONFLOW_API_KEY",
        "capabilities": ["chat", "embedding", "rerank"],
        "models_endpoint": "https://api.siliconflow.cn/v1/models?sub_type=chat",
        "embedding_models_endpoint": "https://api.siliconflow.cn/v1/models?sub_type=embedding",
        "rerank_models_endpoint": "https://api.siliconflow.cn/v1/models?sub_type=reranker",
        "enabled_models": [
            {"id": "Pro/deepseek-ai/DeepSeek-V3.2", "type": "chat", "display_name": "Pro/deepseek-ai/DeepSeek-V3.2"},
            {"id": "Pro/MiniMaxAI/MiniMax-M2.5", "type": "chat", "display_name": "Pro/MiniMaxAI/MiniMax-M2.5"},
            {
                "id": "Pro/BAAI/bge-m3",
                "type": "embedding",
                "display_name": "Pro/BAAI/bge-m3",
                "dimension": 1024,
                "batch_size": 40,
            },
            {
                "id": "BAAI/bge-m3",
                "type": "embedding",
                "display_name": "BAAI/bge-m3",
                "dimension": 1024,
                "batch_size": 40,
            },
            {
                "id": "Qwen/Qwen3-Embedding-0.6B",
                "type": "embedding",
                "display_name": "Qwen/Qwen3-Embedding-0.6B",
                "dimension": 1024,
                "batch_size": 40,
            },
            {
                "id": "Pro/BAAI/bge-reranker-v2-m3",
                "type": "rerank",
                "display_name": "Pro/BAAI/bge-reranker-v2-m3",
            },
            {
                "id": "BAAI/bge-reranker-v2-m3",
                "type": "rerank",
                "display_name": "BAAI/bge-reranker-v2-m3",
            },
        ],
    },
    {
        "provider_id": "siliconflow",
        "display_name": "SiliconFlow (International)",
        "base_url": "https://api.siliconflow.com/v1",
        "embedding_base_url": "https://api.siliconflow.com/v1/embeddings",
        "rerank_base_url": "https://api.siliconflow.com/v1/rerank",
        "api_key_env": "SILICONFLOW_API_KEY",
        "capabilities": ["chat", "embedding", "rerank"],
        "models_endpoint": "https://api.siliconflow.com/v1/models?sub_type=chat",
        "embedding_models_endpoint": "https://api.siliconflow.com/v1/models?sub_type=embedding",
        "rerank_models_endpoint": "https://api.siliconflow.com/v1/models?sub_type=reranker",
        "enabled_models": [
            {"id": "deepseek-ai/DeepSeek-V3.2", "type": "chat", "display_name": "deepseek-ai/DeepSeek-V3.2"},
            {"id": "MiniMaxAI/MiniMax-M2.5", "type": "chat", "display_name": "MiniMaxAI/MiniMax-M2.5"},
            {
                "id": "Pro/BAAI/bge-m3",
                "type": "embedding",
                "display_name": "Pro/BAAI/bge-m3",
                "dimension": 1024,
                "batch_size": 40,
            },
            {
                "id": "BAAI/bge-m3",
                "type": "embedding",
                "display_name": "BAAI/bge-m3",
                "dimension": 1024,
                "batch_size": 40,
            },
            {
                "id": "Qwen/Qwen3-Embedding-0.6B",
                "type": "embedding",
                "display_name": "Qwen/Qwen3-Embedding-0.6B",
                "dimension": 1024,
                "batch_size": 40,
            },
            {
                "id": "Pro/BAAI/bge-reranker-v2-m3",
                "type": "rerank",
                "display_name": "Pro/BAAI/bge-reranker-v2-m3",
            },
            {
                "id": "BAAI/bge-reranker-v2-m3",
                "type": "rerank",
                "display_name": "BAAI/bge-reranker-v2-m3",
            },
        ],
    },
]


def _normalize_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _normalize_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _validate_provider_id(provider_id: str) -> None:
    if not _PROVIDER_ID_RE.match(provider_id):
        raise ValueError("provider_id 只能包含字母、数字、下划线和中划线，长度 2-100")


def _normalize_model_item(model: dict[str, Any]) -> dict[str, Any]:
    """规范化模型配置对象，校验运行所需字段。"""
    model_id = str(model.get("id") or "").strip()
    if not model_id:
        raise ValueError("模型 id 不能为空")

    model_type = str(model.get("type") or "unknown").strip()
    if model_type not in VALID_MODEL_TYPES:
        raise ValueError(f"启用模型 {model_id} 的 type 必须是 chat、embedding 或 rerank")

    # source 区分手动添加 vs 远端拉取，用于跳过远端清单存在性的视觉警告。
    source = str(model.get("source") or "remote").strip()
    if source not in VALID_MODEL_SOURCES:
        raise ValueError(f"模型 {model_id} 的 source 必须是 manual 或 remote")

    normalized = dict(model)
    normalized["id"] = model_id
    normalized["type"] = model_type
    normalized["source"] = source
    normalized["display_name"] = str(model.get("display_name") or model.get("name") or model_id)
    normalized["extra"] = _normalize_dict(model.get("extra"))

    if model_type == "embedding":
        dimension = normalized.get("dimension")
        if dimension not in (None, ""):
            normalized["dimension"] = int(dimension)
        if normalized.get("batch_size") not in (None, ""):
            normalized["batch_size"] = int(normalized["batch_size"])

    return normalized


def _normalize_model_list(models: Any) -> list[dict[str, Any]]:
    normalized_models: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in _normalize_list(models):
        if not isinstance(item, dict):
            raise ValueError("模型配置必须是对象列表")
        normalized = _normalize_model_item(item)
        if normalized["id"] in seen_ids:
            raise ValueError(f"模型 id 重复: {normalized['id']}")
        seen_ids.add(normalized["id"])
        normalized_models.append(normalized)
    return normalized_models


def _validate_models_capabilities(enabled_models: list[dict], capabilities: set[str]) -> None:
    """校验 enabled_models 中所有模型的 type 都在 provider capabilities 范围内。"""
    for model in enabled_models or []:
        if model["type"] not in capabilities:
            raise ValueError(f"模型 {model['id']} 的 type={model['type']} 不在 provider 能力 {sorted(capabilities)} 内")


def _normalize_payload(data: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    payload = dict(data)
    if not partial or "provider_id" in payload:
        provider_id = str(payload.get("provider_id") or "").strip()
        _validate_provider_id(provider_id)
        payload["provider_id"] = provider_id

    if not partial or "display_name" in payload:
        display_name = str(payload.get("display_name") or "").strip()
        if not display_name:
            raise ValueError("display_name 不能为空")
        payload["display_name"] = display_name

    if not partial or "base_url" in payload:
        base_url = str(payload.get("base_url") or "").strip()
        if not base_url:
            raise ValueError("base_url 不能为空")
        payload["base_url"] = base_url

    for endpoint_field, default_endpoint in (
        ("models_endpoint", DEFAULT_MODELS_ENDPOINT),
        ("embedding_models_endpoint", DEFAULT_EMBEDDING_MODELS_ENDPOINT),
        ("rerank_models_endpoint", None),
    ):
        if endpoint_field in payload:
            endpoint = str(payload.get(endpoint_field) or "").strip()
            payload[endpoint_field] = endpoint or default_endpoint
        elif not partial and default_endpoint is not None:
            payload[endpoint_field] = default_endpoint

    provider_type = payload.get("provider_type")
    if provider_type is None and not partial:
        payload["provider_type"] = "openai"
    elif provider_type is not None:
        if provider_type not in VALID_PROVIDER_TYPES:
            raise ValueError(f"provider_type 必须是 {', '.join(sorted(VALID_PROVIDER_TYPES))} 之一")

    if "capabilities" in payload:
        payload["capabilities"] = _normalize_list(payload.get("capabilities"))
    elif not partial:
        payload["capabilities"] = []

    capabilities = set(payload.get("capabilities") or [])
    if "embedding" in capabilities:
        embedding_base_url = str(payload.get("embedding_base_url") or "").strip()
        if not embedding_base_url:
            raise ValueError("embedding provider 必须配置 embedding_base_url")
        payload["embedding_base_url"] = embedding_base_url
        embedding_endpoint = str(payload.get("embedding_models_endpoint") or "").strip()
        if embedding_endpoint and not embedding_endpoint.startswith(("http://", "https://")):
            raise ValueError("embedding_models_endpoint 必须是完整的 HTTP URL")
        payload["embedding_models_endpoint"] = embedding_endpoint
    if "rerank" in capabilities:
        rerank_base_url = str(payload.get("rerank_base_url") or "").strip()
        if not rerank_base_url:
            raise ValueError("rerank provider 必须配置 rerank_base_url")
        payload["rerank_base_url"] = rerank_base_url
        rerank_endpoint = str(payload.get("rerank_models_endpoint") or "").strip()
        if rerank_endpoint and not rerank_endpoint.startswith(("http://", "https://")):
            raise ValueError("rerank_models_endpoint 必须是完整的 HTTP URL")
        payload["rerank_models_endpoint"] = rerank_endpoint

    if "enabled_models" in payload:
        payload["enabled_models"] = _normalize_model_list(payload.get("enabled_models"))
    elif not partial:
        payload["enabled_models"] = []

    if "headers_json" in payload:
        payload["headers_json"] = _normalize_dict(payload.get("headers_json"))
    elif not partial:
        payload["headers_json"] = {}

    if "extra_json" in payload:
        payload["extra_json"] = _normalize_dict(payload.get("extra_json"))
    elif not partial:
        payload["extra_json"] = {}

    if "is_enabled" in payload:
        payload["is_enabled"] = bool(payload["is_enabled"])
    elif not partial:
        payload["is_enabled"] = True

    if "is_builtin" in payload:
        payload["is_builtin"] = bool(payload["is_builtin"])
    elif not partial:
        payload["is_builtin"] = False

    # 仅当本次 payload 同时携带 capabilities 与 enabled_models 时做一致性校验，
    # 防止前端把超出 provider.capabilities 的模型 type 写入。
    # partial 模式下若只更新其中一项，跳过校验避免误判（DB 已有值不可见）。
    if "capabilities" in payload and "enabled_models" in payload:
        capabilities_set = set(payload.get("capabilities") or [])
        if capabilities_set:
            _validate_models_capabilities(payload.get("enabled_models"), capabilities_set)

    return payload


def _resolve_api_key(provider: ModelProvider) -> str | None:
    if provider.api_key:
        return provider.api_key
    if provider.api_key_env:
        return os.getenv(provider.api_key_env)
    return None


def _check_credential_status(provider: ModelProvider) -> str:
    """检查 provider 的凭证配置状态。仅对启用的 provider 做校验。"""
    if not provider.is_enabled:
        return "ok"
    if provider.api_key:
        return "ok"
    if provider.api_key_env:
        return "ok" if os.getenv(provider.api_key_env) else "warning"
    return "warning"


def _models_url(base_url: str, endpoint: str | None = DEFAULT_MODELS_ENDPOINT) -> str:
    base = base_url.rstrip("/")
    if not endpoint:
        return base
    endpoint = endpoint.strip()
    if endpoint.startswith(("http://", "https://")):
        return endpoint
    return f"{base}/{endpoint.lstrip('/')}"


def _normalize_remote_model(raw_model: dict[str, Any], model_type: str = "chat") -> dict[str, Any]:
    model_id = str(raw_model.get("id") or "").strip()
    if not model_id:
        return {}

    architecture = _normalize_dict(raw_model.get("architecture"))
    top_provider = _normalize_dict(raw_model.get("top_provider"))
    raw_type = raw_model.get("type")
    normalized_type = raw_type if raw_type in VALID_MODEL_TYPES else model_type
    normalized = {
        "id": model_id,
        "object": raw_model.get("object"),
        "created": raw_model.get("created"),
        "owned_by": raw_model.get("owned_by"),
        "type": normalized_type,
        "display_name": raw_model.get("name") or model_id,
        "description": raw_model.get("description"),
        "context_length": raw_model.get("context_length") or top_provider.get("context_length"),
        "max_completion_tokens": top_provider.get("max_completion_tokens"),
        "input_modalities": architecture.get("input_modalities") or [],
        "output_modalities": architecture.get("output_modalities") or [],
        "supported_parameters": raw_model.get("supported_parameters") or [],
        "pricing": raw_model.get("pricing") or {},
        "default_parameters": raw_model.get("default_parameters") or {},
        "raw_metadata": raw_model,
        "extra": {},
    }
    return {key: value for key, value in normalized.items() if value is not None}


async def get_all_model_providers(db: AsyncSession) -> list[ModelProvider]:
    """获取全部独立模型供应商配置。"""
    return await list_model_providers(db)


async def get_model_provider_by_id(db: AsyncSession, provider_id: str) -> ModelProvider | None:
    """按 provider_id 获取独立模型供应商配置。"""
    return await get_model_provider(db, provider_id)


async def ensure_builtin_model_providers_in_db(db: AsyncSession) -> None:
    """确保独立模型配置模块的内置 provider 模板存在。

    这里只补不存在的内置 provider，不覆盖管理员已编辑的配置。
    """
    existing = await list_model_providers(db)
    existing_ids = {p.provider_id: p for p in existing}

    for provider_def in _DEFAULT_BUILTIN_PROVIDERS:
        provider_id = provider_def["provider_id"]
        existing_provider = existing_ids.get(provider_id)
        if existing_provider:
            if not existing_provider.enabled_models and provider_def.get("enabled_models"):
                existing_provider.enabled_models = _normalize_model_list(provider_def["enabled_models"])
                existing_provider.capabilities = provider_def.get("capabilities") or existing_provider.capabilities
                existing_provider.updated_by = "system"
                await db.flush()
            continue

        payload = {key: value for key, value in provider_def.items() if value is not None}
        payload["enabled_models"] = provider_def.get("enabled_models", [])
        payload["headers_json"] = payload.get("headers_json") or {}
        payload["extra_json"] = payload.get("extra_json") or {}
        payload["is_enabled"] = provider_id == "siliconflow-cn"
        payload["is_builtin"] = True
        payload["created_by"] = "system"
        payload["updated_by"] = "system"
        await create_model_provider(db, _normalize_payload(payload))


async def create_provider_config(db: AsyncSession, data: dict[str, Any], username: str) -> ModelProvider:
    """创建独立模型供应商配置。"""
    payload = _normalize_payload(data)
    if await get_model_provider(db, payload["provider_id"]):
        raise ValueError(f"供应商 {payload['provider_id']} 已存在")
    payload["created_by"] = username
    payload["updated_by"] = username
    return await create_model_provider(db, payload)


async def update_provider_config(
    db: AsyncSession,
    provider_id: str,
    data: dict[str, Any],
    username: str,
) -> ModelProvider | None:
    """更新独立模型供应商配置。"""
    provider = await get_model_provider(db, provider_id)
    if provider is None:
        return None
    payload = _normalize_payload(data, partial=True)
    # partial 更新时仅传 enabled_models，结合 DB 中现有 capabilities 校验
    if "enabled_models" in payload and "capabilities" not in payload:
        existing_caps = set(provider.capabilities or [])
        if existing_caps:
            _validate_models_capabilities(payload.get("enabled_models"), existing_caps)
    payload["updated_by"] = username
    return await update_model_provider(db, provider, payload)


async def delete_provider_config(db: AsyncSession, provider_id: str) -> bool:
    """删除独立模型供应商配置。"""
    provider = await get_model_provider(db, provider_id)
    if provider is None:
        return False
    await delete_model_provider(db, provider)
    return True


async def _fetch_models_from_endpoint(
    client: httpx.AsyncClient,
    provider: ModelProvider,
    headers: dict[str, str],
    endpoint: str | None,
    model_type: str,
) -> list[dict[str, Any]]:
    """按单个模型类型端点拉取并规范化远端模型列表。"""
    if not endpoint:
        return []

    response = await client.get(_models_url(provider.base_url, endpoint), headers=headers)
    response.raise_for_status()
    payload = response.json()

    raw_models = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(raw_models, list):
        raise ValueError(f"{endpoint} 响应必须是列表或包含 data 列表")

    models = []
    for raw_model in raw_models:
        if isinstance(raw_model, dict):
            normalized = _normalize_remote_model(raw_model, model_type)
            if normalized:
                models.append(normalized)
    return models


async def fetch_remote_models(provider: ModelProvider) -> list[dict[str, Any]]:
    """按 provider 配置实时拉取远端模型列表，不落库。

    Chat 模型默认走 /models；embedding 只有 provider 声明能力时才走
    /embeddings/models；rerank 供应商没有稳定通用端点，配置了 endpoint 才拉取。
    """
    headers = dict(provider.headers_json or {})
    api_key = _resolve_api_key(provider)
    if api_key:
        headers.setdefault("Authorization", f"Bearer {api_key}")

    capabilities = set(provider.capabilities or [])
    endpoint_specs = [
        (provider.models_endpoint or DEFAULT_MODELS_ENDPOINT, "chat"),
    ]
    if "embedding" in capabilities:
        endpoint_specs.append((provider.embedding_models_endpoint or DEFAULT_EMBEDDING_MODELS_ENDPOINT, "embedding"))
    if "rerank" in capabilities and provider.rerank_models_endpoint:
        endpoint_specs.append((provider.rerank_models_endpoint, "rerank"))

    seen_ids: set[tuple[str, str]] = set()
    models: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        results = await asyncio.gather(
            *[
                _fetch_models_from_endpoint(client, provider, headers, endpoint, model_type)
                for endpoint, model_type in endpoint_specs
            ]
        )
        for fetched_models in results:
            for model in fetched_models:
                model_key = (model["id"], model["type"])
                if model_key in seen_ids:
                    continue
                seen_ids.add(model_key)
                models.append(model)
    return models
