"""知识库原件暂存；逻辑名称与内容重复在登记用例中处理。"""

from dataclasses import dataclass
from os.path import splitext
from typing import Literal
from urllib.parse import quote
from uuid import uuid4

from yuxi.infrastructure.minio.client import MinIOClient, UploadResult, get_minio_client
from yuxi.modules.knowledge.names import normalize_name
from yuxi.modules.knowledge.utils import calculate_content_hash


@dataclass(frozen=True, slots=True)
class StagedDocument:
    """暂存对象及内容指纹，尚未创建正式文件。"""

    upload: UploadResult
    content_hash: str


async def stage_document(*, kb_id: str | None, filename: str, content: bytes, source: Literal["file", "url"] = "file") -> StagedDocument:
    """每次暂存使用独立对象键，避免同内容或并发同名对象相互覆盖。"""
    digest = await calculate_content_hash(content)
    leaf = normalize_name(filename) if source == "file" else "page.html"
    extension = splitext(leaf)[1]
    object_name = f"{kb_id or 'unknown'}/upload/{uuid4().hex}/source{extension}"
    uploaded = await get_minio_client().aupload_file(
        bucket_name=MinIOClient.KB_BUCKETS["documents"],
        object_name=object_name,
        data=content,
        content_type="text/html" if source == "url" else None,
        metadata={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename if source == "file" else leaf, safe="")},
    )
    return StagedDocument(upload=uploaded, content_hash=digest)
