"""真实 PDFium 调用的并发隔离与 OCR 资源生命周期。"""

from __future__ import annotations

import io
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import pypdfium2 as pdfium
import pytest
from PIL import Image
from pypdf import PdfWriter

from yuxi.infrastructure.document_parsing import OCRException, pdf_utils
from yuxi.infrastructure.document_parsing.engines.deepseek_ocr import DeepSeekOCRParser
from yuxi.infrastructure.document_parsing.engines.rapid_ocr import RapidOCRParser


@pytest.fixture
def pdf_source(tmp_path):
    """生成实际可渲染的三页 PDF，不依赖外部文献。"""
    source = tmp_path / "pages.pdf"
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=72, height=72)
    writer.write(source)
    return source


@pytest.mark.parametrize("engine", ["rapid", "deepseek"])
@pytest.mark.parametrize("failure", [None, "page_count", "render", "ocr"])
def test_ocr_releases_native_resources_before_consuming_copied_image(pdf_source, monkeypatch, engine, failure):
    """原生资源先关闭，锁外 OCR 仍可读完整图像；任一步骤失败也回收文档。"""
    document_type = pdfium.PdfDocument
    document = document_type(pdf_source)
    pages, bitmaps = [], []
    original_page = document_type.get_page
    original_count = document_type.__len__
    original_render = pdfium.PdfPage.render
    original_bitmap_close = pdfium.PdfBitmap.close

    def page_count(current):
        """恢复文档打开后读取页数失败的路径。"""
        if failure == "page_count":
            raise RuntimeError("page_count failed")
        return original_count(current)

    def get_page(current, index):
        """保留原生页引用以独立核对关闭结果。"""
        page = original_page(current, index)
        pages.append(page)
        return page

    def render(page, *args, **kwargs):
        """保留原生 bitmap 引用，并覆盖渲染失败。"""
        if failure == "render":
            raise RuntimeError("render failed")
        if engine == "deepseek":
            kwargs["force_bitmap_format"] = pdfium.raw.FPDFBitmap_BGRA
        bitmap = original_render(page, *args, **kwargs, rev_byteorder=True, prefer_bgrx=True)
        with bitmap.to_pil() as shared_image:
            assert shared_image.mode == ("RGBA" if engine == "deepseek" else "RGBX")
            bitmap.fill_rect((0, 0, 0, 255), 0, 0, bitmap.width, bitmap.height)
            assert shared_image.getpixel((0, 0))[:3] == (0, 0, 0)
            bitmap.fill_rect((255, 255, 255, 255), 0, 0, bitmap.width, bitmap.height)
            assert shared_image.getpixel((0, 0))[:3] == (255, 255, 255)
        bitmaps.append(bitmap)
        return bitmap

    def consume_image(image):
        """从已释放的 PDFium 资源外读取独立图像，并核对耗时工作未持锁。"""
        assert all(page.raw is None for page in pages)
        assert all(bitmap.raw is None for bitmap in bitmaps)
        assert pdf_utils.PDFIUM_LOCK.acquire(blocking=False)
        pdf_utils.PDFIUM_LOCK.release()
        with image.convert("RGB") as rgb:
            assert rgb.getpixel((0, 0)) == (255, 255, 255)
        if failure == "ocr":
            raise RuntimeError("ocr failed")
        return "page text"

    def close_bitmap(bitmap, *args, **kwargs):
        """释放前覆写原生缓冲区，未复制的图像不能继续呈现原像素。"""
        if bitmap.raw is not None:
            bitmap.fill_rect((0, 0, 0, 255), 0, 0, bitmap.width, bitmap.height)
        return original_bitmap_close(bitmap, *args, **kwargs)

    def call_api(data, mime_type, params):
        """以真正 PNG 字节回读代替外部网络调用。"""
        assert mime_type == "image/png"
        with Image.open(io.BytesIO(data)) as image:
            return consume_image(image)

    monkeypatch.setattr(document_type, "__len__", page_count)
    monkeypatch.setattr(document_type, "get_page", get_page)
    monkeypatch.setattr(pdfium.PdfPage, "render", render)
    monkeypatch.setattr(pdfium.PdfBitmap, "close", close_bitmap)
    monkeypatch.setattr(pdfium, "PdfDocument", lambda _: document)
    if engine == "rapid":
        parser = RapidOCRParser()
        monkeypatch.setattr(parser, "process_image", consume_image)
        operation = partial(parser.process_pdf, str(pdf_source))
    else:
        parser = DeepSeekOCRParser(api_key="test-key")
        monkeypatch.setattr(parser, "_call_api", call_api)
        operation = partial(parser._process_pdf, str(pdf_source), {})

    if failure:
        expected_error = OCRException if engine == "rapid" else RuntimeError
        with pytest.raises(expected_error, match=f"{failure} failed"):
            operation()
    else:
        assert operation() == "page text\n\npage text\n\npage text"
    assert document.raw is None
    assert all(page.raw is None for page in pages)
    assert all(bitmap.raw is None for bitmap in bitmaps)


@pytest.mark.parametrize(
    "operations",
    [("preflight", "preflight"), ("preflight", "rapid"), ("preflight", "deepseek"), ("rapid", "deepseek")],
)
def test_pdfium_native_calls_never_overlap_between_consumers(pdf_source, monkeypatch, operations):
    """独立原生入口拒绝线程重入，三种调用方必须在同一序列化边界完成。"""
    native_owner = threading.RLock()
    start = threading.Barrier(2)
    overlap = []
    document_type = pdfium.PdfDocument

    def guard(operation):
        """在进入真实 native 调用前独立检查并发，不依赖应用锁的实现。"""

        def guarded(*args, **kwargs):
            """保留真实结果；检测到重入时拒绝进入不安全 native 代码。"""
            if not native_owner.acquire(blocking=False):
                overlap.append(threading.get_ident())
                raise RuntimeError("native PDFium calls overlap")
            try:
                time.sleep(0.001)
                return operation(*args, **kwargs)
            finally:
                native_owner.release()

        return guarded

    for native_type, methods in (
        (document_type, ("__len__", "get_page", "close")),
        (pdfium.PdfPage, ("get_size", "render", "close")),
        (pdfium.PdfBitmap, ("to_pil", "close")),
    ):
        for method in methods:
            monkeypatch.setattr(native_type, method, guard(getattr(native_type, method)))
    monkeypatch.setattr(pdfium, "PdfDocument", guard(document_type))
    rapid = RapidOCRParser()
    deepseek = DeepSeekOCRParser(api_key="test-key")
    monkeypatch.setattr(rapid, "process_image", lambda _: "page text")
    monkeypatch.setattr(deepseek, "_call_api", lambda *_: "page text")

    def run(kind):
        """同时启动不同入口，让底层原生 oracle 观察实际交错。"""
        start.wait()
        if kind == "preflight":
            return pdf_utils.validate_pdf_page_tree_loadable(pdf_source)
        if kind == "rapid":
            return rapid.process_pdf(str(pdf_source))
        return deepseek._process_pdf(str(pdf_source), {})

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, operations))
    assert not overlap
    assert results == [None if kind == "preflight" else "page text\n\npage text\n\npage text" for kind in operations]
