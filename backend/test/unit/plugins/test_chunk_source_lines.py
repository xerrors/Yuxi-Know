"""Chunk 起止行号使用完整原文，而非分片内相对行号。"""

import pytest

from yuxi.modules.knowledge.chunking.dispatcher import _build_chunk_records, chunk_markdown
from yuxi.modules.knowledge.chunking.ragflow_like.parsers import semantic
from yuxi.modules.knowledge.chunking.source_spans import LocatedText, SourceText


def test_blank_lines_and_repeated_chunks_keep_distinct_source_locations():
    """保留空行计数，并按原文顺序区分重复内容。"""
    records = chunk_markdown("相同内容\r\n\r\n相同内容", "file", "text.txt", {"chunk_preset_id": "separator"})
    assert [(row["chunk_index"], row["start_line"], row["end_line"]) for row in records] == [(0, 1, 1), (1, 3, 3)]


def test_overlap_can_start_before_previous_chunk_end():
    """从前一块终点搜索会丢失的重叠，仍定位到原文行。"""
    source = SourceText("甲\n乙\n丙")
    records = _build_chunk_records([source[:3], source[2:]], "file", source)
    assert [(row["start_line"], row["end_line"]) for row in records] == [(1, 2), (2, 3)]


def test_normalized_whitespace_does_not_shift_original_line_numbers():
    """合并时去掉的空行与缩进仍占原文行号。"""
    records = chunk_markdown("  第一行\n\n    第二行\n", "file", "text.md", {"chunk_preset_id": "general"})
    assert (records[0]["start_line"], records[0]["end_line"]) == (1, 3)


def test_plain_text_ingestion_has_source_lines():
    """TXT 经相同文本入口保存原文首尾行。"""
    records = chunk_markdown("第一段\n\n第二段", "file", "text.txt", {"chunk_preset_id": "separator"})
    assert [(row["start_line"], row["end_line"]) for row in records] == [(1, 1), (3, 3)]


def test_rewritten_semantic_block_uses_token_source_map():
    """重写的 HTML 表格正文使用 parser 来源，避免对子串作猜测。"""
    records = _build_chunk_records(
        [LocatedText("# Table KV\n- 名称: 测试", (2, 5))],
        "file",
        "# 标题\n\n<table>\n<tr><td>测试</td></tr>\n</table>",
    )
    assert (records[0]["start_line"], records[0]["end_line"]) == (3, 5)


@pytest.mark.parametrize("content", ["不存在的内容", "实际内容"])
def test_chunk_without_source_mapping_is_rejected(content):
    """缺少切分来源时，即使字符串恰好匹配也不能猜测位置。"""
    with pytest.raises(ValueError, match="无法.*定位"):
        _build_chunk_records([content], "file", "实际内容")


def test_repeated_multiline_chunks_keep_parser_boundaries():
    """重复多行块不能被反查误认为前一块的重叠。"""
    records = chunk_markdown(
        "甲\n甲\n甲\n甲\n甲\n甲",
        "file",
        "text.md",
        {
            "chunk_preset_id": "general",
            "chunk_parser_config": {"chunk_token_num": 2},
        },
    )
    assert [(row["start_line"], row["end_line"]) for row in records] == [(1, 3), (4, 6)]


def test_separator_overlap_keeps_repeated_source_locations():
    """配置重叠时，由实际切片范围定位重复文本。"""
    records = chunk_markdown(
        "甲\n甲\n甲\n甲",
        "file",
        "text.txt",
        {
            "chunk_preset_id": "separator",
            "chunk_parser_config": {"delimiter": "###", "chunk_token_num": 2, "overlapped_percent": 50},
        },
    )
    assert [(row["start_line"], row["end_line"]) for row in records] == [(1, 2), (2, 3), (3, 4)]


def test_symbol_lines_keep_source_boundaries_after_blank_line_removal():
    """纯符号首尾行仍属于片段，不能仅定位到字母数字正文。"""
    records = chunk_markdown("```\n\nhello\n\n```", "file", "code.md", {"chunk_preset_id": "general"})
    assert (records[0]["start_line"], records[0]["end_line"]) == (1, 5)


def test_long_semantic_code_keeps_fences_without_source_failure():
    """长代码块切分后，围栏子块仍保存有效来源。"""
    source = "```python\nprint(1)\nprint(2)\nprint(3)\n```"
    chunks = semantic.chunk_markdown(source, {"chunk_token_num": 2}, embed_fn=lambda _: [])
    records = _build_chunk_records(chunks, "file", source)
    assert records[0]["start_line"] == 1
    assert records[-1]["end_line"] == 5
    assert all(row["start_line"] > 0 and row["end_line"] >= row["start_line"] for row in records)


def test_qa_repeated_answer_uses_its_own_source_lines():
    """重复问题和答案保留当前问答来源，而非回到首次出现位置。"""
    source = "Q: 同一问题\nA: 同一答案\n\nQ: 第二问题\nA: 同一答案"
    records = chunk_markdown(source, "file", "qa.md", {"chunk_preset_id": "qa"})
    assert [(row["start_line"], row["end_line"]) for row in records] == [(1, 2), (4, 5)]


def test_csv_escaped_quotes_keep_complete_record_range():
    """CSV 结构引号不能冒充跨行字段的正文来源。"""
    source = '"Q","""\n"""'
    records = chunk_markdown(source, "file", "qa.csv", {"chunk_preset_id": "qa"})
    assert (records[0]["start_line"], records[0]["end_line"]) == (1, 2)


def test_long_csv_answer_keeps_record_range_after_subdivision():
    """CSV 解码后的长问答子块仍定位到完整原始 record。"""
    source = '"问题","' + "长答案" * 2000 + '"'
    records = chunk_markdown(source, "file", "qa.csv", {"chunk_preset_id": "qa"})
    assert len(records) > 1
    assert all((row["start_line"], row["end_line"]) == (1, 1) for row in records)


@pytest.mark.parametrize("closing", ["````", "    ```", ""])
def test_semantic_fence_uses_parser_closing_boundary(closing):
    """更长或缩进的围栏由 Markdown parser 认定，未闭合时不保存虚构行。"""
    source = "```python\nprint(1)\nprint(2)\n" + closing
    chunks = semantic.chunk_markdown(source, {"chunk_token_num": 2}, embed_fn=lambda _: [])
    records = _build_chunk_records(chunks, "file", source)
    assert records[0]["start_line"] == 1
    assert records[-1]["end_line"] == (4 if closing else 3)
