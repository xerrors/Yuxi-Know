from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path

import pytest

from yuxi.modules.workspace import filesystem as workspace_filesystem_module
from yuxi.modules.workspace.filesystem import Workspace
from yuxi.modules.workspace.errors import FileTransferLimitError


@pytest.mark.parametrize("failure", ["oversize", "read_error"])
def test_upload_stream_failure_preserves_target_and_removes_staging(tmp_path, monkeypatch, failure):
    """累计超限或中途读取失败都不发布半成品，也不关闭借用的输入。"""
    monkeypatch.setattr(workspace_filesystem_module, "user_workspace_dir", lambda _uid: tmp_path)
    target = tmp_path / "file.txt"
    target.write_bytes(b"original")

    class ChunkedSource(BytesIO):
        """限制每次读取长度，并按需注入中途失败。"""

        def read(self, size=-1):
            """真实消费者必须分块读取；失败发生在写过首块之后。"""
            assert 0 < size <= 1024 * 1024
            if failure == "read_error" and self.tell() >= 3:
                raise OSError("source failed")
            return super().read(min(size, 3))

    source = ChunkedSource(b"123456")
    expected = FileTransferLimitError if failure == "oversize" else OSError
    with pytest.raises(expected):
        Workspace("user-1").upload_authorized_file_from_stream("/file.txt", source, max_bytes=5)
    assert target.read_bytes() == b"original"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["file.txt"]
    assert not source.closed


@pytest.mark.parametrize("existing_kind", ["file", "symlink"])
def test_upload_stream_no_clobber_and_limit(tmp_path, monkeypatch, existing_kind):
    """流入口也在最终发布处拒绝覆盖文件及 symlink。"""
    monkeypatch.setattr(workspace_filesystem_module, "user_workspace_dir", lambda _uid: tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"original")
    target = tmp_path / "file.txt"
    if existing_kind == "symlink":
        target.symlink_to(outside)
    else:
        target.write_bytes(b"original")
    with pytest.raises(FileExistsError):
        Workspace("user-1").upload_authorized_file_from_stream("/file.txt", BytesIO(b"12345"), max_bytes=5, overwrite=False)
    assert target.read_bytes() == b"original"
    assert outside.read_bytes() == b"original"
    assert not list(tmp_path.glob(".yuxi-write-*"))

    result = Workspace("user-1").upload_authorized_file_from_stream("/new.txt", BytesIO(b"12345"), max_bytes=5, overwrite=False)
    assert result["size"] == 5
    assert (tmp_path / "new.txt").read_bytes() == b"12345"
    assert (tmp_path / "new.txt").stat().st_mode & 0o777 == 0o600


def test_upload_stream_rejects_symlink_parent(tmp_path, monkeypatch):
    """直接调用流写入也无法沿目录链接越过 workspace 边界。"""
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(workspace_filesystem_module, "user_workspace_dir", lambda _uid: root)
    with pytest.raises(PermissionError):
        Workspace("user-1").upload_authorized_file_from_stream("/linked/file.txt", BytesIO(b"content"), max_bytes=10)
    assert list(outside.iterdir()) == []


def test_upload_authorized_file_uses_owner_only_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    source = tmp_path / "source.txt"
    source.write_text("content", encoding="utf-8")
    monkeypatch.setattr(workspace_filesystem_module, "user_workspace_dir", lambda _uid: workspace_root)

    previous_umask = os.umask(0o077)
    try:
        Workspace("user-1").upload_authorized_file_from_path(
            "/projects/11111111-1111-4111-8111-111111111111/file.txt",
            str(source),
        )
    finally:
        os.umask(previous_umask)

    target = workspace_root / "projects" / "11111111-1111-4111-8111-111111111111" / "file.txt"
    assert target.read_text(encoding="utf-8") == "content"
    assert target.stat().st_mode & 0o777 == 0o600
    assert target.parent.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("existing_kind", ["file", "symlink"])
def test_upload_without_overwrite_atomically_preserves_existing_entry(
    tmp_path: Path,
    monkeypatch,
    existing_kind: str,
) -> None:
    workspace_root = tmp_path / "workspace"
    project_root = workspace_root / "projects" / "11111111-1111-4111-8111-111111111111"
    project_root.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    target = project_root / "occupied.txt"
    if existing_kind == "file":
        target.write_text("original", encoding="utf-8")
    else:
        target.symlink_to(outside)
    source = tmp_path / "source.txt"
    source.write_text("replacement", encoding="utf-8")
    monkeypatch.setattr(workspace_filesystem_module, "user_workspace_dir", lambda _uid: workspace_root)

    with pytest.raises(FileExistsError):
        Workspace("user-1").upload_authorized_file_from_path(
            "/projects/11111111-1111-4111-8111-111111111111/occupied.txt",
            str(source),
            overwrite=False,
        )

    if existing_kind == "file":
        assert target.read_text(encoding="utf-8") == "original"
    else:
        assert target.is_symlink()
    assert outside.read_text(encoding="utf-8") == "outside"


def test_upload_without_parent_creation_rejects_missing_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    source = tmp_path / "source.txt"
    source.write_text("content", encoding="utf-8")
    monkeypatch.setattr(workspace_filesystem_module, "user_workspace_dir", lambda _uid: workspace_root)

    with pytest.raises(FileNotFoundError):
        Workspace("user-1").upload_authorized_file_from_path(
            "/missing/file.txt",
            str(source),
            create_parents=False,
        )

    assert not (workspace_root / "missing").exists()


def test_create_authorized_directory_uses_owner_only_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    monkeypatch.setattr(workspace_filesystem_module, "user_workspace_dir", lambda _uid: workspace_root)

    previous_umask = os.umask(0o077)
    try:
        metadata = Workspace("user-1").create_authorized_directory(
            "/",
            "project",
            root="/",
        )
    finally:
        os.umask(previous_umask)

    assert metadata["is_dir"] is True
    assert metadata["size"] == 0
    assert (workspace_root / "project").stat().st_mode & 0o777 == 0o700


