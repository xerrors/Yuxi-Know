from types import SimpleNamespace

import pytest

from yuxi.modules.agents.runtime.sandbox.download import (
    MAX_SANDBOX_TREE_BYTES,
    MAX_SANDBOX_TREE_DEPTH,
    MAX_SANDBOX_TREE_ENTRIES,
    download_sandbox_directory,
)

REMOTE_DIR = "/home/user/workspace/outputs/remote/demo"


def _backend(*, ls=None, entries=(), download=None):
    """为目录下载测试提供最小列表与下载协议。"""
    download_calls = []

    def list_path(remote_dir):
        current_entries = ls(remote_dir) if ls is not None else entries
        return SimpleNamespace(error=None, entries=current_entries)

    def download_files(paths):
        download_calls.append(paths)
        if download is None:
            return [SimpleNamespace(error=None, content=b"")]
        return download(paths)

    return SimpleNamespace(ls=list_path, download_files=download_files, download_calls=download_calls)


@pytest.mark.parametrize(
    "path",
    [
        "/home/user/workspace/outputs/outside.txt",
        f"{REMOTE_DIR}/../escape.txt",
    ],
    ids=["outside-root", "parent-traversal"],
)
def test_download_sandbox_directory_rejects_outside_paths_before_download(tmp_path, path):
    """目录清单越界时必须在下载和写入前失败。"""
    backend = _backend(entries=[{"path": path, "is_dir": False, "size": 1}])

    with pytest.raises(ValueError, match="越界"):
        download_sandbox_directory(backend, REMOTE_DIR, tmp_path / "skill", empty_message="empty")

    assert backend.download_calls == []
    assert not (tmp_path / "escape.txt").exists()


@pytest.mark.parametrize(
    ("list_entries", "error"),
    [
        (
            lambda _path: [{"path": f"{REMOTE_DIR}/file-{index}.txt", "is_dir": False, "size": 1} for index in range(1001)],
            "最多 1000 个文件",
        ),
        (
            lambda path: (
                [{"path": f"{REMOTE_DIR}/dir-{index}", "is_dir": True} for index in range(MAX_SANDBOX_TREE_ENTRIES + 1)]
                if path == REMOTE_DIR
                else []
            ),
            "条目数超过限制",
        ),
        (
            lambda path: [{"path": f"{path}/nested", "is_dir": True}],
            f"最多 {MAX_SANDBOX_TREE_DEPTH} 层",
        ),
        (
            lambda _path: [{"path": f"{REMOTE_DIR}/loop", "is_dir": True}],
            "重复目录路径",
        ),
        (
            lambda _path: [{"path": f"{REMOTE_DIR}/large.bin", "is_dir": False, "size": MAX_SANDBOX_TREE_BYTES + 1}],
            "总大小超过限制",
        ),
    ],
    ids=["file-count", "entry-count", "depth", "repeated-directory", "declared-size"],
)
def test_download_sandbox_directory_rejects_oversized_or_invalid_trees(tmp_path, list_entries, error):
    """下载前拒绝超出文件、条目、深度、重复路径或声明大小边界的清单。"""
    backend = _backend(ls=list_entries)

    with pytest.raises(ValueError, match=error):
        download_sandbox_directory(backend, REMOTE_DIR, tmp_path / "skill", empty_message="empty")

    assert backend.download_calls == []


def test_download_sandbox_directory_removes_partial_target_on_failure(tmp_path):
    """部分文件下载失败时回收本次创建的目标目录。"""

    def fail_second_file(paths):
        path = paths[0]
        if path.endswith("SKILL.md"):
            return [SimpleNamespace(error=None, content=b"# demo")]
        return [SimpleNamespace(error="read_failed", content=None)]

    backend = _backend(
        entries=[
            {"path": f"{REMOTE_DIR}/SKILL.md", "is_dir": False, "size": 6},
            {"path": f"{REMOTE_DIR}/broken.txt", "is_dir": False, "size": 1},
        ],
        download=fail_second_file,
    )
    target = tmp_path / "skill"

    with pytest.raises(ValueError, match="下载沙盒文件失败"):
        download_sandbox_directory(backend, REMOTE_DIR, target, empty_message="empty")

    assert len(backend.download_calls) == 2
    assert not target.exists()


def test_download_sandbox_directory_rejects_actual_size_over_limit(monkeypatch, tmp_path):
    """响应体超过总字节上限时清理未完成目录。"""
    backend = _backend(
        entries=[{"path": f"{REMOTE_DIR}/SKILL.md", "is_dir": False, "size": 1}],
        download=lambda _paths: [SimpleNamespace(error=None, content=b"oversized")],
    )
    monkeypatch.setattr("yuxi.modules.agents.runtime.sandbox.download.MAX_SANDBOX_TREE_BYTES", 5)
    target = tmp_path / "skill"

    with pytest.raises(ValueError, match="总大小超过限制"):
        download_sandbox_directory(backend, REMOTE_DIR, target, empty_message="empty")

    assert len(backend.download_calls) == 1
    assert not target.exists()


def test_download_sandbox_directory_preserves_preexisting_target(tmp_path):
    """目标已存在时不触发下载，也不破坏原有内容。"""
    backend = _backend(entries=[{"path": f"{REMOTE_DIR}/SKILL.md", "is_dir": False, "size": 6}])
    target = tmp_path / "skill"
    target.mkdir()
    marker = target / "existing.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        download_sandbox_directory(backend, REMOTE_DIR, target, empty_message="empty")

    assert backend.download_calls == []
    assert marker.read_text(encoding="utf-8") == "keep"
