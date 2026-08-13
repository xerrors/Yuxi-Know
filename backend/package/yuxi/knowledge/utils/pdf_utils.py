"""PDF 解析前置检查。

本模块在文档进入 MinerU、PyPDFLoader 等解析器之前，
先用 Yuxi 已有的 pypdfium2 依赖检查 PDF 页面树是否能逐页加载。
它只负责识别明显的 PDF 结构异常，例如页树中存在 null 页槽、非 Page 对象或循环引用；
不负责修复 PDF，也不能被当作内容 OCR 或页数统计的业务事实源。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium

from yuxi.knowledge.parser.base import DocumentParserException


@dataclass(slots=True)
class PDFPageLoadIssue:
    """PDF 页面加载异常位置。"""

    page_number: int
    message: str


def _format_page_numbers(page_numbers: list[int], *, limit: int = 8) -> str:
    """格式化页码列表，避免异常信息过长。"""

    visible = page_numbers[:limit]
    result = "、".join(str(page_number) for page_number in visible)
    if len(page_numbers) > limit:
        result = f"{result} 等 {len(page_numbers)} 个"
    return result


def validate_pdf_page_tree_loadable(file_path: str | Path) -> None:
    """校验 PDF 页树中的每一个页槽都能作为页面加载。"""

    path = Path(file_path)

    try:
        doc = pdfium.PdfDocument(str(path))
    except Exception as exc:  # noqa: BLE001
        # pypdfium2 打开加密 PDF 时抛 PdfiumError（消息含 password），无独立加密属性。
        if isinstance(exc, pdfium.PdfiumError) and "password" in str(exc).lower():
            raise DocumentParserException(
                "PDF 文件已加密或需要密码，无法进入文档解析流程",
                "pdf_preflight",
                "encrypted_pdf",
            ) from exc
        raise DocumentParserException(
            f"PDF 文件结构异常，无法打开页面目录: {exc}",
            "pdf_preflight",
            "invalid_pdf_structure",
        ) from exc

    try:
        page_count = len(doc)
        if page_count <= 0:
            raise DocumentParserException(
                "PDF 文件没有可解析页面",
                "pdf_preflight",
                "empty_pdf",
            )

        issues: list[PDFPageLoadIssue] = []
        for page_index in range(page_count):
            try:
                page = doc[page_index]
                # 访问页面尺寸会触发页面对象基础解析，能提前暴露 null/非 Page 页槽。
                _ = page.get_size()
            except Exception as exc:  # noqa: BLE001
                issues.append(PDFPageLoadIssue(page_number=page_index + 1, message=str(exc)))

        if issues:
            bad_pages = _format_page_numbers([issue.page_number for issue in issues])
            first_error = issues[0].message or "页面对象无法加载"
            raise DocumentParserException(
                "PDF 页面结构异常："
                f"声明页数为 {page_count}，但第 {bad_pages} 个页槽不是可加载页面对象。"
                f"底层错误：{first_error}。请先用 Acrobat、打印为 PDF、qpdf 或 mutool 等工具重写 PDF 后再上传。",
                "pdf_preflight",
                "invalid_pdf_page_tree",
            )
    finally:
        doc.close()
