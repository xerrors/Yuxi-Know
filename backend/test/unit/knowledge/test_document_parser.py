from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import yuxi.infrastructure.document_parsing.engines as engines
import yuxi.infrastructure.document_parsing.parser as parser_unified
from yuxi.infrastructure.document_parsing import ParseOptions
from yuxi.modules.documents.service import parse

PARSER_FIXTURES = Path(__file__).parents[2] / "data"


def _build_pdf(file_path: Path, text: str | list[str]) -> None:
    """用标准库构造带文本的最小 PDF，避免测试引入额外 PDF 依赖。"""
    pages = [text] if isinstance(text, str) else text
    kids = " ".join(f"{4 + index * 2} 0 R" for index in range(len(pages)))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    for index, page_text in enumerate(pages):
        escaped = page_text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1")
        objects.extend(
            [
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                    f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + index * 2} 0 R >>"
                ).encode(),
                b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
            ]
        )
    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_number, object_body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_number} 0 obj\n".encode())
        pdf.extend(object_body)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode())
    pdf.extend(f"startxref\n{xref_offset}\n%%EOF\n".encode())
    file_path.write_bytes(pdf)


async def _parse_markdown(source, params=None, db=None):
    """回读真实解析入口，保留文本格式测试的独立断言。"""
    with tempfile.TemporaryDirectory() as temporary:
        result = await parse(str(source), Path(temporary) / "parsed", params, db)
        return result.markdown_path.read_text()


def test_pdfreader_preserves_page_order_blank_pages_and_trimming(tmp_path: Path):
    """文本提取保留空页分隔并去除逐页首尾空白。"""
    from yuxi.infrastructure.document_parsing.parser import _parse_ocr

    file_path = tmp_path / "pages.pdf"
    _build_pdf(file_path, ["  First page  ", "", "Last page"])
    assert _parse_ocr(file_path, tmp_path, ParseOptions()) == "First page\n\n\n\nLast page"


def test_pdfreader_rejects_corrupt_pdf(tmp_path: Path):
    """损坏 PDF 显式失败，不返回伪成功空文本。"""
    from pypdf.errors import PdfReadError
    from yuxi.infrastructure.document_parsing.parser import _parse_ocr

    file_path = tmp_path / "broken.pdf"
    file_path.write_bytes(b"%PDF-1.4\ninvalid")
    with pytest.raises(PdfReadError):
        _parse_ocr(file_path, tmp_path, ParseOptions())


@pytest.mark.asyncio
async def test_parse_document_pdf_returns_markdown_text(tmp_path: Path):
    file_path = tmp_path / "parser_test.pdf"
    _build_pdf(file_path, "Parser PDF content")

    markdown = await _parse_markdown(str(file_path), params={"ocr_engine": "disable"})

    assert "Parser" in markdown
    assert "content" in markdown


@pytest.mark.parametrize(
    ("filename", "expected_fragments"),
    [
        ("测试文档.docx", ("20XX个人述职报告", "测试表格")),
        ("测试演示.pptx", ("BUSINESS REPORT TEMPLATE", "工作内容回顾")),
        ("测试表格.xlsx", ("个人所得税计算",)),
    ],
)
def test_slim_office_backends_convert_real_fixtures(
    filename: str,
    expected_fragments: tuple[str, ...],
) -> None:
    document = parser_unified._convert_office_document(PARSER_FIXTURES / filename)

    markdown = document.export_to_markdown()

    assert markdown.strip()
    assert all(fragment in markdown for fragment in expected_fragments)


def test_xls_parsed_with_pandas_without_libreoffice() -> None:
    """旧版 .xls 不走 Docling，直接用 pandas + xlrd 解析为 Markdown。"""
    markdown = parser_unified._convert_xls_to_markdown(PARSER_FIXTURES / "测试旧表格.xls")

    assert markdown.strip()
    assert "Docling Slim" in markdown
    assert "53" in markdown


async def test_parse_resolved_document_routes_xls_to_pandas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """parse_resolved_document 对 .xls 使用 pandas 路径而非 Docling。"""
    docling_calls: list[Path] = []

    def _fake_docling(file_path: Path, params: dict | None = None) -> str:
        docling_calls.append(file_path)
        return "docling"

    monkeypatch.setattr(parser_unified, "_convert_with_docling", _fake_docling)

    markdown = await _parse_markdown(str(PARSER_FIXTURES / "测试旧表格.xls"))

    assert "Docling Slim" in markdown
    assert not docling_calls


