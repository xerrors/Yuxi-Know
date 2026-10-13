from __future__ import annotations

import re
from typing import Any

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin

from yuxi.infrastructure.observability.logging import logger
from yuxi.modules.knowledge.chunking.ragflow_like.nlp import count_tokens
from yuxi.modules.knowledge.chunking.ragflow_like.utils.md_parser_utils import (
    extract_table_block,
    get_title_path,
    split_text_by_length_and_newline,
)
from yuxi.modules.knowledge.chunking.ragflow_like.utils.table_utils import html_table_to_key_value
from yuxi.modules.knowledge.chunking.source_spans import LocatedText, SourceText, join_source_text


def _flush_content(
    result: list,
    current_content: list,
    title_stack: list,
    max_length: int,
    embed_fn: Any,
    special_element: str = None,
    allow_split: bool = False,
) -> None:
    if not current_content:
        return

    ranges = [part.source_range for part in current_content if hasattr(part, "source_range")]
    source_range = (min(item[0] for item in ranges), max(item[1] for item in ranges)) if ranges else None
    content = (
        join_source_text(current_content, "\n").strip()
        if all(isinstance(part, SourceText) for part in current_content)
        else "\n".join(current_content).strip()
    )
    if source_range is not None and not isinstance(content, SourceText):
        content = LocatedText(content, source_range)
    if not content:
        current_content.clear()
        return

    level = next((i + 1 for i in range(5, -1, -1) if title_stack[i]), 1)
    title_path = get_title_path(title_stack)

    if special_element and not allow_split:
        header = f"{'#' * level} {title_path}|{special_element}" if title_path else f"{'#' * level} {special_element}"
        result.extend([header, content, "-" * 10])
    else:
        if count_tokens(content) > max_length:
            chunks = split_text_by_length_and_newline(content, max_length, embed_fn=embed_fn, token_count_fn=count_tokens)
            cursor = 0
            for idx, chunk in enumerate(chunks, 1):
                base_header = f"{'#' * level} {title_path}" if title_path else f"{'#' * level}"
                if special_element:
                    header = f"{base_header}|{special_element}|Part {idx}"
                else:
                    header = f"{base_header}|Part {idx}"
                if isinstance(content, SourceText):
                    located, cursor = content.map_fragment(chunk, cursor)
                    if not any(position >= 0 for position in located.source_positions):
                        # 未闭合 fence 补出的独立围栏没有原文正文，不单独入库。
                        continue
                else:
                    # HTML 表格转 KV 会重复表头和合并单元格，来源属于原表格块。
                    located = LocatedText(chunk, source_range) if source_range else chunk
                result.extend([header, located, "-" * 10])
        else:
            base_header = f"{'#' * level} {title_path}" if title_path else f"{'#' * level}"
            if special_element:
                header = f"{base_header}|{special_element}"
            else:
                header = base_header

            if header:
                result.append(header)
                result.append("")
            result.extend([content, "-" * 10])

    current_content.clear()


def _handle_image_caption(tokens, i, result, current_content, title_stack, max_length, embed_fn):
    token = tokens[i]
    if token.type != "paragraph_open":
        return False, i

    inline_token = tokens[i + 1]
    if inline_token.type != "inline":
        return False, i

    content = inline_token.content.strip()
    image_pattern = r"^!\[.*?\]\(.*?\)\s*$"
    caption_pattern = r"^(?:Figure|图|Fig\.|表|Table)\s*[\d\w\.]+"

    img_match = re.search(r"^(!\[.*?\]\(.*?\))", content)
    if img_match:
        rest = content[img_match.end() :].strip()
        if rest and re.match(caption_pattern, rest, re.IGNORECASE):
            _flush_content(result, current_content, title_stack, max_length, embed_fn)
            current_content.append(LocatedText(content, tuple(inline_token.map or token.map)))
            caption_title = rest.split("\n")[0].strip()
            _flush_content(result, current_content, title_stack, max_length, embed_fn, special_element=caption_title)
            return True, i + 3

    if re.match(image_pattern, content):
        next_p_idx = i + 3
        if next_p_idx + 1 < len(tokens) and tokens[next_p_idx].type == "paragraph_open":
            next_inline = tokens[next_p_idx + 1]
            if next_inline.type == "inline":
                next_content = next_inline.content.strip()
                if re.match(caption_pattern, next_content, re.IGNORECASE):
                    _flush_content(result, current_content, title_stack, max_length, embed_fn)
                    current_content.append(LocatedText(content, tuple(inline_token.map or token.map)))
                    current_content.append(LocatedText(next_content, tuple(next_inline.map)))
                    _flush_content(result, current_content, title_stack, max_length, embed_fn, special_element=next_content)
                    return True, i + 6

    if current_content and re.match(caption_pattern, content, re.IGNORECASE):
        last_item = current_content[-1].strip()
        if re.match(image_pattern, last_item):
            image_tag = current_content.pop()
            _flush_content(result, current_content, title_stack, max_length, embed_fn)
            current_content.append(image_tag)
            current_content.append(LocatedText(content, tuple(inline_token.map or token.map)))
            _flush_content(result, current_content, title_stack, max_length, embed_fn, special_element=content)
            return True, i + 3

    return False, i


