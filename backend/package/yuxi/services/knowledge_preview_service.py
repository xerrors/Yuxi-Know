"""知识库文件注册、后台预览与只读预览状态用例。"""

from __future__ import annotations

from yuxi.knowledge.preview import read_knowledge_file_preview
from yuxi.knowledge.runtime import knowledge_base
from yuxi.repositories.knowledge_file_repository import KnowledgeFileRepository
from yuxi.services.task_service import Task, TaskContext, tasker
from yuxi.utils.filepreview import MAX_BINARY_PREVIEW_SIZE_BYTES, is_office_pdf_preview_file
from yuxi.utils.logging_config import logger


async def register_knowledge_file(kb_id: str, item: str, *, params: dict, operator_id: str) -> dict:
    """注册原件后立即提交独立预览任务，解析与预览各自保留状态。"""
    file_meta = await knowledge_base.add_file_record(kb_id, item, params=params, operator_id=operator_id)
    size = file_meta.get("size")
    if is_office_pdf_preview_file(file_meta["filename"]) and (
        size is None or int(size) <= MAX_BINARY_PREVIEW_SIZE_BYTES
    ):
        try:
            await enqueue_knowledge_preview(kb_id, file_meta["file_id"])
        except Exception:
            logger.exception(
                "预览任务提交失败，原件注册已完成: kb_id={}, file_id={}",
                kb_id,
                file_meta["file_id"],
            )
    return file_meta


async def enqueue_knowledge_preview(kb_id: str, file_id: str) -> Task:
    """按知识库和文件去重，复用持久 Task 的提交后投递与恢复。"""
    payload = {"kb_id": kb_id, "file_id": file_id}
    task, _ = await tasker.enqueue_unique_by_payload(
        name="知识库文件预览",
        task_type="knowledge_preview",
        payload=payload,
        payload_match=payload,
    )
    return task


async def read_workspace_knowledge_preview(kb_id: str, file_id: str) -> dict:
    """读取现成缓存，缺失时呈现后台任务状态而不在请求中转换。"""
    response = await read_knowledge_file_preview(kb_id, file_id, prepare_office=False)
    if response.get("status") != "loading":
        return response

    task = await tasker.find_task_by_payload(
        task_type="knowledge_preview", payload_match={"kb_id": kb_id, "file_id": file_id}
    )
    if task is not None and task.status in {"failed", "cancelled"}:
        return {**response, "status": "error", "supported": False, "message": "预览生成失败，请下载原件查看"}
    if task is None or task.status == "success":
        task = await enqueue_knowledge_preview(kb_id, file_id)
    return response


async def run_knowledge_preview(context: TaskContext) -> dict:
    """由真实 worker 生成共享 PDF，发布前核对租约和原件记录。"""
    kb_id, file_id = context.payload["kb_id"], context.payload["file_id"]
    await context.raise_if_cancelled()
    await context.set_progress(10, "正在生成文件预览")

    async def before_cache_write():
        """转换可以较慢，发布缓存前重新检查执行权与文件存在性。"""
        await context.raise_if_cancelled()
        record = await KnowledgeFileRepository().get_by_file_id(file_id)
        if record is None or record.kb_id != kb_id:
            raise ValueError("原件已删除，停止发布预览")

    preview = await read_knowledge_file_preview(kb_id, file_id, before_cache_write=before_cache_write)
    if not preview.get("binary") or preview.get("preview_type") != "pdf":
        raise ValueError("当前文件无法生成 PDF 预览")
    result = {"kb_id": kb_id, "file_id": file_id, "preview_type": "pdf", "size": len(preview["content"])}
    await context.set_progress(100, "文件预览已就绪")
    return result
