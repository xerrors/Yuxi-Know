"""将知识库内部读取模型转换为现有 HTTP 响应。"""

from __future__ import annotations

from typing import Any

from yuxi.modules.identity.permissions import ResourcePermission
from yuxi.modules.knowledge.read_models import KnowledgeBaseDetail, KnowledgeBaseSummary
from yuxi.modules.knowledge.services.uploads import StagedDocument
from yuxi.modules.knowledge.utils.security import redact_sensitive_params
from yuxi.shared.datetime import utc_isoformat


def serialize_staged_file(staged: StagedDocument, *, kb_id: str | None, filename: str, size: int) -> dict:
    """投影普通上传和工作区导入共用的既有文件字段。"""
    return {
        "file_path": staged.upload.url,
        "minio_path": staged.upload.url,
        "kb_id": kb_id,
        "content_hash": staged.content_hash,
        "filename": filename,
        "original_filename": filename,
        "size": size,
        "minio_filename": staged.upload.object_name[len(f"{kb_id or 'unknown'}/upload/") :],
        "object_name": staged.upload.object_name,
        "bucket_name": staged.upload.bucket_name,
    }


def _knowledge_base_stats(knowledge_base: KnowledgeBaseSummary) -> dict[str, int]:
    """组装兼容现有接口的嵌套统计字段。"""
    return {
        "file_count": knowledge_base.file_count,
        "folder_count": knowledge_base.folder_count,
        "row_count": knowledge_base.row_count,
        "total_size": knowledge_base.total_size,
        "chunk_count": knowledge_base.chunk_count,
        "token_count": knowledge_base.token_count,
        "pending_parse_count": knowledge_base.pending_parse_count,
        "pending_index_count": knowledge_base.pending_index_count,
        "processing_count": knowledge_base.processing_count,
    }


def serialize_knowledge_base(
    knowledge_base: KnowledgeBaseSummary,
    *,
    permission: ResourcePermission | None = None,
    redact_secrets: bool = False,
) -> dict[str, Any]:
    """转换单个知识库读取模型为 HTTP 响应。"""
    stats = _knowledge_base_stats(knowledge_base)
    additional_params = dict(knowledge_base.additional_params)
    if redact_secrets or knowledge_base.kb_type == "feishu":
        additional_params = redact_sensitive_params(additional_params)

    response = {
        "kb_id": knowledge_base.kb_id,
        "name": knowledge_base.name,
        "description": knowledge_base.description,
        "kb_type": knowledge_base.kb_type,
        "embedding_model_spec": knowledge_base.embedding_model_spec,
        "llm_model_spec": knowledge_base.llm_model_spec,
        "query_params": dict(knowledge_base.query_params),
        "metadata": dict(additional_params),
        "created_by": knowledge_base.created_by,
        "created_at": utc_isoformat(knowledge_base.created_at) if knowledge_base.created_at else None,
        "status": "已连接",
        "stats": stats,
        "row_count": knowledge_base.row_count,
        "share_config": knowledge_base.share_config,
        "additional_params": additional_params,
    }

    effective_permission = permission or knowledge_base.effective_permission
    if effective_permission is not None:
        response["effective_permission"] = effective_permission.value
        response["can_manage"] = effective_permission == ResourcePermission.MANAGE

    if isinstance(knowledge_base, KnowledgeBaseDetail):
        response["sample_questions"] = list(knowledge_base.sample_questions)
        if knowledge_base.files is not None:
            response["files"] = knowledge_base.files
            response["files_truncated"] = knowledge_base.files_truncated
            response["files_page_size"] = knowledge_base.files_page_size

    return response


def serialize_knowledge_base_list(knowledge_bases: list[KnowledgeBaseSummary]) -> dict[str, list[dict[str, Any]]]:
    """转换知识库摘要列表为现有列表接口响应。"""
    return {"knowledge_bases": [serialize_knowledge_base(knowledge_base) for knowledge_base in knowledge_bases]}
