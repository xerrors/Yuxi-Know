from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from yuxi.infrastructure.observability.logging import logger
from yuxi.modules.knowledge.graphs.service import KnowledgeGraphService
from yuxi.modules.knowledge.repositories.files import KnowledgeFileRepository
from yuxi.modules.knowledge.runtime import knowledge_base

if TYPE_CHECKING:
    from yuxi.workers.background_job_context import BackgroundJobContext

DOCUMENT_ACTION_BATCH_SIZE = 500
DOCUMENT_ACTION_RESULT_ITEM_LIMIT = 200


async def fail_knowledge_file_job(session, job_record, error: str) -> None:
    """原子收敛仍由失败 Job attempt 拥有的知识文件中间态。"""
    await KnowledgeFileRepository.fail_job_processing_in_session(
        session,
        job_id=job_record.id,
        error=error,
    )


async def run_knowledge_ingest(context: BackgroundJobContext) -> dict:
    """从持久 payload 重建文档添加、解析和可选索引流程。"""
    payload = context.payload
    kb_id = payload["kb_id"]
    added_files = [{**record, "index": index} for index, record in enumerate(payload["files"])]
    items = [record["item"] for record in added_files]
    params = dict(payload.get("params") or {})
    operator_id = payload["operator_id"]
    auto_index = bool(params.get("auto_index", False))
    indexing_params = {key: params[key] for key in ("chunk_preset_id", "chunk_parser_config") if key in params and params[key] is not None}
    processing_owner = {
        "processing_job_id": context.job_id,
        "processing_owner": context.worker_id,
    }

    await context.set_progress(5.0, "准备处理文档")
    total = len(items)
    processed_items: list[dict | None] = [None] * total
    parsed_files: list[dict] = []

    try:
        parse_end = 60.0 if auto_index else 95.0
        for index, record in enumerate(added_files, 1):
            await context.raise_if_cancelled()
            await context.set_progress(
                30.0 + (index / len(added_files)) * (parse_end - 30.0),
                f"[2/3] 解析文件 {index}/{len(added_files)}",
            )
            try:
                file_meta = await knowledge_base.parse_file(
                    kb_id,
                    record["file_id"],
                    operator_id=operator_id,
                    **processing_owner,
                )
                if auto_index and file_meta.get("status") == "parsed":
                    parsed_files.append(record)
                else:
                    processed_items[record["index"]] = file_meta
            except Exception as exc:
                _log_document_failure(context, kb_id=kb_id, action="parse", exc=exc, file_id=record["file_id"])
                error_type = "timeout" if isinstance(exc, TimeoutError) else "parse_failed"
                error_message = "解析超时" if isinstance(exc, TimeoutError) else "解析失败"
                processed_items[record["index"]] = {
                    "item": record["item"],
                    "status": "failed",
                    "error": f"{error_message}: {exc}",
                    "error_type": error_type,
                }

        for index, record in enumerate(parsed_files, 1):
            await context.raise_if_cancelled()
            await context.set_progress(
                60.0 + (index / len(parsed_files)) * 35.0,
                f"[3/3] 入库文件 {index}/{len(parsed_files)}",
            )
            try:
                await knowledge_base.update_file_params(
                    kb_id,
                    record["file_id"],
                    indexing_params,
                    operator_id=operator_id,
                )
                processed_items[record["index"]] = await knowledge_base.index_file(
                    kb_id,
                    record["file_id"],
                    operator_id=operator_id,
                    params=indexing_params,
                    **processing_owner,
                )
            except Exception as exc:
                _log_document_failure(context, kb_id=kb_id, action="index", exc=exc, file_id=record["file_id"])
                processed_items[record["index"]] = {
                    "item": record["item"],
                    "status": "failed",
                    "error": f"入库失败: {exc}",
                    "error_type": "index_failed",
                }
    except asyncio.CancelledError:
        await context.set_progress(100.0, "任务已取消")
        raise

    await context.raise_if_cancelled()
    final_items = [
        item
        if item is not None
        else {
            "item": items[index],
            "status": "failed",
            "error": "文件未处理",
            "error_type": "not_processed",
        }
        for index, item in enumerate(processed_items)
    ]
    failed_count = sum(_is_failed_item(item) for item in final_items)
    summary = _document_result(final_items, processed=total, failed=failed_count)
    summary.update(kb_id=kb_id, item_type="文件", submitted=total)
    await context.set_result(summary)
    await context.set_progress(100.0, f"文件处理完成，失败 {failed_count} 个" if failed_count else "文件处理完成")
    if failed_count:
        raise RuntimeError(f"文件处理完成，失败 {failed_count} 个")
    return summary


