"""知识原件暂存：内容去重、对象上传与同名查询。"""

import os
import time
from dataclasses import dataclass
from typing import Literal

from yuxi.infrastructure.minio.client import MinIOClient, UploadResult, get_minio_client
from yuxi.modules.knowledge.runtime import knowledge_base
from yuxi.modules.knowledge.utils import calculate_content_hash
from yuxi.shared.errors import StateConflictError


class DuplicateDocumentContentError(StateConflictError):
    """知识库已有相同原件内容，由入口保留各自冲突文案。"""


@dataclass(frozen=True, slots=True)
class StagedDocument:
    """暂存完成的对象与内容事实，尚未创建正式文件或作业。"""

    upload: UploadResult
    content_hash: str
    same_name_files: list[dict]


async def stage_document(*, kb_id: str | None, filename: str, content: bytes, source: Literal["file", "url"] = "file") -> StagedDocument:
    """复用原件暂存序列，保留文件与 URL 的既有命名和 MIME。"""
    content_hash = await calculate_content_hash(content)
    if await knowledge_base.file_exists_in_knowledge_base(kb_id, content_hash):
        raise DuplicateDocumentContentError("知识库中已经存在了相同内容文件")

    folder = kb_id if kb_id else "unknown"
    if source == "url":
        object_name = f"{folder}/upload/{content_hash}.html"
        display_name = filename
        content_type = "text/html"
    else:
        basename, ext = os.path.splitext(filename)
        object_name = f"{folder}/upload/{basename}_{int(time.time() * 1000)}{ext}"
        display_name = filename.lower()
        content_type = None
    uploaded = await get_minio_client().aupload_file(
        bucket_name=MinIOClient.KB_BUCKETS["documents"],
        object_name=object_name,
        data=content,
        content_type=content_type,
    )
    same_name_files = await knowledge_base.get_same_name_files(kb_id, display_name)
    return StagedDocument(upload=uploaded, content_hash=content_hash, same_name_files=same_name_files)
