"""PDF 页树预检的原生资源生命周期回归。"""

from __future__ import annotations

import gc
import threading

import pypdfium2 as pdfium
import pytest
from pypdf import PdfWriter

from yuxi.infrastructure.document_parsing import DocumentParserException
from yuxi.infrastructure.document_parsing import pdf_utils


@pytest.mark.parametrize("invalid_page", [None, 1])
def test_preflight_releases_native_pages_on_owning_thread(tmp_path, monkeypatch, invalid_page):
    """正常页和读取失败页都由预检线程释放，不遗留给其他线程的 GC。"""
    source = tmp_path / "pages.pdf"
    writer = PdfWriter()
    for _ in range(4):
        writer.add_blank_page(width=100, height=100)
    writer.write(source)

    document = pdfium.PdfDocument(source)
    owner_thread = threading.get_ident()
    release_threads = []
    original_close = pdfium.PdfPage._close_impl
    original_get_size = pdfium.PdfPage.get_size

    def close_page(*args, **kwargs):
        """记录真实 PDFium 页释放的执行线程。"""
        release_threads.append(threading.get_ident())
        return original_close(*args, **kwargs)

    def page_size(page):
        """在指定真实页面上恢复基础读取失败。"""
        if page.audit_index == invalid_page:
            raise ValueError("page size unavailable")
        return original_get_size(page)

    class ObservedDocument:
        """在下一次原生加载前触发异线程回收，固定生命周期交错。"""

        def __len__(self):
            """保留真实 PDF 页数。"""
            return len(document)

        def __getitem__(self, index):
            """前一页局部引用已释放后，在加载下一页前完成 GC。"""
            if index >= 2:
                collector = threading.Thread(target=gc.collect)
                collector.start()
                collector.join()
            page = document[index]
            page.audit_index = index
            return page

        def close(self):
            """关闭真实文档，并保留页面到文档的关闭顺序。"""
            document.close()

    monkeypatch.setattr(pdfium.PdfPage, "_close_impl", staticmethod(close_page))
    monkeypatch.setattr(pdfium.PdfPage, "get_size", page_size)
    monkeypatch.setattr(pdf_utils.pdfium, "PdfDocument", lambda _: ObservedDocument())

    if invalid_page is None:
        pdf_utils.validate_pdf_page_tree_loadable(source)
    else:
        with pytest.raises(DocumentParserException, match="第 2 个页槽"):
            pdf_utils.validate_pdf_page_tree_loadable(source)

    assert document.raw is None
    assert release_threads and set(release_threads) == {owner_thread}
