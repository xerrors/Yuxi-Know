from __future__ import annotations

from copy import deepcopy
from typing import Any

from yuxi.utils import logger

CHUNK_PRESET_GENERAL = "general"
CHUNK_PRESET_QA = "qa"
CHUNK_PRESET_BOOK = "book"
CHUNK_PRESET_LAWS = "laws"

CHUNK_PRESET_IDS = {
    CHUNK_PRESET_GENERAL,
    CHUNK_PRESET_QA,
    CHUNK_PRESET_BOOK,
    CHUNK_PRESET_LAWS,
}

CHUNK_PRESET_DESCRIPTIONS: dict[str, str] = {
    CHUNK_PRESET_GENERAL: "通用分块：按分隔符和长度切分，适合大多数普通文档。",
    CHUNK_PRESET_QA: "问答分块：优先抽取问题-回答结构，适合 FAQ、题库、问答手册。",
    CHUNK_PRESET_BOOK: "书籍分块：强化章节标题识别并做层级合并，适合教材、手册、长章节文档。",
    CHUNK_PRESET_LAWS: "法规分块：按法条层级组织与合并，适合法律法规、制度规范类文本。",
}

CHUNK_ENGINE_VERSION = "ragflow_like_v1"
GENERAL_INTERNAL_PARSER_ID = "naive"

_BASE_DEFAULTS: dict[str, Any] = {
    "table_context_size": 0,
    "image_context_size": 0,
}