async def run_knowledge_parse(context: BackgroundJobContext) -> dict:
    """按指定文件或待处理状态执行可重建的解析任务。"""
    if context.payload.get("scope") == "pending":
        return await _run_pending_files(context, action="parse")
    return await _run_file_ids(context, action="parse")


async def run_knowledge_index(context: BackgroundJobContext) -> dict:
    """按指定文件或待处理状态执行可重建的索引任务。"""
    if context.payload.get("scope") == "pending":
        return await _run_pending_files(context, action="index")
    return await _run_file_ids(context, action="index")


async def run_knowledge_graph(context: BackgroundJobContext) -> dict:
    """根据持久 action 重建图谱构建或向量修复任务。"""
    payload = context.payload
    kb_id = payload["kb_id"]
    service = KnowledgeGraphService()
    if payload.get("action") == "reconcile":
        mode = payload.get("reconcile_mode") or "failed"
        await context.set_progress(5.0, "准备修复图谱向量索引")
        reconcile_result = await service.reconcile_vectors(kb_id, all_vectors=mode == "all_vectors")
        result = await service.build_pending_chunks(kb_id, context=context)
        await context.raise_if_cancelled()
        result["reconcile"] = reconcile_result
        await context.set_result(result)
        await context.set_progress(100.0, "图谱向量索引修复完成")
        return result

    await context.set_progress(5.0, "准备构建图谱")
    result = await service.build_pending_chunks(kb_id, context=context)
    await context.raise_if_cancelled()
    await context.set_result(result)
    await context.set_progress(
        100.0,
        f"图谱构建执行完成，成功 {result['success']} 个，抽取失败 {result['extraction_failed']} 个",
    )
    return result


async def _run_file_ids(context: BackgroundJobContext, *, action: str) -> dict:
    payload = context.payload
    kb_id = payload["kb_id"]
    file_ids = list(payload["file_ids"])
    params = dict(payload.get("params") or {})
    operator_id = payload["operator_id"]
    label = "解析" if action == "parse" else "入库"
    await context.set_progress(5.0, f"准备{label}文档")

    processed_items: list[dict] = []
    for index, file_id in enumerate(file_ids, 1):
        await context.raise_if_cancelled()
        await context.set_progress(
            5.0 + (index / len(file_ids)) * 90.0,
            f"正在{label}第 {index}/{len(file_ids)} 个文档",
        )
        try:
            result = await _process_document_file(
                context,
                kb_id=kb_id,
                file_id=file_id,
                action=action,
                params=params,
                operator_id=operator_id,
            )
            processed_items.append(result)
        except Exception as exc:
            _log_document_failure(context, kb_id=kb_id, action=action, exc=exc, file_id=file_id)
            processed_items.append({"file_id": file_id, "status": "failed", "error": str(exc)})

    await context.raise_if_cancelled()
    failed_count = sum(_is_failed_item(item) for item in processed_items)
    result = _document_result(processed_items, processed=len(processed_items), failed=failed_count)
    await context.set_result(result)
    await context.set_progress(100.0, f"{label}完成，失败 {failed_count} 个")
    if failed_count:
        raise RuntimeError(f"{label}完成，失败 {failed_count} 个")
    return result


