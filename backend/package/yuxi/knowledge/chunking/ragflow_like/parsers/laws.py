from __future__ import annotations

import re
from typing import Any

from yuxi.knowledge.chunking.ragflow_like import nlp

_ARTICLE_PATTERN = re.compile(r"^(第[零一二三四五六七八九十百千万0-9]+条)[\s　:：]*(.*)$")


def _unescape_delimiter(delimiter: str) -> str:
    return delimiter.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t").replace("\\\\", "\\")


def _iter_lines(markdown_content: str) -> list[str]:
    return [line.strip() for line in (markdown_content or "").splitlines() if line.strip()]


def _normalize_law_line(line: str) -> str:
    # 法规 markdown 常见的 #、-、** 装饰会干扰层级识别，这里先做轻量归一化。
    text = (line or "").strip()
    text = re.sub(r"^#{1,6}\s+", "", text)
    text = re.sub(r"^[-*+]\s+", "", text)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _expand_article_line(line: str) -> list[str]:
    normalized = _normalize_law_line(line)
    if not normalized:
        return []

    matched = _ARTICLE_PATTERN.match(normalized)
    if not matched:
        return [normalized]

    article = matched.group(1).strip()
    body = matched.group(2).strip()
    if not body:
        return [article]
    return [article, body]


def _iter_law_sections(markdown_content: str) -> list[str]:
    sections: list[str] = []
    for line in _iter_lines(markdown_content):
        sections.extend(_expand_article_line(line))
    return [section for section in sections if section]


def _docx_heading_tree(markdown_content: str) -> list[str]:
    lines: list[tuple[int, str]] = []
    level_set: set[int] = set()

    for raw in (markdown_content or "").splitlines():
        text = raw.strip()
        if not text:
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", text)
        if heading_match:
            level = len(heading_match.group(1))
            value = heading_match.group(2).strip()
        else:
            level = 99
            value = text

        if not value:
            continue

        lines.append((level, value))
        level_set.add(level)

    if not lines:
        return []

    sorted_levels = sorted(level_set)
    h2_level = sorted_levels[1] if len(sorted_levels) > 1 else 1
    h2_level = sorted_levels[-2] if h2_level == sorted_levels[-1] and len(sorted_levels) > 2 else h2_level

    root = nlp.Node(level=0, depth=h2_level, texts=[])
    root.build_tree(lines)
    return [element for element in root.get_tree() if element]


def _hard_split_by_token_limit(text: str, chunk_token_num: int) -> list[str]:
    token_iter = list(re.finditer(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text or ""))
    if not token_iter:
        cleaned = (text or "").strip()
        return [cleaned] if cleaned else []

    chunks: list[str] = []
    start = 0
    index = 0
    max_tokens = max(int(chunk_token_num or 0), 1)

    while index < len(token_iter):
        end_index = min(index + max_tokens, len(token_iter)) - 1
        end = token_iter[end_index].end()
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        start = end
        index = end_index + 1

    tail = text[start:].strip()
    if tail:
        chunks.append(tail)
    return chunks


def _ensure_chunk_token_limit(
    chunks: list[str], chunk_token_num: int, delimiter: str, overlapped_percent: int
) -> list[str]:
    """
    对输出 chunk 做 token 上限保护：
    1) 先尝试按行用 naive_merge 再切一次；
    2) 仍超长时才硬切，避免 embeddings 413。
    """
    max_tokens = int(chunk_token_num or 0)
    normalized = [chunk.strip() for chunk in chunks if chunk and chunk.strip()]
    if max_tokens <= 0:
        return normalized

    protected: list[str] = []
    for chunk in normalized:
        if nlp.count_tokens(chunk) <= max_tokens:
            protected.append(chunk)
            continue

        refined = nlp.naive_merge(
            [(_line, "") for _line in _iter_lines(chunk)],
            chunk_token_num=max_tokens,
            delimiter=delimiter,
            overlapped_percent=overlapped_percent,
        )
        if not refined:
            refined = [chunk]

        for item in refined:
            cleaned = (item or "").strip()
            if not cleaned:
                continue
            if nlp.count_tokens(cleaned) <= max_tokens:
                protected.append(cleaned)
            else:
                sentence_refined = nlp.naive_merge(
                    [(_sentence, "") for _sentence in re.split(r"(?<=[。！？；;!?])", cleaned) if _sentence.strip()],
                    chunk_token_num=max_tokens,
                    delimiter=delimiter,
                    overlapped_percent=overlapped_percent,
                )
                if not sentence_refined:
                    sentence_refined = [cleaned]

                for sentence_chunk in sentence_refined:
                    text = sentence_chunk.strip()
                    if not text:
                        continue
                    if nlp.count_tokens(text) <= max_tokens:
                        protected.append(text)
                    else:
                        protected.extend(_hard_split_by_token_limit(text, max_tokens))

    return [chunk for chunk in protected if chunk.strip()]


def chunk_markdown(filename: str, markdown_content: str, parser_config: dict[str, Any] | None = None) -> list[str]:
    """
    法规分块主流程（简化版）：
    - docx 优先尝试标题树；
    - 其余格式先做法规文本归一化，再按章/节/条树形切分（depth=3）；
    - 最后统一执行超长保护。
    """
    parser_config = parser_config or {}

    delimiter = _unescape_delimiter(str(parser_config.get("delimiter", "\n") or "\n"))
    chunk_token_num = int(parser_config.get("chunk_token_num", 512) or 512)
    overlapped_percent = int(parser_config.get("overlapped_percent", 0) or 0)

    if re.search(r"\.docx$", filename or "", re.IGNORECASE):
        docx_chunks = _docx_heading_tree(markdown_content)
        if len(docx_chunks) > 1:
            return _ensure_chunk_token_limit(docx_chunks, chunk_token_num, delimiter, overlapped_percent)

    sections = _iter_law_sections(markdown_content)
    if not sections:
        return []

    nlp.remove_contents_table(sections, eng=nlp.is_english(sections))
    typed_sections = [(s, "") for s in sections]
    nlp.make_colon_as_title(typed_sections)

    bull = nlp.bullets_category([s for s, _ in typed_sections])
    if bull == nlp.MARKDOWN_BULLET_GROUP_INDEX:
        # 归一化后仍命中 markdown 组时，回退到中文法规层级组，避免退化成“按章大块”。
        bull = 0

    merged = nlp.tree_merge(bull, typed_sections, depth=3)
    if not merged:
        merged = nlp.naive_merge(
            typed_sections,
            chunk_token_num=chunk_token_num,
            delimiter=delimiter,
            overlapped_percent=overlapped_percent,
        )

    return _ensure_chunk_token_limit(merged, chunk_token_num, delimiter, overlapped_percent)
