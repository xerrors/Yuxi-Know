from pathlib import Path

import pytest

from yuxi.utils.paths import ensure_within_root


def test_ensure_within_root_returns_root_and_descendant(tmp_path: Path) -> None:
    root = tmp_path / "root"
    child = root / "nested" / "file.txt"

    assert ensure_within_root(root, root, error_message="outside") == root
    assert ensure_within_root(child, root, error_message="outside") == child


def test_ensure_within_root_rejects_sibling_path(tmp_path: Path) -> None:
    root = tmp_path / "root"
    sibling = tmp_path / "root-other" / "file.txt"

    with pytest.raises(ValueError, match="outside"):
        ensure_within_root(sibling, root, error_message="outside")