async def _run_pending_files(context: BackgroundJobContext, *, action: str) -> dict:
    payload = context.payload
    kb_id = payload["kb_id"]
    statuses = list(payload["statuses"])
    initial_total = int(payload["count"])
    params = dict(payload.get("params") or {})
    operator_id = payload["operator_id"]
    label = "解析" if action == "parse" else "入库"
    await context.set_progress(5.0, f"准备{label}待处理文档")

    processed_count = 0
    failed_count = 0
    result_items: list[dict] = []
    after_file_id = None
    while True:
        file_ids = await knowledge_base.list_document_file_ids_by_statuses(
            kb_id,
            statuses=statuses,
            after_file_id=after_file_id,
            limit=DOCUMENT_ACTION_BATCH_SIZE,
        )
        if not file_ids:
            break
        for file_id in file_ids:
            await context.raise_if_cancelled()
            after_file_id = file_id
            processed_count += 1
            progress_total = max(initial_total, processed_count)
            await context.set_progress(
                5.0 + (processed_count / progress_total) * 90.0,
                f"正在{label}第 {processed_count}/{progress_total} 个文档",
            )
            try:
                result = await _process_document_file(
                    context,
                    kb_id=kb_id,
                    file_id=file_id,
                    action=action,
                    params=params,
                    operator_id=operator_id,
                )
                if _is_failed_item(result):
                    failed_count += 1
                _append_result_sample(result_items, result)
            except Exception as exc:
                failed_count += 1
                _log_document_failure(context, kb_id=kb_id, action=action, exc=exc, file_id=file_id)
                _append_result_sample(
                    result_items,
                    {"file_id": file_id, "status": "failed", "error": str(exc)},
                )

    await context.raise_if_cancelled()
    result = _document_result(result_items, processed=processed_count, failed=failed_count)
    await context.set_result(result)
    await context.set_progress(
        100.0,
        f"{label}完成，失败 {failed_count} 个" if processed_count else f"没有待{label}文档",
    )
    if failed_count:
        raise RuntimeError(f"{label}完成，失败 {failed_count} 个")
    return result


async def _process_document_file(
    context: BackgroundJobContext,
    *,
    kb_id: str,
    file_id: str,
    action: str,
    params: dict,
    operator_id: str,
) -> dict:
    """先更新参数，再以当前 attempt 身份执行单文件解析或入库。"""
    if params:
        await knowledge_base.update_file_params(kb_id, file_id, params, operator_id=operator_id)
    processing_owner = {
        "processing_job_id": context.job_id,
        "processing_owner": context.worker_id,
    }
    if action == "parse":
        return await knowledge_base.parse_file(kb_id, file_id, operator_id=operator_id, **processing_owner)
    return await knowledge_base.index_file(kb_id, file_id, operator_id=operator_id, params=params, **processing_owner)


def _log_document_failure(
    context: BackgroundJobContext,
    *,
    kb_id: str,
    action: str,
    exc: Exception,
    file_id: str,
) -> None:
    """记录任务与资源标识，不输出上传路径或底层异常秘密。"""
    logger.error(
        "Knowledge document failed: job_id={}, kb_id={}, file_id={}, action={}, error_type={}",
        context.job_id,
        kb_id,
        file_id,
        action,
        type(exc).__name__,
    )


def _is_failed_item(item: dict) -> bool:
    """按文件状态或错误字段识别单项失败。"""
    return item.get("status") == "failed" or bool(item.get("error"))


def _append_result_sample(items: list[dict], item: dict) -> None:
    """仅保留数量受限的任务结果样本。"""
    if len(items) < DOCUMENT_ACTION_RESULT_ITEM_LIMIT:
        items.append(item)


def _document_result(items: list[dict], *, processed: int, failed: int) -> dict:
    """任务结果保留计数和有限文件引用，文件详情由知识库拥有。"""
    samples = []
    for item in items[:DOCUMENT_ACTION_RESULT_ITEM_LIMIT]:
        sample = {key: item[key] for key in ("file_id", "status", "error") if key in item}
        if sample.get("error"):
            sample["error"] = "处理失败，详情请查看文件状态或日志"
        samples.append(sample)
    return {
        "items": samples,
        "processed": processed,
        "succeeded": processed - failed,
        "failed": failed,
        "outcome": "partial" if failed else "completed",
        "result_truncated": processed > len(samples),
    }