def test_write_rejects_final_symlink_without_touching_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace_root = tmp_path / "workspace"
    workdir = workspace_root / "projects" / "11111111-1111-4111-8111-111111111111"
    workdir.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (workdir / "note.txt").symlink_to(outside)
    monkeypatch.setattr(workspace_filesystem_module, "user_workspace_dir", lambda _uid: workspace_root)

    with pytest.raises(PermissionError, match="symlink"):
        Workspace("user-1").write_authorized_file(
            "/projects/11111111-1111-4111-8111-111111111111/note.txt",
            b"replacement",
        )

    assert outside.read_text(encoding="utf-8") == "outside"


def test_read_authorized_file_prefix_reports_truncation(tmp_path: Path, monkeypatch) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "AGENTS.md").write_bytes(b"abcdef")
    monkeypatch.setattr(workspace_filesystem_module, "user_workspace_dir", lambda _uid: workspace_root)

    content, truncated = Workspace("user-1").read_authorized_file_prefix(
        "/AGENTS.md",
        4,
    )

    assert content == b"abcd"
    assert truncated is True


def test_workspace_boundary_rejects_deleting_its_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(workspace_filesystem_module, "user_workspace_dir", lambda _uid: tmp_path)

    with pytest.raises(ValueError, match="cannot target"):
        Workspace("user-1").delete_authorized_path("/", root="/")


@pytest.mark.parametrize("recursive", [False, True])
@pytest.mark.parametrize("link_kind", ["file", "directory", "dangling"])
def test_delete_unlinks_symlinks_without_touching_targets(tmp_path, monkeypatch, recursive, link_kind):
    """直接删除与递归清理都只移除链接，外部目标保持原样。"""
    root = tmp_path / "workspace"
    cleanup = root / "cleanup"
    cleanup.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_bytes(b"keep")
    target = {"file": marker, "directory": outside, "dangling": outside / "missing"}[link_kind]
    link = cleanup / "link"
    link.symlink_to(target, target_is_directory=link_kind == "directory")
    monkeypatch.setattr(workspace_filesystem_module, "user_workspace_dir", lambda _uid: root)

    Workspace("user-1").delete_authorized_path("/cleanup" if recursive else "/cleanup/link", root="/")

    assert not link.is_symlink()
    assert cleanup.exists() is not recursive
    assert marker.read_bytes() == b"keep"
    assert sorted(item.name for item in outside.iterdir()) == ["keep.txt"]


def test_delete_rejects_symlink_parent_without_touching_target(tmp_path, monkeypatch):
    """删除不能沿中间目录链接越过 Workspace。"""
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_bytes(b"keep")
    (root / "link").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(workspace_filesystem_module, "user_workspace_dir", lambda _uid: root)

    with pytest.raises(PermissionError):
        Workspace("user-1").delete_authorized_path("/link/keep.txt", root="/")

    assert marker.read_bytes() == b"keep"
    assert (root / "link").is_symlink()


def test_search_tree_prunes_hidden_excluded_and_overdeep_directories(tmp_path: Path, monkeypatch) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "main.py").write_text("main", encoding="utf-8")
    hidden = workspace_root / ".git"
    hidden.mkdir()
    (hidden / "secret.py").write_text("secret", encoding="utf-8")
    deep = workspace_root
    for index in range(4):
        deep = deep / f"dir-{index}"
        deep.mkdir()
    (deep / "too-deep.py").write_text("deep", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "escaped.py").write_text("escaped", encoding="utf-8")
    (workspace_root / "linked").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(workspace_filesystem_module, "user_workspace_dir", lambda _uid: workspace_root)

    results = Workspace("user-1").search_authorized_tree(
        "/",
        ".py",
        exclude_directories=frozenset({".git"}),
        exclude_hidden=True,
        max_depth=2,
    )

    assert [item["name"] for item in results] == ["main.py"]


def test_search_tree_limits_flat_directory_width_and_total_scan(tmp_path: Path, monkeypatch) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    for index in range(30):
        (workspace_root / f"file-{index:02}.txt").write_text(str(index), encoding="utf-8")
    monkeypatch.setattr(workspace_filesystem_module, "user_workspace_dir", lambda _uid: workspace_root)

    results = Workspace("user-1").search_authorized_tree(
        "/",
        "file",
        max_results=100,
        max_entries_per_directory=12,
        max_scanned_entries=7,
    )

    assert len(results) == 7
    assert all(item["name"].startswith("file-") for item in results)


def test_search_tree_entry_budget_limits_actual_directory_iteration(tmp_path: Path, monkeypatch) -> None:
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    for index in range(30):
        (workspace_root / f"file-{index:02}.txt").write_text(str(index), encoding="utf-8")
    monkeypatch.setattr(workspace_filesystem_module, "user_workspace_dir", lambda _uid: workspace_root)
    real_scandir = os.scandir
    examined = 0

    class CountingScandir:
        def __init__(self, path):
            self._iterator = real_scandir(path)

        def __enter__(self):
            self._iterator.__enter__()
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return self._iterator.__exit__(exc_type, exc_value, traceback)

        def __iter__(self):
            return self

        def __next__(self):
            nonlocal examined
            entry = next(self._iterator)
            examined += 1
            return entry

    monkeypatch.setattr(workspace_filesystem_module.os, "scandir", CountingScandir)

    Workspace("user-1").search_authorized_tree(
        "/",
        "file",
        max_results=100,
        max_entries_per_directory=12,
        max_scanned_entries=7,
    )

    assert examined == 7
