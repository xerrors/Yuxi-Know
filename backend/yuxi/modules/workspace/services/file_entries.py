"""个人工作区与 Workdir Viewer 共用的文件条目字段。"""

from pathlib import PurePosixPath

from yuxi.shared.datetime import utc_isoformat_from_timestamp


def file_entry(scope: str, metadata: dict) -> dict:
    """规范化浏览路径、名称、类型、大小与修改时间。"""
    path = PurePosixPath(scope).as_posix()
    is_dir = bool(metadata.get("is_dir"))
    return {
        "path": f"{path}/" if is_dir and path != "/" else path,
        "name": PurePosixPath(path).name or "工作区",
        "is_dir": is_dir,
        "size": int(metadata.get("size") or 0),
        "modified_at": utc_isoformat_from_timestamp(float(metadata.get("modified_at") or 0)) or "",
    }


def sort_file_entries(entries) -> list[dict]:
    """目录排在文件前，同类按名称不区分大小写排序。"""
    return sorted(entries, key=lambda item: (not item["is_dir"], item["name"].lower()))
