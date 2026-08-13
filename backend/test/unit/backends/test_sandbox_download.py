from pathlib import Path
from types import SimpleNamespace

import pytest
from yuxi.agents.backends.sandbox.download import (
    MAX_SANDBOX_TREE_BYTES,
    MAX_SANDBOX_TREE_DEPTH,
    MAX_SANDBOX_TREE_ENTRIES,
    download_sandbox_directory,
)

REMOTE_DIR = "/home/gem/user-data/outputs/remote/demo"


def test_download_sandbox_directory_rejects_outside_path_before_download(tmp_path: Path):
    class FakeBackend:
        downloaded = False

        def ls(self, _remote_dir):
            return SimpleNamespace(
                error=None,
                entries=[{"path": "/home/gem/user-data/outputs/outside.txt", "is_dir": False}],
            )

        def download_files(self, _paths):
            self.downloaded = True
            return [SimpleNamespace(error=None, content=b"")]

    backend = FakeBackend()

    with pytest.raises(ValueError, match="越界"):
        download_sandbox_directory(backend, REMOTE_DIR, tmp_path / "skill", empty_message="empty")

    assert backend.downloaded is False


def test_download_sandbox_directory_rejects_parent_path_escape(tmp_path: Path):
    class FakeBackend:
        def ls(self, _remote_dir):
            return SimpleNamespace(
                error=None,
                entries=[{"path": f"{REMOTE_DIR}/../escape.txt", "is_dir": False, "size": 1}],
            )

    with pytest.raises(ValueError, match="越界"):
        download_sandbox_directory(FakeBackend(), REMOTE_DIR, tmp_path / "skill", empty_message="empty")

    assert not (tmp_path / "escape.txt").exists()


def test_download_sandbox_directory_rejects_more_than_1000_files(tmp_path: Path):
    class FakeBackend:
        def ls(self, _remote_dir):
            return SimpleNamespace(
                error=None,
                entries=[{"path": f"{REMOTE_DIR}/file-{idx}.txt", "is_dir": False, "size": 1} for idx in range(1001)],
            )

    with pytest.raises(ValueError, match="最多 1000 个文件"):
        download_sandbox_directory(FakeBackend(), REMOTE_DIR, tmp_path / "skill", empty_message="empty")


def test_download_sandbox_directory_limits_empty_directory_entries(tmp_path: Path):
    class FakeBackend:
        def ls(self, remote_dir):
            if remote_dir == REMOTE_DIR:
                return SimpleNamespace(
                    error=None,
                    entries=[
                        {"path": f"{REMOTE_DIR}/dir-{idx}", "is_dir": True}
                        for idx in range(MAX_SANDBOX_TREE_ENTRIES + 1)
                    ],
                )
            return SimpleNamespace(error=None, entries=[])

    with pytest.raises(ValueError, match="条目数超过限制"):
        download_sandbox_directory(FakeBackend(), REMOTE_DIR, tmp_path / "skill", empty_message="empty")


def test_download_sandbox_directory_limits_directory_depth(tmp_path: Path):
    class FakeBackend:
        def ls(self, remote_dir):
            depth = remote_dir.count("/dir-")
            return SimpleNamespace(
                error=None,
                entries=[{"path": f"{remote_dir}/dir-{depth}", "is_dir": True}],
            )

    with pytest.raises(ValueError, match=f"最多 {MAX_SANDBOX_TREE_DEPTH} 层"):
        download_sandbox_directory(FakeBackend(), REMOTE_DIR, tmp_path / "skill", empty_message="empty")


def test_download_sandbox_directory_rejects_repeated_directory_path(tmp_path: Path):
    class FakeBackend:
        def ls(self, _remote_dir):
            return SimpleNamespace(
                error=None,
                entries=[{"path": f"{REMOTE_DIR}/loop", "is_dir": True}],
            )

    with pytest.raises(ValueError, match="重复目录路径"):
        download_sandbox_directory(FakeBackend(), REMOTE_DIR, tmp_path / "skill", empty_message="empty")


def test_download_sandbox_directory_rejects_oversized_tree_before_download(tmp_path: Path):
    class FakeBackend:
        downloaded = False

        def ls(self, _remote_dir):
            return SimpleNamespace(
                error=None,
                entries=[
                    {
                        "path": f"{REMOTE_DIR}/large.bin",
                        "is_dir": False,
                        "size": MAX_SANDBOX_TREE_BYTES + 1,
                    }
                ],
            )

        def download_files(self, _paths):
            self.downloaded = True
            return [SimpleNamespace(error=None, content=b"")]

    backend = FakeBackend()

    with pytest.raises(ValueError, match="总大小超过限制"):
        download_sandbox_directory(backend, REMOTE_DIR, tmp_path / "skill", empty_message="empty")

    assert backend.downloaded is False


def test_download_sandbox_directory_removes_partial_target_on_failure(tmp_path: Path):
    class FakeBackend:
        def ls(self, _remote_dir):
            return SimpleNamespace(
                error=None,
                entries=[
                    {"path": f"{REMOTE_DIR}/SKILL.md", "is_dir": False, "size": 6},
                    {"path": f"{REMOTE_DIR}/broken.txt", "is_dir": False, "size": 1},
                ],
            )

        def download_files(self, paths):
            [path] = paths
            if path == f"{REMOTE_DIR}/SKILL.md":
                return [SimpleNamespace(error=None, content=b"# demo")]
            return [SimpleNamespace(error="read_failed", content=None)]

    target = tmp_path / "skill"

    with pytest.raises(ValueError, match="下载沙盒文件失败"):
        download_sandbox_directory(FakeBackend(), REMOTE_DIR, target, empty_message="empty")

    assert not target.exists()


def test_download_sandbox_directory_rejects_actual_size_over_limit(monkeypatch, tmp_path: Path):
    class FakeBackend:
        def ls(self, _remote_dir):
            return SimpleNamespace(
                error=None,
                entries=[{"path": f"{REMOTE_DIR}/SKILL.md", "is_dir": False, "size": 1}],
            )

        def download_files(self, _paths):
            return [SimpleNamespace(error=None, content=b"oversized")]

    monkeypatch.setattr("yuxi.agents.backends.sandbox.download.MAX_SANDBOX_TREE_BYTES", 5)
    target = tmp_path / "skill"

    with pytest.raises(ValueError, match="总大小超过限制"):
        download_sandbox_directory(FakeBackend(), REMOTE_DIR, target, empty_message="empty")

    assert not target.exists()


def test_download_sandbox_directory_preserves_preexisting_target(tmp_path: Path):
    class FakeBackend:
        def ls(self, _remote_dir):
            return SimpleNamespace(
                error=None,
                entries=[{"path": f"{REMOTE_DIR}/SKILL.md", "is_dir": False, "size": 6}],
            )

    target = tmp_path / "skill"
    target.mkdir()
    marker = target / "existing.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        download_sandbox_directory(FakeBackend(), REMOTE_DIR, target, empty_message="empty")

    assert marker.read_text(encoding="utf-8") == "keep"
