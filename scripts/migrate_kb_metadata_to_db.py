import argparse
import asyncio
import glob
import json
import os
import sys
from datetime import datetime, UTC
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("YUXI_SKIP_APP_INIT", "1")

from src import config
from src.repositories.evaluation_repository import EvaluationRepository
from src.repositories.knowledge_base_repository import KnowledgeBaseRepository
from src.repositories.knowledge_file_repository import KnowledgeFileRepository
from src.utils import logger


def _load_json(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _utc_dt(value: Any) -> datetime | None:
    """Convert various datetime formats to naive UTC datetime (consistent with model)."""
    if not value:
        return None
    if isinstance(value, datetime):
        # 转换为 UTC 并移除时区信息（模型使用 DateTime 无时区）
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)
    if isinstance(value, (int, float)):
        # 时间戳转换为 UTC 时间
        return datetime.fromtimestamp(value, tz=UTC).replace(tzinfo=None)
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        try:
            # 解析 ISO 格式并转换为 UTC
            dt_val = datetime.fromisoformat(v.replace("Z", "+00:00"))
            if dt_val.tzinfo is None:
                return dt_val
            return dt_val.astimezone(UTC).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def _default_share_config(meta: dict[str, Any]) -> dict[str, Any]:
    share_config = meta.get("share_config") or {}
    if "is_shared" not in share_config:
        share_config["is_shared"] = True
    if "accessible_departments" not in share_config:
        share_config["accessible_departments"] = []
    return share_config


async def rollback_all() -> None:
    eval_repo = EvaluationRepository()
    kb_repo = KnowledgeBaseRepository()
    file_repo = KnowledgeFileRepository()

    await eval_repo.delete_all()

    rows = await kb_repo.get_all()
    for row in rows:
        await file_repo.delete_by_db_id(row.db_id)
        await kb_repo.delete(row.db_id)


