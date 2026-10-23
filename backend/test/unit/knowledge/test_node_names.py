"""名称边界和后缀的固定预期，不由生产算法生成 oracle。"""

import pytest

from yuxi.modules.knowledge.names import normalize_name, source_segments, suffixed_name
from yuxi.shared.errors import InvalidInputError


@pytest.mark.parametrize("name", ["", " ", ".", "..", "a/b", "a\\b", "a\x00b", "a\nb", "x" * 513])
def test_invalid_leaf_names(name):
    with pytest.raises(InvalidInputError):
        normalize_name(name)


def test_nfc_and_literal_suffix():
    assert normalize_name(" Cafe\u0301 ") == "Café"
    assert suffixed_name("Report.pdf", 1) == "Report (1).pdf"
    assert suffixed_name("Report (1).pdf", 1) == "Report (1) (1).pdf"
    assert suffixed_name(".env", 2) == ".env (2)"
    assert suffixed_name("a" * 508 + ".txt", 1) == "a" * 504 + " (1).txt"


@pytest.mark.parametrize("path", ["/a/b", "C:\\a\\b", "a//b", "a/./b", "a/../b", "a/"])
def test_invalid_manifest_paths(path):
    with pytest.raises(InvalidInputError):
        source_segments(path)