async def test_xls_preserves_single_row_text_and_blank_cells() -> None:
    """真实多 sheet 文件保留单行内容、文本编号与空白，跳过空表。"""
    markdown = await _parse_markdown(str(PARSER_FIXTURES / "xls-cell-preservation.xls"))

    assert "## 单行" in markdown
    assert "## 文本与空白" in markdown
    assert "## 空表" not in markdown
    rows = [[cell.strip() for cell in line.strip("|").split("|")] for line in markdown.splitlines() if line.startswith("|")]
    assert ["唯一内容", "53"] in rows
    assert ["编号", "标记", "备注"] in rows
    assert ["00123", "NA", ""] in rows
    assert ["00456", "NULL", "保留文本"] in rows


def test_slim_office_backend_unloads_after_conversion_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unloaded = False

    class FailingBackend:
        def convert(self):
            raise RuntimeError("conversion failed")

        def unload(self):
            nonlocal unloaded
            unloaded = True

    input_document = SimpleNamespace(valid=True, _backend=FailingBackend())
    monkeypatch.setattr(parser_unified, "InputDocument", lambda *_args: input_document)

    with pytest.raises(RuntimeError, match="conversion failed"):
        parser_unified._convert_office_document(tmp_path / "failure.docx")

    assert unloaded


@pytest.mark.asyncio
async def test_pdf_never_enters_office_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file_path = tmp_path / "parser_test.pdf"
    _build_pdf(file_path, "Existing PDF path")
    monkeypatch.setattr(
        parser_unified,
        "_convert_office_document",
        lambda *_args, **_kwargs: pytest.fail("PDF 不得进入 Office backend"),
    )

    markdown = await _parse_markdown(str(file_path), params={"ocr_engine": "disable"})

    assert "Existing PDF path" in markdown


def test_convert_csv_to_markdown_preserves_column_dtypes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_path = tmp_path / "parser_test.csv"
    file_path.write_text("id,score\n9007199254740993,2.5\n", encoding="utf-8")
    captured_dtypes: list[dict[str, object]] = []
    original_to_markdown = pd.DataFrame.to_markdown

    def _capture_dtypes(dataframe: pd.DataFrame, *args, **kwargs) -> str:
        captured_dtypes.append(dataframe.dtypes.to_dict())
        return original_to_markdown(dataframe, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "to_markdown", _capture_dtypes)

    markdown = parser_unified._convert_csv_to_markdown(file_path)

    assert markdown
    assert str(captured_dtypes[0]["id"]) == "int64"


@pytest.mark.asyncio
async def test_parse_document_docx_does_not_block_event_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_path = tmp_path / "parser_test_async.docx"
    file_path.write_bytes(b"fake docx")
    completion_order: list[str] = []

    def _slow_docling_conversion(*args, **kwargs) -> str:
        time.sleep(0.1)
        return "Async DOCX content"

    async def __parse_markdown() -> None:
        await _parse_markdown(str(file_path))
        completion_order.append("parse")

    async def _record_event_loop_progress() -> None:
        await asyncio.sleep(0.01)
        completion_order.append("event_loop")

    monkeypatch.setattr(parser_unified, "_convert_with_docling", _slow_docling_conversion)

    await asyncio.gather(__parse_markdown(), _record_event_loop_progress())

    assert completion_order == ["event_loop", "parse"]


@pytest.mark.asyncio
async def test_default_engine_resolves_system_ocr_config_before_conversion(tmp_path, monkeypatch):
    """应用层解析默认引擎，底层只接收有效值。"""
    source = tmp_path / "source.pdf"
    _build_pdf(source, "text")

    async def config(*args):
        return {"default_ocr_engine": "mineru_ocr"}

    async def kwargs(*args):
        return {"server_url": "http://configured.test"}

    captured = {}

    def get_engine(engine_id, **kwargs):
        captured.update(engine=engine_id, kwargs=kwargs)
        return SimpleNamespace(process_file=lambda *args: "configured OCR text")

    monkeypatch.setattr("yuxi.modules.system.services.options.Option.get", config)
    monkeypatch.setattr("yuxi.modules.documents.service._build_processor_kwargs", kwargs)
    monkeypatch.setattr(engines, "get_engine", get_engine)
    result = await parse(str(source), tmp_path / "parsed", db=object())
    assert result.markdown_path.read_text() == "configured OCR text"
    assert captured == {"engine": "mineru_ocr", "kwargs": {"server_url": "http://configured.test"}}
