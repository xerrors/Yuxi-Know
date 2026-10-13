"""文件写入状态与历史值的读取映射。"""


class FileStatus:
    """当前持久化文件状态；历史别名只在读取时展开。"""

    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    ERROR_PARSING = "error_parsing"
    INDEXING = "indexing"
    INDEXED = "indexed"
    ERROR_INDEXING = "error_indexing"
    DELETED = "deleted"
    FOLDER_READY = "done"


def status_filter_values(status: str | None) -> set[str] | None:
    """列表与跨库搜索共享历史状态映射，不改写已有记录。"""
    if not status or status == "all":
        return None
    return {
        FileStatus.INDEXED: {FileStatus.INDEXED, "done"},
        FileStatus.ERROR_INDEXING: {FileStatus.ERROR_INDEXING, "failed"},
    }.get(status, {status})
