from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from .semantic_utils import semantic_chunking_with_auto_clusters


def infer_heading_level(title: str) -> int:
    """
    根据标题文本推断其层级级别（1-6级）。

    逻辑说明：
    1. 数字序号推断：
       - 匹配如 "1.", "1.1", "1.2.3" 等格式。
       - 根据点号分隔的数量确定层级，例如 "1.1" 为 2 级，"1.2.3" 为 3 级。
       - 层级限制在 1-6 之间。
    2. 中文序号推断：
       - 匹配如 "一、", "二." 等中文数字序号。
       - 统一归类为 1 级标题。
    3. 默认处理：
       - 若不匹配以上规则，默认返回 1 级。
    """
    m = re.match(r"^\s*(\d+(?:\.\d+)*)[.)、]?\s*", title)
    if m:
        return max(1, min(len(m.group(1).split(".")), 6))
    m_zh = re.match(r"^\s*[一二三四五六七八九十百千]+[、.]\s*", title)
    if m_zh:
        return 1
    return 1


def get_title_path(stack: list[str]) -> str:
    """
    根据标题栈生成标题路径，用"|"分隔。
    """
    return "|".join([t for t in stack if t])


def extract_table_block(tokens: list[Any], i: int, original_lines: list[str]) -> tuple[int, str]:
    """
    从token流和原始文本中提取完整的表格块。

    逻辑说明：
    1. 定位起始：通过当前 token (i) 的 `map` 属性获取表格在原始行中的起始行号 `table_start`。
    2. 查找结束 token：遍历后续 tokens 直到找到 `table_close`。
    3. 确定结束行号 (`table_end`)：
       - 优先使用 `table_close` token 的 `map` 属性。
       - 若不存在，则尝试查找下一个带有 `map` 信息的 token 的起始行作为当前表格的结束。
       - 若上述均失败（如文件末尾或解析异常），则回退到基于文本内容的启发式扫描：
         从 `table_start` 开始向下扫描，直到遇到不符合 Markdown 表格特征（不以 '|' 开头且不含 '|'）的行为止。
    4. 返回结果：返回 `table_close` 的索引 `j` 以及拼接后的表格原始字符串。
    """
    token = tokens[i]
    table_start = token.map[0] if token.map else 0
    j = i + 1
    while j < len(tokens) and tokens[j].type != "table_close":
        j += 1
    if j < len(tokens):
        end_token = tokens[j]
        if end_token.map and end_token.map[1] is not None:
            table_end = end_token.map[1]
        else:
            table_end = None
            for k in range(j + 1, len(tokens)):
                if tokens[k].map and tokens[k].map[0] is not None:
                    table_end = tokens[k].map[0]
                    break
            if table_end is None:
                table_end = table_start + 1
                for line_idx in range(table_start, len(original_lines)):
                    line = original_lines[line_idx].strip()
                    if not line or not (line.startswith("|") or "|" in line):
                        table_end = line_idx
                        break
    else:
        table_end = table_start + 1
        for line_idx in range(table_start, len(original_lines)):
            line = original_lines[line_idx].strip()
            if not line or not (line.startswith("|") or "|" in line):
                table_end = line_idx
                break
    return j, "\n".join(original_lines[table_start:table_end])


def split_text_by_length_and_newline(
    text: str, max_length: int, embed_fn: Callable[[list[str]], Any] | None, token_count_fn: Callable[[str], int]
) -> list[str]:
    """
    层次化文本切分策略。
    """
    chunks = []

    paragraphs = text.split("\n\n")

    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        paragraph_token_count = token_count_fn(paragraph)

        # 如果当前段落长度未超过最大 Token 数量，直接作为独立分块放入chunks
        # 否则继续尝试按行切分
        if paragraph_token_count <= max_length:
            chunks.append(paragraph)
            continue

        # 把段落进一步使用换行符进行切分为行
        lines = paragraph.split("\n")
        current_chunk_lines = []
        current_chunk_tokens = 0

        for line in lines:
            line = line.strip()
            if not line:  # 跳过空行
                continue

            line_token_count = token_count_fn(line)  # 计算当前行的 Token 数量
            # 为了考虑行之间的空格，需要在计算 Token 数量时加 1（如果当前行不是第一行，需要添加一个换行符的Token数量）
            added_tokens = line_token_count + (1 if current_chunk_lines else 0)
            # 如果当前行的 Token 数量超过最大 Token 数量，直接作为独立分块放入chunks
            if line_token_count > max_length:
                if current_chunk_lines:
                    chunks.append("\n".join(current_chunk_lines))
                    current_chunk_lines = []
                    current_chunk_tokens = 0

                sub_chunks = semantic_chunking_with_auto_clusters(
                    line, embed_fn=embed_fn, token_count_fn=token_count_fn, max_chunk_size=max_length
                )
                chunks.extend(sub_chunks)
            # 如果当前行的 Token 数量与当前分块的 Token 数量合并后超过最大 Token 数量，直接作为独立分块放入chunks
            elif current_chunk_tokens + added_tokens > max_length:
                # 把之前的分块内容放入chunks
                chunks.append("\n".join(current_chunk_lines))
                # 重置当前分块为当前行的内容
                current_chunk_lines = [line]
                # 更新当前分块的 Token 数量
                current_chunk_tokens = line_token_count
            # 如果当前行的内容加入当前分块后不会超过最大 Token 数量，直接加入当前分块
            else:
                current_chunk_lines.append(line)
                current_chunk_tokens += added_tokens  # 更新当前分块的 Token 数量
        # 最后的收尾，把最后一行内容放入chunks
        if current_chunk_lines:
            chunks.append("\n".join(current_chunk_lines))

    return chunks