_PRESET_DEFAULTS: dict[str, dict[str, Any] | None] = {
    CHUNK_PRESET_GENERAL: {
        "layout_recognize": "DeepDOC",
        "chunk_token_num": 512,
        "delimiter": "\n",
        "auto_keywords": 0,
        "auto_questions": 0,
        "html4excel": False,
        "topn_tags": 3,
        "raptor": {
            "use_raptor": True,
            "prompt": (
                "Please summarize the following paragraphs. Be careful with the "
                "numbers, do not make things up. Paragraphs as following:\n"
                "      {cluster_content}\n"
                "The above is the content you need to summarize."
            ),
            "max_token": 256,
            "threshold": 0.1,
            "max_cluster": 64,
            "random_seed": 0,
        },
        "graphrag": {
            "use_graphrag": True,
            "entity_types": ["organization", "person", "geo", "event", "category"],
            "method": "light",
        },
    },
    CHUNK_PRESET_QA: {"raptor": {"use_raptor": False}, "graphrag": {"use_graphrag": False}},
    CHUNK_PRESET_BOOK: {"raptor": {"use_raptor": False}, "graphrag": {"use_graphrag": False}},
    CHUNK_PRESET_LAWS: {"raptor": {"use_raptor": False}, "graphrag": {"use_graphrag": False}},
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def normalize_chunk_preset_id(value: str | None) -> str:
    if not value:
        return CHUNK_PRESET_GENERAL

    normalized = str(value).strip().lower()
    if normalized == GENERAL_INTERNAL_PARSER_ID:
        return CHUNK_PRESET_GENERAL

    if normalized in CHUNK_PRESET_IDS:
        return normalized

    logger.warning(f"Unknown chunk preset id '{value}', fallback to general")
    return CHUNK_PRESET_GENERAL


def map_to_internal_parser_id(preset_id: str) -> str:
    normalized = normalize_chunk_preset_id(preset_id)
    if normalized == CHUNK_PRESET_GENERAL:
        return GENERAL_INTERNAL_PARSER_ID
    return normalized


def get_default_chunk_parser_config(preset_id: str) -> dict[str, Any]:
    normalized = normalize_chunk_preset_id(preset_id)
    default_config = deepcopy(_PRESET_DEFAULTS.get(normalized) or {})
    return deep_merge(_BASE_DEFAULTS, default_config)


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _legacy_params_to_parser_config(params: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(params, dict):
        return {}

    parser_config: dict[str, Any] = {}

    chunk_size = _safe_int(params.get("chunk_size"))
    chunk_overlap = _safe_int(params.get("chunk_overlap"))

    if chunk_size and chunk_size > 0:
        parser_config["chunk_token_num"] = chunk_size
    if chunk_size and chunk_size > 0 and chunk_overlap is not None:
        overlap_percent = round(max(0, min(chunk_overlap, chunk_size - 1)) * 100 / chunk_size)
        parser_config["overlapped_percent"] = max(0, min(overlap_percent, 99))

    if isinstance(params.get("qa_separator"), str) and params.get("qa_separator"):
        parser_config["delimiter"] = params["qa_separator"]

    if isinstance(params.get("delimiter"), str) and params.get("delimiter"):
        parser_config["delimiter"] = params["delimiter"]

    if "chunk_token_num" in params:
        normalized_chunk_token_num = _safe_int(params.get("chunk_token_num"))
        if normalized_chunk_token_num is not None:
            parser_config["chunk_token_num"] = normalized_chunk_token_num

    if "overlapped_percent" in params:
        normalized_overlapped_percent = _safe_int(params.get("overlapped_percent"))
        if normalized_overlapped_percent is not None:
            parser_config["overlapped_percent"] = max(0, min(normalized_overlapped_percent, 99))

    return parser_config


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

    preset_id = normalize_chunk_preset_id(
        request.get("chunk_preset_id") or file_params.get("chunk_preset_id") or kb_additional.get("chunk_preset_id")
    )

    parser_config = get_default_chunk_parser_config(preset_id)

    kb_parser_config = kb_additional.get("chunk_parser_config")
    if isinstance(kb_parser_config, dict):
        parser_config = deep_merge(parser_config, kb_parser_config)

    file_parser_config = file_params.get("chunk_parser_config")
    if isinstance(file_parser_config, dict):
        parser_config = deep_merge(parser_config, file_parser_config)

    req_parser_config = request.get("chunk_parser_config")
    if isinstance(req_parser_config, dict):
        parser_config = deep_merge(parser_config, req_parser_config)

    merged_legacy = {}
    merged_legacy.update(file_params)
    merged_legacy.update(request)
    parser_config = deep_merge(parser_config, _legacy_params_to_parser_config(merged_legacy))

    # Build processing params snapshot (keep existing + request overrides for non-chunk fields)
    snapshot: dict[str, Any] = {}
    snapshot.update(file_params)
    snapshot.update(request)
    snapshot["chunk_preset_id"] = preset_id
    snapshot["chunk_parser_config"] = parser_config
    snapshot["chunk_engine_version"] = CHUNK_ENGINE_VERSION

    # Keep backward-compatible fields for current UI
    if "chunk_size" not in snapshot and isinstance(parser_config.get("chunk_token_num"), int):
        snapshot["chunk_size"] = parser_config["chunk_token_num"]

    if "chunk_overlap" not in snapshot and isinstance(parser_config.get("overlapped_percent"), int):
        token_num = parser_config.get("chunk_token_num")
        if isinstance(token_num, int) and token_num > 0:
            snapshot["chunk_overlap"] = int(token_num * parser_config["overlapped_percent"] / 100)

    if "qa_separator" not in snapshot and isinstance(parser_config.get("delimiter"), str):
        snapshot["qa_separator"] = parser_config["delimiter"]

    return snapshot


def get_chunk_preset_options() -> list[dict[str, str]]:
    return [
        {
            "value": CHUNK_PRESET_GENERAL,
            "label": "General",
            "description": CHUNK_PRESET_DESCRIPTIONS[CHUNK_PRESET_GENERAL],
        },
        {
            "value": CHUNK_PRESET_QA,
            "label": "QA",
            "description": CHUNK_PRESET_DESCRIPTIONS[CHUNK_PRESET_QA],
        },
        {
            "value": CHUNK_PRESET_BOOK,
            "label": "Book",
            "description": CHUNK_PRESET_DESCRIPTIONS[CHUNK_PRESET_BOOK],
        },
        {
            "value": CHUNK_PRESET_LAWS,
            "label": "Laws",
            "description": CHUNK_PRESET_DESCRIPTIONS[CHUNK_PRESET_LAWS],
        },
    ]
