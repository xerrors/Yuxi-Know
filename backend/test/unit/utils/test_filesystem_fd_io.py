import errno
import os
from pathlib import Path

import pytest

from yuxi.infrastructure import filesystem


def test_open_directory_fd_creates_nested_directories_without_taking_root_fd(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

    previous_umask = os.umask(0o077)
    try:
        directory_fd = filesystem.open_directory_fd(root_fd, ("first", "second"), create=True)
    finally:
        os.umask(previous_umask)
    try:
        assert os.fstat(directory_fd).st_ino == (root / "first" / "second").stat().st_ino
        assert os.fstat(root_fd).st_ino == root.stat().st_ino
        assert (root / "first").stat().st_mode & 0o777 == 0o700
        assert (root / "first" / "second").stat().st_mode & 0o777 == 0o700
    finally:
        os.close(directory_fd)
        os.close(root_fd)


def test_open_directory_fd_distinguishes_symlink_and_non_directory_components(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "target").mkdir()
    (root / "linked").symlink_to(root / "target", target_is_directory=True)
    (root / "file").write_text("not a directory", encoding="utf-8")

    with pytest.raises(OSError) as symlink_error:
        filesystem.open_directory_fd(root, ("linked",))
    assert symlink_error.value.errno == errno.ELOOP

    with pytest.raises(NotADirectoryError) as non_directory_error:
        filesystem.open_directory_fd(root, ("file",))
    assert non_directory_error.value.errno == errno.ENOTDIR


def test_open_directory_fd_closes_internal_fd_after_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[int] = []

    def fail_open(*_args, **_kwargs):
        raise OSError("boom")

    monkeypatch.setattr(filesystem.os, "dup", lambda _fd: 101)
    monkeypatch.setattr(filesystem.os, "open", fail_open)
    monkeypatch.setattr(filesystem.os, "close", closed.append)

    with pytest.raises(OSError, match="boom"):
        filesystem.open_directory_fd(7, ("child",))

    assert closed == [101]


def test_ensure_within_root_returns_root_and_descendant(tmp_path: Path) -> None:
    root = tmp_path / "root"
    child = root / "nested" / "file.txt"

    assert filesystem.ensure_within_root(root, root, error_message="outside") == root
    assert filesystem.ensure_within_root(child, root, error_message="outside") == child


def test_ensure_within_root_rejects_sibling_path(tmp_path: Path) -> None:
    root = tmp_path / "root"
    sibling = tmp_path / "root-other" / "file.txt"

    with pytest.raises(ValueError, match="outside"):
        filesystem.ensure_within_root(sibling, root, error_message="outside")


@pytest.mark.parametrize("content", [b"", b"abc", b"x" * (1024 * 1024 + 7)])
def test_copy_file_fd_preserves_bytes_at_limit_and_borrows_descriptors(tmp_path, content):
    """空文件、边界大小和跨块内容完整复制，借用 fd 保持打开。"""
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.write_bytes(content)
    with source.open("rb") as src, target.open("wb") as dst:
        assert filesystem.copy_file_fd(src.fileno(), dst.fileno(), max_bytes=len(content)) == len(content)
        os.fstat(src.fileno())
        os.fstat(dst.fileno())
    assert target.read_bytes() == content


def test_copy_file_fd_preserves_current_offsets(tmp_path):
    """复制不重新定位或截断调用方已打开的文件。"""
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.write_bytes(b"abcdef")
    target.write_bytes(b"prefix")
    with source.open("rb") as src, target.open("ab") as dst:
        os.lseek(src.fileno(), 2, os.SEEK_SET)
        assert filesystem.copy_file_fd(src.fileno(), dst.fileno(), max_bytes=4) == 4
    assert target.read_bytes() == b"prefixcdef"


@pytest.mark.parametrize("limit", [0, 5])
def test_copy_file_fd_rejects_oversize_without_writing_over_budget(tmp_path, limit):
    """超限保留源文件且绝不把超预算块写入目标。"""
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.write_bytes(b"123456")
    with source.open("rb") as src, target.open("wb") as dst:
        with pytest.raises(filesystem.FileTransferLimitError):
            filesystem.copy_file_fd(src.fileno(), dst.fileno(), max_bytes=limit)
        os.fstat(src.fileno())
        os.fstat(dst.fileno())
    assert source.read_bytes() == b"123456"
    assert len(target.read_bytes()) <= limit


def test_copy_file_fd_rejects_source_growth_after_first_chunk(tmp_path, monkeypatch):
    """复制期间增长的源文件也受实际累计字节限制。"""
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.write_bytes(b"1234")
    original_read = os.read
    grown = False

    def read_and_grow(fd, size):
        """首块读取之后追加真实源文件，恢复 stat-only 的失败面。"""
        nonlocal grown
        chunk = original_read(fd, min(size, 2))
        if not grown:
            with source.open("ab") as stream:
                stream.write(b"56")
            grown = True
        return chunk

    monkeypatch.setattr(filesystem.os, "read", read_and_grow)
    with source.open("rb") as src, target.open("wb") as dst:
        with pytest.raises(filesystem.FileTransferLimitError):
            filesystem.copy_file_fd(src.fileno(), dst.fileno(), max_bytes=4)
    assert source.read_bytes() == b"123456"
    assert target.read_bytes() == b"1234"


def test_copy_file_fd_rejects_negative_budget_before_io(tmp_path):
    """非法上限在消费源字节或写入之前拒绝。"""
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.write_bytes(b"abc")
    target.write_bytes(b"original")
    with source.open("rb") as src, target.open("r+b") as dst:
        with pytest.raises(ValueError, match="non-negative"):
            filesystem.copy_file_fd(src.fileno(), dst.fileno(), max_bytes=-1)
        assert os.lseek(src.fileno(), 0, os.SEEK_CUR) == 0
    assert target.read_bytes() == b"original"


def test_copy_file_fd_handles_partial_writes(tmp_path, monkeypatch):
    """短写注入仍通过真实 fd 保存完整内容。"""
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.write_bytes(b"abcdefgh")
    original_write = os.write

    def short_write(fd, content):
        """每次只写两个字节。"""
        return original_write(fd, content[:2])

    monkeypatch.setattr(filesystem.os, "write", short_write)
    with source.open("rb") as src, target.open("wb") as dst:
        assert filesystem.copy_file_fd(src.fileno(), dst.fileno(), max_bytes=8) == 8
    assert target.read_bytes() == b"abcdefgh"


def test_write_all_fd_rejects_no_progress_without_hanging(tmp_path, monkeypatch):
    """首次零写入必须显式失败，不能靠后续写入掩盖。"""
    original_write = os.write
    stalled = False

    def stalled_write(fd, content):
        """仅第一次返回零，缺失 guard 时测试会直接失败而非挂起。"""
        nonlocal stalled
        if not stalled:
            stalled = True
            return 0
        return original_write(fd, content)

    monkeypatch.setattr(filesystem.os, "write", stalled_write)
    target = tmp_path / "target"
    with target.open("wb") as dst:
        with pytest.raises(OSError) as exc:
            filesystem.write_all_fd(dst.fileno(), b"abc")
        assert exc.value.errno == errno.EIO
        os.fstat(dst.fileno())
    assert target.read_bytes() == b""
