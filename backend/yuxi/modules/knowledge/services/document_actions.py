"""管理端文档解析与入库作业的提交用例。"""

from yuxi.modules.background_jobs.dispatch import submit_job
from yuxi.modules.knowledge.read_models import KnowledgeBaseDetail

PENDING_PARSE_STATUSES = ["uploaded"]
PENDING_INDEX_STATUSES = ["parsed", "error_indexing"]


def _action_label(action: str) -> str:
    return "解析" if action == "parse" else "入库"


async def submit_document_action(
    *,
    kb_id: str,
    file_ids: list[str],
    params: dict,
    operator_id: str,
    kb_info: KnowledgeBaseDetail,
    action: str,
) -> dict:
    """提交指定文件的解析或入库任务。"""
    label = _action_label(action)
    job, _ = await submit_job(
        name=f"文档{label} ({kb_info.name})",
        job_type=f"knowledge_{action}",
        payload={
            "kb_id": kb_id,
            "file_ids": file_ids,
            "params": params,
            "operator_id": operator_id,
        },
    )
    return {"message": f"{label}任务已提交", "status": "queued", "job_id": job.id}


async def submit_pending_document_action(
    *,
    kb_id: str,
    params: dict,
    operator_id: str,
    kb_info: KnowledgeBaseDetail,
    action: str,
) -> dict:
    """提交按状态全量的解析或入库任务，重复请求复用活动作业。"""
    label = _action_label(action)
    if action == "parse":
        pending_count = kb_info.pending_parse_count
        statuses = PENDING_PARSE_STATUSES
    else:
        pending_count = kb_info.pending_index_count
        statuses = PENDING_INDEX_STATUSES

    if pending_count <= 0:
        return {"message": f"没有待{label}文档", "status": "success", "queued_count": 0}

    job, created = await submit_job(
        name=f"待{label}文档{label} ({kb_info.name})",
        job_type=f"knowledge_{action}",
        payload={
            "kb_id": kb_id,
            "scope": "pending",
            "action": action,
            "statuses": statuses,
            "count": pending_count,
            "params": params,
            "operator_id": operator_id,
        },
        payload_match={"kb_id": kb_id, "scope": "pending", "action": action},
    )
    return {
        "message": f"{label}任务已提交" if created else f"已有待{label}任务正在执行",
        "status": "queued",
        "job_id": job.id,
        "queued_count": pending_count,
    }
