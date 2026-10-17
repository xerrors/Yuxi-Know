"""统一解析发布边界保留原件，只替换无法持久化的 NUL。"""

from pathlib import Path

import pytest

from yuxi.infrastructure.document_parsing import ParseOptions
from yuxi.infrastructure.document_parsing import parser


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", [".txt", ".md"])
async def test_parse_replaces_null_without_changing_other_text_or_original(tmp_path: Path, suffix: str) -> None:
    """真实文本入口保留换行、控制符、Unicode 和原始文件字节。"""
    original = "标题\x00正文\t保留\n\nLatin\x00\x1f😀\n"
    source = tmp_path / f"source{suffix}"
    source.write_bytes(original.encode())

    result = await parser.parse(source, tmp_path / "parsed")

    assert result.markdown_path.read_text() == "标题�正文\t保留\n\nLatin�\x1f😀\n"
    assert source.read_bytes() == original.encode()
    assert result.resources == ()


@pytest.mark.asyncio
async def test_ocr_result_uses_the_same_null_normalization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """OCR 返回的文本经过相同发布边界，原图像仍按原字节保留。"""
    source = tmp_path / "source.png"
    source.write_bytes(b"original-image")
    monkeypatch.setattr(parser, "_parse_ocr", lambda *_args: "开头\x00中间\n结尾")

    result = await parser.parse(source, tmp_path / "parsed", ParseOptions(ocr_engine="rapid_ocr"))

    assert result.markdown_path.read_text() == "开头�中间\n结尾"
    assert source.read_bytes() == b"original-image"
