from __future__ import annotations

from typing import Any

from yuxi.knowledge.chunking.ragflow_like import nlp


def _unescape_delimiter(delimiter: str) -> str:
    return delimiter.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t").replace("\\\\", "\\")


def _iter_sections(markdown_content: str, delimiter: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    text = markdown_content or ""
    if delimiter and delimiter not in {"\n", "\r\n"} and "`" not in delimiter:
        for part in text.split(delimiter):
            block = part.strip()
            if block:
                sections.append((block, ""))
    else:
        for line in text.splitlines():
            block = line.strip()
            if not block:
                continue
            sections.append((block, ""))

    if not sections and text.strip():
        sections.append((text.strip(), ""))

    return sections


def chunk_markdown(markdown_content: str, parser_config: dict[str, Any] | None = None) -> list[str]:
    parser_config = parser_config or {}

    delimiter = _unescape_delimiter(str(parser_config.get("delimiter", "\n") or "\n"))
    chunk_token_num = int(parser_config.get("chunk_token_num", 512) or 512)
    overlapped_percent = int(parser_config.get("overlapped_percent", 0) or 0)

    sections = _iter_sections(markdown_content, delimiter)
    return nlp.naive_merge(
        sections,
        chunk_token_num=chunk_token_num,
        delimiter=delimiter,
        overlapped_percent=overlapped_percent,
    )
