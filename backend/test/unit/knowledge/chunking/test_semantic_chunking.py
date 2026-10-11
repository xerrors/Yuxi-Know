from types import SimpleNamespace

from yuxi.modules.knowledge.chunking.ragflow_like.parsers import semantic
from yuxi.modules.knowledge.chunking.ragflow_like.utils.md_parser_utils import infer_heading_level


def test_heading_inference():
    """测试标题层级推断工具类。"""
    assert infer_heading_level("1. 简介") == 1
    assert infer_heading_level("1.1 详细设计") == 2
    assert infer_heading_level("1.2.3 核心逻辑") == 3
    assert infer_heading_level("一、 背景") == 1
    assert infer_heading_level("普通文本") == 1


def test_empty_heading_preserves_current_title_context():
    markdown_content = """
## Parent Section

### Child Section

Content before empty heading.

###

Content after empty heading.
"""

    chunks = semantic.chunk_markdown(
        markdown_content,
        parser_config={"chunk_token_num": 512},
        embed_fn=lambda texts: texts,
    )

    assert len(chunks) == 1
    assert chunks[0].splitlines()[0] == "### Parent Section|Child Section"
    assert "Content before empty heading." in chunks[0]
    assert "Content after empty heading." in chunks[0]


def test_truncated_heading_token_stream_is_ignored(monkeypatch):
    markdown_parser = semantic.MarkdownIt("commonmark")
    monkeypatch.setattr(markdown_parser, "parse", lambda _: [SimpleNamespace(type="heading_open")])
    monkeypatch.setattr(semantic, "MarkdownIt", lambda _: markdown_parser)

    assert semantic.chunk_markdown("#", embed_fn=lambda texts: texts) == []
