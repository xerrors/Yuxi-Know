"""模型供应商的叶子凭据解析契约。"""

import os

from yuxi.modules.models.tables import ModelProvider


def resolve_api_key(provider: ModelProvider) -> str | None:
    """解析 provider 的 API Key，优先直接配置，其次从环境变量读取。"""
    if provider.api_key:
        return provider.api_key
    if provider.api_key_env:
        return os.getenv(provider.api_key_env)
    return None
