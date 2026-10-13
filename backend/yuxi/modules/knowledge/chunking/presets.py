from __future__ import annotations

from copy import deepcopy
from typing import Any

from yuxi.infrastructure.observability.logging import logger

DEFAULT_CHUNK_PRESET_ID = "general"

CHUNK_PRESETS: dict[str, dict[str, str]] = {
    "general": {
        "label": "General",
        "description": "通用分块：按分隔符和长度切分，适合大多数普通文档。",
    },
    "qa": {
        "label": "QA",
        "description": "问答分块：优先抽取问题-回答结构，适合 FAQ、题库、问答手册。",
    },
    "book": {
        "label": "Book",
        "description": "书籍分块：强化章节标题识别并做层级合并，适合教材、手册、长章节文档。",
    },
    "laws": {
        "label": "Laws",
        "description": "法规分块：按法条层级组织与合并，适合法律法规、制度规范类文本。",
    },
    "semantic": {
        "label": "Semantic",
        "description": "语义分块：利用嵌入和聚类算法进行语义切分，并自动增强标题上下文。",
    },
    "separator": {
        "label": "Separator",
        "description": "严格分隔：命中分隔符即切分，仅超长片段内部继续按长度切分。",
    },
}

CHUNK_PRESET_IDS = set(CHUNK_PRESETS)

CHUNK_ENGINE_VERSION = "ragflow_like_v1"
GENERAL_INTERNAL_PARSER_ID = "naive"


class ChunkConfigError(ValueError):
    """分块配置非法，管理读取可保留原值供修复。"""


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def normalize_chunk_preset_id(value: str | None) -> str:
    """保留缺省与内部别名，拒绝显式非法策略。"""
    if value is None or value == "":
        return DEFAULT_CHUNK_PRESET_ID
    if not isinstance(value, str):
        raise ChunkConfigError("chunk_preset_id 必须是字符串")
    normalized = value.strip().lower()
    if normalized == GENERAL_INTERNAL_PARSER_ID:
        return DEFAULT_CHUNK_PRESET_ID

    if normalized in CHUNK_PRESET_IDS:
        return normalized

    raise ChunkConfigError(f"未知 chunk_preset_id: {value}")


def map_to_internal_parser_id(preset_id: str) -> str:
    normalized = normalize_chunk_preset_id(preset_id)
    if normalized == DEFAULT_CHUNK_PRESET_ID:
        return GENERAL_INTERNAL_PARSER_ID
    return normalized


def ensure_chunk_defaults_in_additional_params(additional_params: dict[str, Any] | None) -> dict[str, Any]:
    params = dict(additional_params or {})
    params["chunk_preset_id"] = normalize_chunk_preset_id(params.get("chunk_preset_id"))

    if "chunk_parser_config" in params and not isinstance(params.get("chunk_parser_config"), dict):
        logger.warning("Invalid chunk_parser_config in additional_params, fallback to empty dict")
        params["chunk_parser_config"] = {}

    return params


def resolve_chunk_processing_params(
    kb_additional_params: dict[str, Any] | None,
    file_processing_params: dict[str, Any] | None,
    request_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    kb_additional = ensure_chunk_defaults_in_additional_params(kb_additional_params)
    file_params = dict(file_processing_params or {})
    request = dict(request_params or {})

    preset_id = kb_additional["chunk_preset_id"]
    for params in (file_params, request):
        value = params.get("chunk_preset_id")
        if value is not None and value != "":
            preset_id = value
    preset_id = normalize_chunk_preset_id(preset_id)

    parser_config: dict[str, Any] = {}

    kb_parser_config = kb_additional.get("chunk_parser_config")
    if isinstance(kb_parser_config, dict):
        parser_config = deep_merge(parser_config, kb_parser_config)

    file_parser_config = file_params.get("chunk_parser_config")
    if isinstance(file_parser_config, dict):
        parser_config = deep_merge(parser_config, file_parser_config)

    req_parser_config = request.get("chunk_parser_config")
    if isinstance(req_parser_config, dict):
        parser_config = deep_merge(parser_config, req_parser_config)

    return {
        "chunk_preset_id": preset_id,
        "chunk_parser_config": parser_config,
        "chunk_engine_version": CHUNK_ENGINE_VERSION,
    }


def get_chunk_preset_options() -> list[dict[str, str]]:
    return [
        {"value": preset_id, "label": preset["label"], "description": preset["description"]} for preset_id, preset in CHUNK_PRESETS.items()
    ]
