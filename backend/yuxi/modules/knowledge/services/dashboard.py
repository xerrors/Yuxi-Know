"""知识域 Dashboard 统计用例。"""

from typing import Any

from yuxi.modules.knowledge.repositories.bases import KnowledgeBaseRepository
from yuxi.modules.knowledge.repositories.files import KnowledgeFileRepository

FILE_TYPE_MAPPING = {
    "txt": "文本文件",
    "pdf": "PDF文档",
    "docx": "Word文档",
    "doc": "Word文档",
    "md": "Markdown",
    "html": "HTML网页",
    "htm": "HTML网页",
    "json": "JSON数据",
    "csv": "CSV表格",
    "xlsx": "Excel表格",
    "xls": "Excel表格",
    "pptx": "PowerPoint",
    "ppt": "PowerPoint",
    "png": "PNG图片",
    "jpg": "JPEG图片",
    "jpeg": "JPEG图片",
    "gif": "GIF图片",
    "svg": "SVG图片",
    "mp4": "MP4视频",
    "mp3": "MP3音频",
    "zip": "ZIP压缩包",
    "rar": "RAR压缩包",
    "7z": "7Z压缩包",
}

KNOWLEDGE_BASE_TYPE_MAPPING = {
    "faiss": "FAISS",
    "milvus": "Milvus",
    "dify": "Dify",
    "feishu": "飞书",
    "qdrant": "Qdrant",
    "elasticsearch": "Elasticsearch",
    "unknown": "未知类型",
}


async def get_knowledge_stats() -> dict[str, Any]:
    """通过单批 SQL 聚合高效汇总知识库、文件类型与存储大小统计。"""

    knowledge_bases_by_type: dict[str, int] = {}
    files_by_type: dict[str, int] = {}
    total_knowledge_bases = 0
    total_files = 0
    total_nodes = 0
    total_storage_size = 0

    for kb_type, count in await KnowledgeBaseRepository().count_by_type():
        kb_type_normalized = kb_type.lower()
        display_type = KNOWLEDGE_BASE_TYPE_MAPPING.get(kb_type_normalized, kb_type or "未知类型")
        knowledge_bases_by_type[display_type] = knowledge_bases_by_type.get(display_type, 0) + count
        total_knowledge_bases += count

    for file_type, count, size, nodes in await KnowledgeFileRepository().aggregate_dashboard_stats():
        ext = file_type.lower()
        display_name = FILE_TYPE_MAPPING.get(
            ext,
            ext.upper() + "文件" if ext and ext != "unknown" else "其他",
        )
        files_by_type[display_name] = files_by_type.get(display_name, 0) + count
        total_files += count
        total_storage_size += size
        total_nodes += nodes

    return {
        "total_knowledge_bases": total_knowledge_bases,
        "total_files": total_files,
        "total_nodes": total_nodes,
        "total_storage_size": total_storage_size,
        "knowledge_bases_by_type": knowledge_bases_by_type,
        "file_type_distribution": files_by_type,
    }