def chunk_markdown(markdown_content: str, parser_config: dict[str, Any] | None = None, embed_fn: Any | None = None) -> list[str]:
    """
    语义化切分 Markdown 内容。

    Args:
        markdown_content: 待切分的 Markdown 文本
        parser_config: 切分参数，如 chunk_token_num
        embed_fn: 可选。传入用于生成向量的函数。如果不传，将从系统配置中加载模型。
                  通过注入此参数可以避免在单元测试中加载重型资源。
    """
    parser_config = parser_config or {}
    max_length = int(parser_config.get("chunk_token_num", 512))
    logger.info(f"语义切分开始: max_length={max_length}, content_length={len(markdown_content)}")

    # 延迟加载重型资源，仅在没有注入 embed_fn 时触发
    if embed_fn is None:
        from yuxi.modules.models.embed import select_embedding_model

        embed_model_id = parser_config.get("embed_model_id")
        if not embed_model_id:
            raise ValueError("语义切分缺少 embed_model_id")
        embed_fn = select_embedding_model(embed_model_id).encode

    md = MarkdownIt("commonmark").enable("table")
    md.use(dollarmath_plugin, allow_space=True, allow_digits=True)

    tokens: list = md.parse(markdown_content)
    source = SourceText(markdown_content.replace("\x00", "\ufffd"))
    breaks = [match.end() for match in re.finditer(r"\r\n|\r|\n", source)]
    source_lines = [source[start:end] for start, end in zip([0, *breaks], [*breaks, len(source)], strict=True)]
    original_lines: list = [str(line).rstrip("\r\n") for line in source_lines]

    result: list = []
    current_content: list = []
    title_stack: list = [""] * 6

    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.type == "heading_open":
            inline_token = tokens[i + 1] if i + 1 < len(tokens) else None
            full_title = inline_token.content.strip() if inline_token and inline_token.type == "inline" else ""
            if not full_title:
                i += 3
                continue

            _flush_content(result, current_content, title_stack, max_length, embed_fn)
            level = int(token.tag[1:]) if token.tag and len(token.tag) > 1 else 1
            title_stack[level - 1] = full_title
            for j in range(level, 6):
                title_stack[j] = ""
            i += 3
            continue
        elif token.type == "table_open":
            _flush_content(result, current_content, title_stack, max_length, embed_fn)
            j, table_content = extract_table_block(tokens, i, original_lines)
            current_content.append(LocatedText(table_content, tuple(token.map)))
            _flush_content(result, current_content, title_stack, max_length, embed_fn, special_element="Table")
            i = j + 1 if j < len(tokens) else len(tokens)
            continue
        elif token.type == "paragraph_open":
            handled, new_i = _handle_image_caption(tokens, i, result, current_content, title_stack, max_length, embed_fn)
            if handled:
                i = new_i
                continue
            inline_token = tokens[i + 1]
            if inline_token.type == "inline":
                part = _map_token_text(inline_token.content.strip(), token.map, source_lines)
                current_content.append(part)
            i += 3
            continue
        elif token.type == "fence":
            first, last = token.map
            opener = source_lines[first]
            opening = opener.find(token.markup)
            closer = source_lines[last - 1]
            body_line_count = token.content.count("\n") + int(bool(token.content) and not token.content.endswith("\n"))
            # token.content 只包含正文行；token.map 多出的最后一行由 MarkdownIt 认定为 closing。
            has_closer = last > first + 1 + body_line_count
            closing = closer.find(token.markup) if has_closer else -1
            body_lines = source_lines[first + 1 : last - int(has_closer)]
            body_source = join_source_text(body_lines) if body_lines else SourceText("", [])
            body, _ = body_source.map_fragment(token.content)
            fence = join_source_text(
                [
                    SourceText("```", opener.source_positions[opening : opening + 3]),
                    "\n",
                    body,
                    "\n",
                    SourceText("```", closer.source_positions[closing : closing + 3] if has_closer else [-1] * 3),
                ]
            )
            fence.source_range = tuple(token.map)
            current_content.append(fence)
            i += 1
            continue
        elif token.type == "ordered_list_open":
            # _flush_content(result, current_content, title_stack, max_length, embed_fn)
            list_content = []
            j = i + 1
            list_item_counter = 1
            while j < len(tokens) and tokens[j].type != "ordered_list_close":
                if tokens[j].type == "list_item_open":
                    k = j + 1
                    while k < len(tokens) and tokens[k].type != "list_item_close":
                        if tokens[k].type == "paragraph_open" and k + 1 < len(tokens) and tokens[k + 1].type == "inline":
                            list_content.append(LocatedText(f"{list_item_counter}. {tokens[k + 1].content.strip()}", tuple(tokens[k].map)))
                            list_item_counter += 1
                        k += 1
                j += 1
            if list_content:
                current_content.extend(list_content)
                _flush_content(result, current_content, title_stack, max_length, embed_fn, special_element=token.type)
            i = j + 1
            continue
        elif token.type == "bullet_list_open":
            # _flush_content(result, current_content, title_stack, max_length, embed_fn)
            list_content = []
            j = i + 1
            while j < len(tokens) and tokens[j].type != "bullet_list_close":
                if tokens[j].type == "list_item_open":
                    k = j + 1
                    while k < len(tokens) and tokens[k].type != "list_item_close":
                        if tokens[k].type == "paragraph_open" and k + 1 < len(tokens) and tokens[k + 1].type == "inline":
                            list_content.append(LocatedText(f"- {tokens[k + 1].content.strip()}", tuple(tokens[k].map)))
                        k += 1
                j += 1
            if list_content:
                current_content.extend(list_content)
                _flush_content(result, current_content, title_stack, max_length, embed_fn, special_element=token.type)
            i = j + 1
            continue
        elif token.type == "html_block":
            _flush_content(result, current_content, title_stack, max_length, embed_fn)
            content = token.content.strip()
            is_converted_table = False
            if "<table" in content.lower():
                try:
                    kv_list = html_table_to_key_value(content)
                    if kv_list:
                        content = "\n".join([f"- {item}" for item in kv_list])
                        is_converted_table = True
                except Exception as e:
                    logger.warning(f"HTML表格转KV失败: {e}")

            current_content.append(LocatedText(content, tuple(token.map)))
            if is_converted_table:
                _flush_content(
                    result,
                    current_content,
                    title_stack,
                    max_length,
                    embed_fn,
                    special_element="Table KV",
                    allow_split=True,
                )
            else:
                _flush_content(result, current_content, title_stack, max_length, embed_fn, special_element=token.type)
            i += 1
            continue
        elif token.type in ["list_item_close", "ordered_list_close", "bullet_list_close", "list_item_open"]:
            i += 1
            continue
        elif token.type == "math_block":
            # _flush_content(result, current_content, title_stack, max_length, embed_fn)
            current_content.append(LocatedText(f"$ {token.content} $", tuple(token.map)))
            _flush_content(result, current_content, title_stack, max_length, embed_fn, special_element="Math Block")
            i += 1
            continue
        else:
            i += 1

    _flush_content(result, current_content, title_stack, max_length, embed_fn)

    chunks = []
    current_chunk_parts = []
    for item in result:
        if item == "-" * 10:
            if current_chunk_parts:
                chunks.append(_join_source_parts(current_chunk_parts))
                current_chunk_parts = []
        else:
            current_chunk_parts.append(item)

    if current_chunk_parts:
        chunks.append(_join_source_parts(current_chunk_parts))

    logger.info(f"语义切分完成: chunks={len(chunks)}")
    return chunks


def _join_source_parts(parts: list[str]) -> str:
    """合并生成标题与正文，并保留正文 token 的原文范围。"""
    ranges = [part.source_range for part in parts if isinstance(part, LocatedText)]
    content = join_source_text(parts, "\n").strip()
    if isinstance(content, SourceText):
        return content
    if not ranges:
        return content
    return LocatedText(
        content,
        (min(item[0] for item in ranges), max(item[1] for item in ranges)),
    )


def _map_token_text(content: str, source_range: list[int], source_lines: list[SourceText]) -> SourceText:
    """在 token 已知的原文范围中映射正文，避免跨块反查重复文本。"""
    source = join_source_text(source_lines[source_range[0] : source_range[1]])
    mapped, _ = source.map_fragment(content)
    mapped.source_range = tuple(source_range)
    return mapped
