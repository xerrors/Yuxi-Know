from __future__ import annotations

import pytest

import asyncio
import re
import zipfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote, unquote

from yuxi.infrastructure.document_parsing import ParseOptions
import yuxi.infrastructure.document_parsing.parser as parser_unified
from yuxi.infrastructure.document_parsing.artifacts import local_image_links, replace_image_links
from yuxi.modules.documents.service import parse


PARSER_FIXTURES = Path(__file__).parents[2] / "data"


@pytest.mark.asyncio
async def test_docx_directory_preserves_embedded_image_and_position(tmp_path):
    """真实 DOCX 产物保留图片字节及正文顺序。"""
    result = await parse(str(PARSER_FIXTURES / "测试文档.docx"), tmp_path / "parsed")
    markdown = result.markdown_path.read_text()
    assert result.resources == ("images/figure-001.png",)
    assert (result.directory / result.resources[0]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert re.search(r"20XX个人述职报告[\s\S]+!\[image\]\(images/figure-001.png\)[\s\S]+测试图片", markdown)


@pytest.mark.asyncio
async def test_office_resource_failure_rejects_partial_directory(tmp_path, monkeypatch):
    """资源失败不能退回纯文本并报告成功。"""
    source = tmp_path / "source.docx"
    source.write_bytes(b"fixture")
    fake = SimpleNamespace(pictures=[SimpleNamespace(image=None)], export_to_markdown=lambda: "before\n<!-- image -->")
    monkeypatch.setattr(parser_unified, "_convert_office_document", lambda _: fake)
    with pytest.raises(ValueError, match="缺少图像数据"):
        await parse(str(source), tmp_path / "parsed")
    assert not (tmp_path / "parsed").exists()


@pytest.mark.asyncio
async def test_zip_preserves_distinct_paths_and_reference_titles(tmp_path):
    """同名图片保持完整路径，引用式图片与标题也保持可读。"""
    from yuxi.infrastructure.document_parsing.artifacts import extract_markdown_archive

    source = tmp_path / "source.zip"
    markdown_source = '![](a/chart.png "first")\n![second][fig]\n\n[fig]: b/chart.png "second"'
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("nested/full.md", markdown_source)
        archive.writestr("nested/a/chart.png", b"first")
        archive.writestr("nested/b/chart.png", b"second")

    extracted = extract_markdown_archive(str(source), tmp_path / "archive")
    assert isinstance(extracted, str)

    result = await parse(str(source), tmp_path / "parsed")
    markdown = result.markdown_path.read_text()
    assert '![](images/nested/a/chart.png "first")' in markdown
    assert '[fig]: images/nested/b/chart.png "second"' in markdown
    assert (result.directory / "images/nested/a/chart.png").read_bytes() == b"first"
    assert (result.directory / "images/nested/b/chart.png").read_bytes() == b"second"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_path", ["../outside.png", "/absolute.png", "images/../outside.png", "C:\\outside.png"])
async def test_zip_rejects_unsafe_paths_before_writing(tmp_path, bad_path):
    """恢复路径穿越缺陷时，测试必须因拒绝缺失而失败。"""
    source = tmp_path / "source.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("full.md", "# content")
        archive.writestr(bad_path, b"escape")
    with pytest.raises(ValueError, match="不安全的资源路径"):
        await parse(str(source), tmp_path / "parsed")
    assert not (tmp_path / "parsed").exists()
    assert not (tmp_path / "outside.png").exists()


@pytest.mark.asyncio
async def test_missing_image_rejects_successful_text(tmp_path):
    """正文引用不存在的图片时拒绝完整成功。"""
    source = tmp_path / "source.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("full.md", "![](missing.png)")
    with pytest.raises(ValueError, match="缺少 Markdown 资源"):
        await parse(str(source), tmp_path / "parsed")
    assert not (tmp_path / "parsed").exists()


@pytest.mark.asyncio
async def test_cancel_waits_for_converter_before_removing_directory(tmp_path, monkeypatch):
    """取消后没有仍能重新创建资源目录的引擎线程。"""
    import threading
    from yuxi.infrastructure.document_parsing.artifacts import save_resource

    source = tmp_path / "source.png"
    source.write_bytes(b"image")
    started, release = threading.Event(), threading.Event()

    def converter(source, output, options):
        started.set()
        assert release.wait(5)
        save_resource(output, "images/late.png", b"late")
        return "![](images/late.png)"

    monkeypatch.setattr(parser_unified, "_parse_ocr", converter)
    task = asyncio.create_task(parser_unified.parse(source, tmp_path / "parsed", ParseOptions(ocr_engine="rapid_ocr")))
    assert await asyncio.to_thread(started.wait, 5)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not (tmp_path / "parsed").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("markdown_source", "resources", "expected_bytes", "expected_link_count", "expected_fragments", "hosted_link"),
    [
        pytest.param(
            r"![](chart.png)" + "\n![](images/chart.png)\n![](image%20one.png)\n" + r"![](image\(1\).png)",
            {
                "chart.png": b"first",
                "images/chart.png": b"second",
                "image one.png": b"space",
                "image(1).png": b"parentheses",
            },
            [b"first", b"second", b"space", b"parentheses"],
            4,
            [],
            None,
            id="different-paths-and-encoded-destinations",
        ),
        pytest.param(
            "\n".join(f"![]({quote(name, safe='/')})" for name in ["chart#one.png", "chart?one.png", "chart%20one.png", "chart one.png"]),
            {name: name.encode() for name in ["chart#one.png", "chart?one.png", "chart%20one.png", "chart one.png"]},
            [b"chart#one.png", b"chart?one.png", b"chart%20one.png", b"chart one.png"],
            4,
            [],
            (
                "![](chart.png)",
                {"chart.png": "/api/knowledge/knowledge-bases/kb/images/chart%23one.png"},
                "![](/api/knowledge/knowledge-bases/kb/images/chart%23one.png)",
            ),
            id="url-delimiters-preserve-hosted-links",
        ),
        pytest.param(
            r"![chart [section A]](chart.png)" + "\n" + r"![chart \[section A\]](chart.png)",
            {"chart.png": b"image"},
            [b"image"],
            1,
            [("[section A]", 1), ("(images/chart.png)", 2)],
            None,
            id="alt-brackets-do-not-change-resource-identity",
        ),
    ],
)
async def test_zip_image_rewrites_preserve_local_identity(
    tmp_path,
    markdown_source,
    resources,
    expected_bytes,
    expected_link_count,
    expected_fragments,
    hosted_link,
):
    """不同路径与编码的图片引用改写后仍指向原始资源。"""
    source = tmp_path / "source.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("full.md", markdown_source)
        for name, content in resources.items():
            archive.writestr(name, content)

    result = await parse(str(source), tmp_path / "parsed")
    markdown = result.markdown_path.read_text()
    links = local_image_links(markdown)

    assert len(links) == expected_link_count
    assert [(result.directory / unquote(link)).read_bytes() for link in links] == expected_bytes
    for fragment, count in expected_fragments:
        assert markdown.count(fragment) == count
    if hosted_link is not None:
        source_markdown, replacements, expected = hosted_link
        assert replace_image_links(source_markdown, replacements) == expected