async def migrate(dry_run: bool, execute: bool, rollback: bool) -> None:
    base_dir = os.path.join(config.save_dir, "knowledge_base_data")
    global_meta_path = os.path.join(base_dir, "global_metadata.json")
    global_meta = _load_json(global_meta_path).get("databases", {})

    if rollback:
        if dry_run:
            logger.info("Dry-run rollback: would delete all knowledge metadata tables")
            return
        await rollback_all()
        logger.info("Rollback completed")
        return

    kb_repo = KnowledgeBaseRepository()
    file_repo = KnowledgeFileRepository()
    eval_repo = EvaluationRepository()

    kb_rows: list[dict[str, Any]] = []
    file_rows: list[tuple[str, dict[str, Any]]] = []
    benchmark_rows: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    result_detail_rows: list[tuple[str, int, dict[str, Any]]] = []

    kb_type_dirs = [
        p for p in glob.glob(os.path.join(base_dir, "*_data")) if os.path.isdir(p) and os.path.basename(p) != "uploads"
    ]

    for kb_dir in kb_type_dirs:
        kb_type = os.path.basename(kb_dir)[: -len("_data")]
        meta_file = os.path.join(kb_dir, f"metadata_{kb_type}.json")
        meta = _load_json(meta_file)
        databases_meta: dict[str, Any] = meta.get("databases", {})
        files_meta: dict[str, Any] = meta.get("files", {})
        benchmarks_meta: dict[str, Any] = meta.get("benchmarks", {})

        for db_id, db_meta in databases_meta.items():
            g = global_meta.get(db_id, {})
            created_at = _utc_dt(g.get("created_at") or db_meta.get("created_at"))
            updated_at = _utc_dt(g.get("updated_at")) or created_at
            kb_rows.append(
                {
                    "db_id": db_id,
                    "name": g.get("name") or db_meta.get("name") or db_id,
                    "description": g.get("description") or db_meta.get("description"),
                    "kb_type": g.get("kb_type") or db_meta.get("kb_type") or kb_type,
                    "embed_info": db_meta.get("embed_info") or g.get("embed_info"),
                    "llm_info": db_meta.get("llm_info") or g.get("llm_info"),
                    "query_params": db_meta.get("query_params") or g.get("query_params"),
                    "additional_params": g.get("additional_params") or db_meta.get("metadata") or {},
                    "share_config": _default_share_config(g or {}),
                    "mindmap": g.get("mindmap"),
                    "sample_questions": g.get("sample_questions") or [],
                    "created_at": created_at,
                    "updated_at": updated_at,
                }
            )

        for file_id, fmeta in files_meta.items():
            db_id = fmeta.get("database_id")
            if not db_id:
                continue
            file_rows.append(
                (
                    file_id,
                    {
                        "db_id": db_id,
                        "parent_id": fmeta.get("parent_id"),
                        "filename": fmeta.get("filename") or "",
                        "original_filename": fmeta.get("original_filename") or fmeta.get("file_name"),
                        "file_type": fmeta.get("file_type") or fmeta.get("type"),
                        "path": fmeta.get("path"),
                        "minio_url": fmeta.get("minio_url"),
                        "markdown_file": fmeta.get("markdown_file"),
                        "status": fmeta.get("status"),
                        "content_hash": fmeta.get("content_hash"),
                        "file_size": fmeta.get("size") or fmeta.get("file_size"),
                        "content_type": fmeta.get("content_type"),
                        "processing_params": fmeta.get("processing_params"),
                        "is_folder": bool(fmeta.get("is_folder", False)),
                        "error_message": fmeta.get("error") or fmeta.get("error_message"),
                        "created_by": str(fmeta.get("created_by")) if fmeta.get("created_by") else None,
                        "updated_by": str(fmeta.get("updated_by")) if fmeta.get("updated_by") else None,
                        "created_at": _utc_dt(fmeta.get("created_at")),
                        "updated_at": _utc_dt(fmeta.get("updated_at")) or _utc_dt(fmeta.get("created_at")),
                    },
                )
            )

        for db_id, bmap in benchmarks_meta.items():
            if not isinstance(bmap, dict):
                continue
            for benchmark_id, bmeta in bmap.items():
                benchmark_rows.append(
                    {
                        "benchmark_id": benchmark_id,
                        "db_id": db_id,
                        "name": bmeta.get("name") or benchmark_id,
                        "description": bmeta.get("description"),
                        "question_count": int(bmeta.get("question_count") or 0),
                        "has_gold_chunks": bool(bmeta.get("has_gold_chunks")),
                        "has_gold_answers": bool(bmeta.get("has_gold_answers")),
                        "data_file_path": bmeta.get("benchmark_file") or bmeta.get("data_file_path"),
                        "created_by": str(bmeta.get("created_by")) if bmeta.get("created_by") else None,
                        "created_at": _utc_dt(bmeta.get("created_at")),
                        "updated_at": _utc_dt(bmeta.get("updated_at")) or _utc_dt(bmeta.get("created_at")),
                    }
                )

        for db_id in databases_meta.keys():
            result_dir = os.path.join(kb_dir, db_id, "results")
            if not os.path.isdir(result_dir):
                continue
            for result_path in glob.glob(os.path.join(result_dir, "*.json")):
                try:
                    data = _load_json(result_path)
                except Exception as exc:
                    logger.warning(f"Skip invalid result file {result_path}: {exc}")
                    continue
                task_id = data.get("task_id") or os.path.splitext(os.path.basename(result_path))[0]
                benchmark_id = data.get("benchmark_id")
                started_at = _utc_dt(data.get("started_at"))
                result_rows.append(
                    {
                        "task_id": task_id,
                        "db_id": db_id,
                        "benchmark_id": benchmark_id,
                        "status": data.get("status") or "completed",
                        "retrieval_config": data.get("retrieval_config") or {},
                        "metrics": data.get("metrics") or {},
                        "overall_score": data.get("overall_score"),
                        "total_questions": int(data.get("total_questions") or 0),
                        "completed_questions": int(data.get("completed_questions") or 0),
                        "started_at": started_at,
                        "completed_at": _utc_dt(data.get("completed_at")) or started_at,
                        "created_by": str(data.get("created_by")) if data.get("created_by") else None,
                    }
                )
                interim = data.get("interim_results") or data.get("results") or []
                for idx, item in enumerate(interim):
                    result_detail_rows.append(
                        (
                            task_id,
                            idx,
                            {
                                "query_text": item.get("query") or item.get("query_text") or "",
                                "gold_chunk_ids": item.get("gold_chunk_ids"),
                                "gold_answer": item.get("gold_answer"),
                                "generated_answer": item.get("generated_answer"),
                                "retrieved_chunks": item.get("retrieved_chunks"),
                                "metrics": item.get("metrics") or {},
                            },
                        )
                    )

    logger.info(
        f"Prepared: knowledge_bases={len(kb_rows)}, knowledge_files={len(file_rows)}, "
        f"benchmarks={len(benchmark_rows)}, results={len(result_rows)}, result_details={len(result_detail_rows)}"
    )

    if dry_run and not execute:
        return

    for payload in kb_rows:
        db_id = payload["db_id"]
        existing = await kb_repo.get_by_id(db_id)
        data = payload.copy()
        if existing is None:
            await kb_repo.create(data)
        else:
            await kb_repo.update(db_id, data)

    # 先插入文件夹，再插入普通文件（确保父文件夹先存在）
    folders = [(fid, data) for fid, data in file_rows if data.get("is_folder")]
    files = [(fid, data) for fid, data in file_rows if not data.get("is_folder")]

    for file_id, data in folders:
        await file_repo.upsert(file_id=file_id, data=data)

    for file_id, data in files:
        await file_repo.upsert(file_id=file_id, data=data)

    for payload in benchmark_rows:
        # 检查知识库是否存在
        kb = await kb_repo.get_by_id(payload["db_id"])
        if kb is None:
            logger.warning(f"Skipping benchmark {payload['benchmark_id']}: knowledge base {payload['db_id']} not found")
            continue
        existing = await eval_repo.get_benchmark(payload["benchmark_id"])
        if existing is None:
            await eval_repo.create_benchmark(payload)

    for payload in result_rows:
        # 检查知识库是否存在
        kb = await kb_repo.get_by_id(payload["db_id"])
        if kb is None:
            logger.warning(f"Skipping result {payload['task_id']}: knowledge base {payload['db_id']} not found")
            continue
        existing = await eval_repo.get_result(payload["task_id"])
        if existing is None:
            await eval_repo.create_result(payload)
        else:
            await eval_repo.update_result(payload["task_id"], payload)

    for task_id, idx, data in result_detail_rows:
        await eval_repo.upsert_result_detail(task_id=task_id, query_index=idx, data=data)

    logger.info("Migration completed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()

    if not args.dry_run and not args.execute and not args.rollback:
        args.dry_run = True

    asyncio.run(migrate(dry_run=args.dry_run, execute=args.execute, rollback=args.rollback))


if __name__ == "__main__":
    main()
