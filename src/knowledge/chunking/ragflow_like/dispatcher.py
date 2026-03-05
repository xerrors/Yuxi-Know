from __future__ import annotations

from typing import Any

from src.knowledge.chunking.ragflow_like.parsers import book, general, laws, qa
from src.knowledge.chunking.ragflow_like.presets import map_to_internal_parser_id, normalize_chunk_preset_id


def _build_chunk_records(text_chunks: list[str], file_id: str, filename: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for idx, chunk_content in enumerate(text_chunks):
        text = (chunk_content or "").strip()
        if not text:
            continue

        records.append(
            {
                "id": f"{file_id}_chunk_{idx}",
                "content": text,
                "file_id": file_id,
                "filename": filename,
                "chunk_index": idx,
                "source": filename,
                "chunk_id": f"{file_id}_chunk_{idx}",
            }
        )

    return records


def _dispatch_markdown_parser(
    preset_id: str, filename: str, markdown_content: str, parser_config: dict[str, Any]
) -> list[str]:
    parser_id = map_to_internal_parser_id(preset_id)

    if parser_id == "naive":
        return general.chunk_markdown(markdown_content, parser_config)
    if parser_id == "qa":
        return qa.chunk_markdown(filename, markdown_content, parser_config)
    if parser_id == "book":
        return book.chunk_markdown(markdown_content, parser_config)
    if parser_id == "laws":
        return laws.chunk_markdown(filename, markdown_content, parser_config)

    return general.chunk_markdown(markdown_content, parser_config)


def chunk_markdown(
    markdown_content: str, file_id: str, filename: str, processing_params: dict[str, Any]
) -> list[dict[str, Any]]:
    params = dict(processing_params or {})
    preset_id = normalize_chunk_preset_id(params.get("chunk_preset_id"))
    parser_config = params.get("chunk_parser_config") if isinstance(params.get("chunk_parser_config"), dict) else {}

    text_chunks = _dispatch_markdown_parser(preset_id, filename, markdown_content, parser_config)
    return _build_chunk_records(text_chunks, file_id, filename)


def chunk_file(
    file_content: str, file_id: str, filename: str, processing_params: dict[str, Any]
) -> list[dict[str, Any]]:
    # 当前链路中入库前均已转换为 markdown，因此与 chunk_markdown 保持同实现。
    return chunk_markdown(file_content, file_id, filename, processing_params)
