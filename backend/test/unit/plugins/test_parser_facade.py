from __future__ import annotations

import asyncio
from pathlib import Path

import fitz
import pytest
import yuxi.plugins.parser.unified as parser_unified
from docx import Document
from PIL import Image

from yuxi.plugins.parser import Parser
from yuxi.plugins.parser.factory import DocumentProcessorFactory

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _build_pdf(file_path: Path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(file_path))
    doc.close()


def _build_docx(file_path: Path, text: str) -> None:
    document = Document()
    document.add_paragraph(text)
    document.save(str(file_path))


def _build_png(file_path: Path) -> None:
    image = Image.new("RGB", (120, 80), "white")
    image.save(str(file_path))


def test_parser_parse_pdf_file_returns_markdown_text(tmp_path: Path):
    file_path = tmp_path / "parser_test.pdf"
    _build_pdf(file_path, "Parser PDF content")

    markdown = Parser.parse(str(file_path))

    assert isinstance(markdown, str)
    assert "Parser" in markdown
    assert "content" in markdown
    assert len(markdown.strip()) > 0


def test_parser_parse_docx_file_returns_markdown_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    file_path = tmp_path / "parser_test.docx"
    _build_docx(file_path, "Parser DOCX content")

    # 避免测试依赖 docling 行为，直接验证统一 parser 可回退到 python-docx。
    def _raise_docling_error(*args, **kwargs):
        raise RuntimeError("force fallback to python-docx")

    monkeypatch.setattr(parser_unified, "_convert_with_docling", _raise_docling_error)

    markdown = Parser.parse(str(file_path))

    assert isinstance(markdown, str)
    assert "Parser DOCX content" in markdown
    assert len(markdown.strip()) > 0


def test_parser_parse_png_file_returns_markdown_text_with_mocked_ocr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    file_path = tmp_path / "parser_test.png"
    _build_png(file_path)

    async def _fake_parse_image_async(file, params=None):
        return "Parser PNG content"

    monkeypatch.setattr(parser_unified, "parse_image_async", _fake_parse_image_async)

    markdown = Parser.parse(str(file_path), params={"enable_ocr": "rapid_ocr"})

    assert isinstance(markdown, str)
    assert "Parser PNG content" in markdown
    assert len(markdown.strip()) > 0


@pytest.mark.asyncio
async def test_parser_aparse_pdf_file_returns_markdown_text(tmp_path: Path):
    file_path = tmp_path / "parser_test_async.pdf"
    _build_pdf(file_path, "Async Parser PDF content")

    markdown = await Parser.aparse(str(file_path))

    assert isinstance(markdown, str)
    assert "Async" in markdown
    assert "content" in markdown
    assert len(markdown.strip()) > 0


@pytest.mark.asyncio
async def test_parser_aparse_image_file_with_mineru_when_available():
    file_path = DATA_DIR / "测试图片.png"
    assert file_path.exists(), f"测试文件不存在: {file_path}"

    health = await asyncio.to_thread(DocumentProcessorFactory.check_health, "mineru_ocr")
    if health.get("status") != "healthy":
        pytest.skip(f"mineru_ocr 不可用: {health.get('message', 'unknown')}")

    markdown = await Parser.aparse(
        str(file_path),
        params={"enable_ocr": "mineru_ocr", "backend": "pipeline"},
    )

    assert isinstance(markdown, str)
    assert len(markdown) > 100
    assert len(markdown.strip()) > 0
