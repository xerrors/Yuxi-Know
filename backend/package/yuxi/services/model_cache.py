"""模型缓存服务 - 基于 Redis 的跨进程模型信息缓存。

本模块将数据库中的 model_providers 表数据序列化到 Redis，
供 API 和 Worker 等多进程同步读取，避免在同步函数中查询异步数据库。

v2 模型 spec 格式: provider_id:model_id（冒号分隔）
v1 模型 spec 格式: provider/model_name（斜杠分隔）
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from yuxi.utils.logging_config import logger

REDIS_CACHE_KEY = "yuxi:model_cache:v2"
_DEFAULT_REDIS_URL = "redis://redis:6379/0"
_CACHE_TTL_SECONDS = 5


def is_v2_spec_format(spec: str) -> bool:
    """判断 spec 是否为 V2 格式（基于格式特征而非缓存查找）。

    V2 格式的特征是第一个特殊字符为冒号（provider_id:model_id），
    V1 格式的特征是第一个特殊字符为斜杠（provider/model_name）。
    Provider ID 中不包含斜杠，因此第一个特殊字符决定了格式类型。
    """
    colon_pos = spec.find(":")
    slash_pos = spec.find("/")
    if colon_pos == -1:
        return False
    if slash_pos == -1:
        return True
    return colon_pos < slash_pos


@dataclass(frozen=True)
class ModelInfo:
    """不可变的模型信息，供运行时使用。"""

    provider_id: str
    model_id: str
    model_type: str  # chat / embedding / rerank
    display_name: str

    # 运行时配置
    api_key: str
    base_url: str
    provider_type: str  # openai / anthropic / gemini / ollama / openrouter / lmstudio

    # 可选配置
    headers: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    # Embedding 专属
    dimension: int | None = None
    batch_size: int = 40

    @property
    def spec(self) -> str:
        """完整的 spec 标识，格式: provider_id:model_id"""
        return f"{self.provider_id}:{self.model_id}"

    def to_dict(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "model_type": self.model_type,
            "display_name": self.display_name,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "provider_type": self.provider_type,
            "headers": self.headers,
            "extra": self.extra,
            "dimension": self.dimension,
            "batch_size": self.batch_size,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ModelInfo:
        return cls(
            provider_id=data["provider_id"],
            model_id=data["model_id"],
            model_type=data["model_type"],
            display_name=data["display_name"],
            api_key=data["api_key"],
            base_url=data["base_url"],
            provider_type=data["provider_type"],
            headers=data.get("headers", {}),
            extra=data.get("extra", {}),
            dimension=data.get("dimension"),
            batch_size=data.get("batch_size", 40),
        )


class ModelCache:
    """基于 Redis 的模型缓存，所有写入均走 Redis，保证跨进程一致。

    查询接口使用本地内存缓存（带 TTL），避免热路径反复反序列化 JSON。

    注意：本类使用同步 Redis 客户端（redis-py），因为 LangGraph 在初始化模型时
    通过同步路径调用 get_model_info()。后续可统一升级为异步客户端（redis.asyncio）。
    """

    def __init__(self) -> None:
        self._redis = None
        self._local_cache: dict[str, ModelInfo] | None = None
        self._local_cache_at: float = 0.0

    def _get_redis(self):
        """懒加载同步 Redis 客户端，异常时重置以便下次重试。"""
        if self._redis is None:
            try:
                import redis

                redis_url = os.getenv("REDIS_URL", _DEFAULT_REDIS_URL)
                self._redis = redis.from_url(redis_url, decode_responses=True)
            except Exception as e:
                logger.warning(f"Redis client unavailable: {e}")
        return self._redis

    def _reset_redis(self) -> None:
        """重置 Redis 连接，下次调用时重新初始化。"""
        self._redis = None

    def _load_cache(self) -> dict[str, ModelInfo]:
        """从 Redis 同步读取完整缓存，带本地 TTL。"""
        now = time.monotonic()
        if self._local_cache is not None and (now - self._local_cache_at) < _CACHE_TTL_SECONDS:
            return self._local_cache

        r = self._get_redis()
        if r is None:
            return {}
        try:
            raw = r.get(REDIS_CACHE_KEY)
            if not raw:
                self._local_cache = {}
                self._local_cache_at = now
                return {}
            items = json.loads(raw)
            cache = {spec: ModelInfo.from_dict(data) for spec, data in items.items()}
            self._local_cache = cache
            self._local_cache_at = now
            return cache
        except Exception as e:
            logger.warning(f"Failed to load model cache from Redis: {e}")
            self._reset_redis()
            return {}

    def _invalidate_local(self) -> None:
        """使本地缓存失效，下次读取将重新从 Redis 加载。"""
        self._local_cache = None
        self._local_cache_at = 0.0

    def get_model_info(self, spec: str) -> ModelInfo | None:
        """根据 spec 获取模型信息（同步）。"""
        cache = self._load_cache()
        return cache.get(spec)

    def is_v2_spec(self, spec: str) -> bool:
        """判断 spec 是否为 v2 格式（存在于缓存中）。"""
        return self.get_model_info(spec) is not None

    def get_all_specs(self, model_type: str | None = None) -> list[ModelInfo]:
        """获取所有缓存的模型信息，可按类型过滤。"""
        cache = self._load_cache()
        if model_type is None:
            return list(cache.values())
        return [info for info in cache.values() if info.model_type == model_type]

    def get_specs_grouped_by_provider(self, model_type: str = "chat") -> dict[str, list[ModelInfo]]:
        """按 provider 分组获取模型列表（供前端使用）。"""
        cache = self._load_cache()
        grouped: dict[str, list[ModelInfo]] = {}
        for info in cache.values():
            if info.model_type != model_type:
                continue
            grouped.setdefault(info.provider_id, []).append(info)
        return grouped

    def rebuild(self, providers: list[Any]) -> None:
        """从数据库 provider 列表重建缓存并写入 Redis。

        所有修改操作（启动初始化、CRUD）都通过此方法写入，
        保证 Redis 中的数据始终是最新的。
        """
        from yuxi.services.model_provider_service import resolve_api_key

        new_cache: dict[str, ModelInfo] = {}

        for provider in providers:
            if not provider.is_enabled:
                continue

            api_key = resolve_api_key(provider)

            for model in provider.enabled_models or []:
                model_type = model.get("type", "chat")
                base_url = self._get_base_url_for_type(provider, model_type)

                info = ModelInfo(
                    provider_id=provider.provider_id,
                    model_id=model["id"],
                    model_type=model_type,
                    display_name=model.get("display_name", model["id"]),
                    api_key=api_key or "",
                    base_url=base_url,
                    provider_type=provider.provider_type,
                    headers=dict(provider.headers_json or {}),
                    extra=dict(provider.extra_json or {}),
                    dimension=model.get("dimension"),
                    batch_size=model.get("batch_size", 40),
                )
                new_cache[info.spec] = info

        self._save_cache(new_cache)
        self._invalidate_local()
        logger.info(f"Model cache rebuilt: {len(new_cache)} models → Redis")

    def _save_cache(self, cache: dict[str, ModelInfo]) -> None:
        """将完整缓存写入 Redis。"""
        r = self._get_redis()
        if r is None:
            logger.warning("Redis unavailable, cache not saved")
            return
        try:
            data = {spec: info.to_dict() for spec, info in cache.items()}
            r.set(REDIS_CACHE_KEY, json.dumps(data, ensure_ascii=False))
        except Exception as e:
            logger.error(f"Failed to save model cache to Redis: {e}")
            self._reset_redis()

    @staticmethod
    def _get_base_url_for_type(provider: Any, model_type: str) -> str:
        """根据模型类型获取对应的 base_url。"""
        if model_type == "embedding" and provider.embedding_base_url:
            return provider.embedding_base_url
        if model_type == "rerank" and provider.rerank_base_url:
            return provider.rerank_base_url
        return provider.base_url


# 全局单例
model_cache = ModelCache()


def resolve_model_spec(spec: str) -> ModelInfo:
    """统一入口：根据 spec 自动识别 V1/V2 格式并返回 ModelInfo。

    V2 格式（优先）: provider_id:model_id（冒号分隔），从 model_cache 查找
    V1 格式: provider/model_name（斜杠分隔），从 config.model_names 查找

    Raises:
        ValueError: spec 格式无效或模型未找到
    """
    if not spec:
        raise ValueError("spec 不能为空")

    # V2: 第一个特殊字符为冒号则走 v2 路径
    if is_v2_spec_format(spec):
        info = model_cache.get_model_info(spec)
        if info:
            return info
        raise ValueError(f"未找到 V2 模型: {spec}")

    # V1: 从 config 查找（兼容旧版）
    if "/" in spec:
        from yuxi import config

        provider, model_name = spec.split("/", 1)
        model_info = config.model_names.get(provider)
        if not model_info:
            raise ValueError(f"未找到 V1 模型提供者: {provider}")

        import os

        from yuxi.utils import get_docker_safe_url

        api_key = os.getenv(model_info.env) or model_info.env
        return ModelInfo(
            provider_id=provider,
            model_id=model_name,
            model_type="chat",
            display_name=f"{provider}/{model_name}",
            api_key=api_key,
            base_url=get_docker_safe_url(model_info.base_url),
            provider_type="openai",
        )

    raise ValueError(
        f"无效的模型 spec: '{spec}'。V1 格式要求 'provider/model_name'，V2 格式要求 'provider_id:model_id'"
    )
