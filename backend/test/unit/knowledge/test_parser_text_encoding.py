"""知识库文本解析的编码兼容测试。"""

from __future__ import annotations

import codecs
import zipfile
from pathlib import Path

import pytest

import yuxi.knowledge.parser.unified as parser_unified
from yuxi.knowledge.parser.text_encoding import decode_user_text
from yuxi.knowledge.parser.zip_utils import process_zip_file

SIMPLIFIED = (
    "第一章 总则\n"
    "第一条 为了规范知识库文档解析流程，保障用户上传文件的可读性，制定本规定。\n"
    "第二条 本规定适用于文本、表格、演示文稿与扫描影像等文档类型。\n"
    "第三条 用户上传的文档必须经过解析、分块与向量化后才能被检索使用。\n"
    "第四条 解析失败的文件应当给出明确错误信息并支持重新解析。\n"
)
TRADITIONAL = (
    "第一章 總則\n"
    "第一條 為規範知識庫文件解析流程，保障使用者上傳文件的可讀性，訂定本規定。\n"
    "第二條 本規定適用於文字、表格與掃描影像等文件類型，解析後可供檢索使用。\n"
)
ACCENTED = "Reunion cafe naive: deuxieme section du document de test avec les accents é è à û ï ô."


def test_decode_user_text_keeps_utf8_unchanged() -> None:
    assert decode_user_text(SIMPLIFIED.encode("utf-8"), "doc.txt") == SIMPLIFIED


@pytest.mark.parametrize(
    ("codec", "sample"),
    [
        ("gbk", SIMPLIFIED),
        ("gb18030", SIMPLIFIED),
        ("big5", TRADITIONAL),
        ("utf-16", SIMPLIFIED),
        ("latin-1", ACCENTED),
        ("cp1252", ACCENTED),
    ],
)
def test_decode_user_text_detects_legacy_codecs(codec: str, sample: str) -> None:
    """负控：这些字节在硬编码 UTF-8 读取下会抛 UnicodeDecodeError。"""
    raw = sample.encode(codec)

    with pytest.raises(UnicodeDecodeError):
        raw.decode("utf-8")

    assert decode_user_text(raw, f"doc.{codec}") == sample


def test_decode_user_text_strips_utf8_bom() -> None:
    raw = SIMPLIFIED.encode("utf-8-sig")

    decoded = decode_user_text(raw, "bom.txt")

    assert decoded == SIMPLIFIED
    assert raw.decode("utf-8").startswith("\ufeff")


def test_decode_user_text_keeps_gb18030_only_characters() -> None:
    sample = SIMPLIFIED + "生僻字表：囧龘靐彧燚\n"

    decoded = decode_user_text(sample.encode("gb18030"), "rare.txt")

    assert "囧龘靐彧燚" in decoded


def test_decode_user_text_keeps_readable_fragments_of_binary_upload() -> None:
    """二进制残片不能终止解析；识别不到文本编码时仍返回可读内容。"""
    raw = b"\x80\x81\xfe\xff\x80\x81 garbage \xc5\xc5\xc5\xc5" * 4

    decoded = decode_user_text(raw, "broken.txt")

    assert "garbage" in decoded


def test_decode_user_text_replaces_truncated_utf16_tail() -> None:
    raw = codecs.BOM_UTF16_LE + b"A\x00B\x00C"

    decoded = decode_user_text(raw, "truncated.txt")

    assert decoded.startswith("AB")
    assert "\ufffd" in decoded


def test_decode_user_text_routes_nul_bytes_to_detector() -> None:
    """无 BOM 的 UTF-16LE 不得走 UTF-8 快路径静默产出夹杂 NUL 的垃圾（负向：去掉 NUL 嗅探时结果含 \x00）。"""
    raw = "装备清单 alpha 段".encode("utf-16-le")

    decoded = decode_user_text(raw, "utf16le-no-bom.txt")

    assert "\x00" not in decoded
    assert decoded == "装备清单 alpha 段"


def test_decode_user_text_accepts_empty_upload() -> None:
    assert decode_user_text(b"", "empty.txt") == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("suffix", "codec", "sample"),
    [
        (".txt", "gbk", SIMPLIFIED),
        (".md", "gbk", SIMPLIFIED),
        (".txt", "big5", TRADITIONAL),
        (".html", "gbk", "<h1>知识库解析</h1><p>" + SIMPLIFIED + "</p>"),
        (".json", "gbk", '{"名称": "知识库", "条目": 3}'),
        (".csv", "gbk", "姓名,部门\n张三,研发\n"),
    ],
)
async def test_parse_resolved_document_accepts_non_utf8_upload(
    suffix: str,
    codec: str,
    sample: str,
    tmp_path: Path,
) -> None:
    file_path = tmp_path / f"upload{suffix}"
    file_path.write_bytes(sample.encode(codec))

    markdown = await parser_unified.parse_resolved_document(str(file_path))

    assert markdown
    if suffix == ".html":
        assert "# 知识库解析" in markdown
    elif suffix == ".json":
        assert '"名称": "知识库"' in markdown
    elif suffix == ".csv":
        assert "张三" in markdown
    else:
        assert sample[:12] in markdown


async def test_process_zip_file_accepts_non_utf8_markdown(tmp_path: Path) -> None:
    archive = tmp_path / "docs.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr("full.md", "# 知识库\n" + SIMPLIFIED)

    markdown = await process_zip_file(str(archive))

    assert "# 知识库" in markdown
    assert SIMPLIFIED[:12] in markdown
