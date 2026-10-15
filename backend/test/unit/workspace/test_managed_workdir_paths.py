from datetime import datetime
from pathlib import Path
from uuid import UUID

import pytest

from yuxi.modules.workspace import paths


@pytest.mark.parametrize(
    "value",
    [
        "projects/20260902/a1b2c3",
        "projects/20260902/a1b2c3-2",
        "projects/2026-09-02_14-35-08_a1b2c3d4",
        "projects/2026-09-02_14-35-08_a1b2c3d4-2",
    ],
)
def test_normalize_managed_workdir_path_accepts_current_and_existing_names(value: str):
    assert paths.normalize_managed_workdir_path(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "projects/20260230/a1b2c3",
        "projects/20260902/A1B2C3",
        "projects/20260902/a1b2c",
        "projects/20260902/a1b2c3-0",
        "projects/20260902/../a1b2c3",
        "projects/11111111-1111-4111-8111-111111111111",
        "projects/2026-02-30_14-35-08_a1b2c3d4",
        "projects/2026-09-02_24-00-00_a1b2c3d4",
        "projects/2026-09-02_14-35-08_A1B2C3D4",
        "projects/2026-09-02_14-35-08_a1b2c3d4-0",
        "projects/2026-09-02_14-35-08_a1b2c3d",
    ],
)
def test_normalize_managed_workdir_path_rejects_noncanonical_names(value: str):
    with pytest.raises(ValueError, match="supported projects/<managed-id>"):
        paths.normalize_managed_workdir_path(value)


def test_allocate_default_user_workdir_path_uses_shanghai_time_and_project_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(paths, "get_user_data_dir", lambda: tmp_path)

    result = paths.allocate_default_user_workdir_path(
        "user-1",
        "a1b2c3d4-e5f6-4789-8123-456789abcdef",
        allocated_at=datetime.fromisoformat("2026-09-02T06:35:08+00:00"),
    )

    assert result == "projects/20260902/a1b2c3"


def test_allocate_default_user_workdir_path_appends_first_available_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(paths, "get_user_data_dir", lambda: tmp_path)
    paths.ensure_user_workspace("user-1")
    projects = paths.user_workspace_dir("user-1") / "projects" / "20260902"
    projects.mkdir(parents=True)
    stem = "a1b2c3"
    (projects / stem).mkdir()
    (projects / f"{stem}-1").mkdir()
    (projects / f"{stem}-2").write_text("occupied", encoding="utf-8")

    result = paths.allocate_default_user_workdir_path(
        "user-1",
        UUID("a1b2c3d4-e5f6-4789-8123-456789abcdef"),
        allocated_at=datetime.fromisoformat("2026-09-02T14:35:08+08:00"),
    )

    assert result == "projects/20260902/a1b2c3-3"


def test_allocate_default_user_workdir_path_checks_unmaterialized_bindings(tmp_path: Path, monkeypatch):
    """已绑定但尚未落盘的目录同样不能复用。"""
    monkeypatch.setattr(paths, "get_user_data_dir", lambda: tmp_path)
    result = paths.allocate_default_user_workdir_path(
        "user-1",
        "a1b2c3d4-e5f6-4789-8123-456789abcdef",
        allocated_at=datetime.fromisoformat("2026-09-01T16:35:08+00:00"),
        reserved_paths={"projects/20260902/a1b2c3"},
    )
    assert result == "projects/20260902/a1b2c3-1"
    assert not paths.user_workspace_dir("user-1").exists()


@pytest.mark.parametrize("operation", ["allocate", "materialize"])
def test_managed_workdir_rejects_symlink_date_directory(tmp_path: Path, monkeypatch, operation: str):
    """日期目录不能借助符号链接指向工作区外。"""
    monkeypatch.setattr(paths, "get_user_data_dir", lambda: tmp_path)
    paths.ensure_user_workspace("user-1")
    projects = paths.user_workspace_dir("user-1") / "projects"
    projects.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (projects / "20260902").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="符号链接"):
        if operation == "allocate":
            paths.allocate_default_user_workdir_path(
                "user-1",
                "a1b2c3d4-e5f6-4789-8123-456789abcdef",
                allocated_at=datetime.fromisoformat("2026-09-02T14:35:08+08:00"),
            )
        else:
            paths.ensure_bound_user_workdir("user-1", "projects/20260902/a1b2c3")
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("relative_path", ["projects/20260902/a1b2c3", "projects/2026-09-02_14-35-08_a1b2c3d4"])
def test_bound_managed_workdir_materializes_and_preserves_bytes(tmp_path: Path, monkeypatch, relative_path: str):
    """新旧绑定均可物化，重复打开保留原有文件。"""
    monkeypatch.setattr(paths, "get_user_data_dir", lambda: tmp_path)
    paths.ensure_bound_user_workdir("user-1", relative_path)
    target = paths.user_workdir_host_dir("user-1", relative_path)
    (target / "keep.txt").write_text("keep", encoding="utf-8")
    paths.ensure_bound_user_workdir("user-1", relative_path)
    assert (target / "keep.txt").read_text(encoding="utf-8") == "keep"
