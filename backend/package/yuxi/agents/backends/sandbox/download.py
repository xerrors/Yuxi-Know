from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath

MAX_SANDBOX_TREE_FILES = 1000
MAX_SANDBOX_TREE_BYTES = 100 * 1024 * 1024
MAX_SANDBOX_TREE_ENTRIES = 2000
MAX_SANDBOX_TREE_DEPTH = 64


def _relative_sandbox_path(path: str, remote_root: PurePosixPath) -> PurePosixPath:
    """返回 Sandbox 根目录内的相对路径，并拒绝词法逃逸。"""
    try:
        relative_path = PurePosixPath(path).relative_to(remote_root)
    except ValueError as exc:
        raise ValueError("Sandbox 返回了越界文件路径") from exc
    if not relative_path.parts or ".." in relative_path.parts:
        raise ValueError("Sandbox 返回了越界文件路径")
    return relative_path


def download_sandbox_directory(
    backend,
    remote_dir: str,
    target_dir: Path,
    *,
    empty_message: str,
) -> None:
    """校验并下载 Sandbox 目录到新建的宿主目录。"""
    remote_root = PurePosixPath(remote_dir.rstrip("/"))
    files: list[tuple[str, PurePosixPath]] = []
    visited_dirs: set[str] = set()
    total_size = 0
    total_entries = 0

    def collect(current_dir: str, depth: int) -> None:
        nonlocal total_entries, total_size

        if depth > MAX_SANDBOX_TREE_DEPTH:
            raise ValueError(f"Skill 目录嵌套层级超过限制（最多 {MAX_SANDBOX_TREE_DEPTH} 层）")
        if current_dir in visited_dirs:
            raise ValueError("Sandbox 返回了重复目录路径")
        visited_dirs.add(current_dir)

        result = backend.ls(current_dir)
        if result.error:
            raise ValueError(result.error)
        for entry in result.entries or []:
            total_entries += 1
            if total_entries > MAX_SANDBOX_TREE_ENTRIES:
                raise ValueError(f"Skill 目录条目数超过限制（最多 {MAX_SANDBOX_TREE_ENTRIES} 个条目）")
            path = str(entry["path"])
            relative_path = _relative_sandbox_path(path, remote_root)
            if entry.get("is_dir"):
                collect(path, depth + 1)
                continue

            if len(files) >= MAX_SANDBOX_TREE_FILES:
                raise ValueError(f"Skill 目录文件数超过限制（最多 {MAX_SANDBOX_TREE_FILES} 个文件）")
            size = entry.get("size")
            if not isinstance(size, int) or size < 0:
                raise ValueError(f"无法确认 Sandbox 文件大小: {path}")
            total_size += size
            if total_size > MAX_SANDBOX_TREE_BYTES:
                raise ValueError("Skill 目录总大小超过限制（最多 100 MB）")
            files.append((path, relative_path))

    collect(remote_dir, 0)
    if not files:
        raise ValueError(empty_message)

    target_dir.mkdir(parents=True, exist_ok=False)
    try:
        downloaded_size = 0
        for remote_path, relative_path in files:
            response = backend.download_files([remote_path])[0]
            if response.error or response.content is None:
                raise ValueError(f"下载沙盒文件失败: {remote_path} ({response.error or 'empty_content'})")
            content = response.content
            downloaded_size += len(content)
            if downloaded_size > MAX_SANDBOX_TREE_BYTES:
                raise ValueError("Skill 目录总大小超过限制（最多 100 MB）")

            local_path = target_dir / Path(relative_path.as_posix())
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(content)
    except Exception:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise
