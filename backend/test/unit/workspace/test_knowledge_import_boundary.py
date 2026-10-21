from __future__ import annotations

from pathlib import Path

import pytest

from yuxi.modules.identity.models import User
from yuxi.modules.workspace import paths as workspace_paths
from yuxi.modules.workspace.services import files as workspace_files
from yuxi.shared.errors import InvalidOperationError, PermissionDeniedError


@pytest.fixture
def import_workspace(tmp_path: Path, monkeypatch) -> tuple[Path, User]:
    """使用临时配置根初始化真实工作区，并缩小读取预算以验证边界。"""
    monkeypatch.setattr(workspace_paths, "get_user_data_dir", lambda: tmp_path / "user-data")
    monkeypatch.setattr(workspace_files, "MAX_WORKSPACE_UPLOAD_SIZE_BYTES", 8)
    user = User(uid="import-user")
    workspace_paths.ensure_user_workspace(user.uid)
    root = workspace_paths.user_workspace_dir(user.uid)
    (root / "imports").mkdir()
    return root, user


@pytest.mark.parametrize("content", [b"notes", b"12345678"], ids=["ordinary", "exact-limit"])
async def test_import_reads_regular_file_through_workspace_boundary(import_workspace, content: bytes) -> None:
    """普通文件与恰好达到上限的文件均返回原始文件名及完整字节。"""
    root, user = import_workspace
    source = root / "imports" / "source.md"
    source.write_bytes(content)

    result = await workspace_files.read_workspace_file_bytes(path="/imports/source.md", current_user=user)

    assert result == ("source.md", content)
    assert source.read_bytes() == content


async def test_import_rejects_oversized_file_without_changing_source(import_workspace) -> None:
    """超过上限一个字节即返回领域错误，源文件保持完整。"""
    root, user = import_workspace
    source = root / "imports" / "source.md"
    source.write_bytes(b"123456789")

    with pytest.raises(InvalidOperationError, match="文件过大"):
        await workspace_files.read_workspace_file_bytes(path="/imports/source.md", current_user=user)

    assert source.read_bytes() == b"123456789"


@pytest.mark.parametrize("link_kind", ["final", "parent"])
async def test_import_rejects_symlinks_without_touching_outside_files(import_workspace, tmp_path: Path, link_kind: str) -> None:
    """最终文件或父目录为链接时拒绝导入，外部文件与链接保持原样。"""
    root, user = import_workspace
    outside = tmp_path / "outside"
    outside.mkdir()
    external_file = outside / "source.md"
    external_file.write_bytes(b"private")
    if link_kind == "final":
        link = root / "imports" / "source.md"
        link.symlink_to(external_file)
    else:
        link = root / "linked"
        link.symlink_to(outside, target_is_directory=True)
    path = "/imports/source.md" if link_kind == "final" else "/linked/source.md"

    with pytest.raises(PermissionDeniedError, match="Access denied"):
        await workspace_files.read_workspace_file_bytes(path=path, current_user=user)

    assert external_file.read_bytes() == b"private"
    assert sorted(item.name for item in outside.iterdir()) == ["source.md"]
    assert link.is_symlink()
    assert link.readlink() == (external_file if link_kind == "final" else outside)


async def test_import_rejects_directory_without_changing_contents(import_workspace) -> None:
    """目录不能作为知识导入文件，目录内文件不受影响。"""
    root, user = import_workspace
    source = root / "imports" / "source.md"
    source.write_bytes(b"notes")

    with pytest.raises(InvalidOperationError, match="当前路径不是文件"):
        await workspace_files.read_workspace_file_bytes(path="/imports", current_user=user)

    assert source.read_bytes() == b"notes"
    assert sorted(item.name for item in (root / "imports").iterdir()) == ["source.md"]
