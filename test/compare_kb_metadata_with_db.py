import asyncio
import glob
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select

os.environ.setdefault("YUXI_SKIP_APP_INIT", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.config import config
from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_knowledge import (
    EvaluationBenchmark,
    EvaluationResult,
    EvaluationResultDetail,
    KnowledgeBase,
    KnowledgeFile,
)


def _load_json(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@dataclass(frozen=True)
class JsonState:
    kb_ids: set[str]
    file_ids: set[str]
    benchmark_ids: set[str]
    result_task_ids: set[str]
    result_detail_count: int


@dataclass(frozen=True)
class DbState:
    kb_ids: set[str]
    file_ids: set[str]
    benchmark_ids: set[str]
    result_task_ids: set[str]
    result_detail_count: int


def load_json_state() -> JsonState:
    base_dir = os.path.join(config.save_dir, "knowledge_base_data")
    global_meta = _load_json(os.path.join(base_dir, "global_metadata.json")).get("databases", {}) or {}

    kb_ids: set[str] = set(global_meta.keys())
    file_ids: set[str] = set()
    benchmark_ids: set[str] = set()
    result_task_ids: set[str] = set()
    result_detail_count = 0

    kb_type_dirs = [
        p for p in glob.glob(os.path.join(base_dir, "*_data")) if os.path.isdir(p) and os.path.basename(p) != "uploads"
    ]

    for kb_dir in kb_type_dirs:
        kb_type = os.path.basename(kb_dir)[: -len("_data")]
        meta_file = os.path.join(kb_dir, f"metadata_{kb_type}.json")
        meta = _load_json(meta_file)

        databases_meta: dict[str, Any] = meta.get("databases", {}) or {}
        files_meta: dict[str, Any] = meta.get("files", {}) or {}
        benchmarks_meta: dict[str, Any] = meta.get("benchmarks", {}) or {}

        kb_ids.update(databases_meta.keys())
        file_ids.update(files_meta.keys())

        for _db_id, bmap in benchmarks_meta.items():
            if not isinstance(bmap, dict):
                continue
            benchmark_ids.update(bmap.keys())

        for db_id in databases_meta.keys():
            result_dir = os.path.join(kb_dir, db_id, "results")
            if not os.path.isdir(result_dir):
                continue
            for result_path in glob.glob(os.path.join(result_dir, "*.json")):
                try:
                    data = _load_json(result_path)
                except Exception:
                    continue
                task_id = data.get("task_id") or os.path.splitext(os.path.basename(result_path))[0]
                result_task_ids.add(task_id)
                interim = data.get("interim_results") or data.get("results") or []
                result_detail_count += len(interim)

    return JsonState(
        kb_ids=kb_ids,
        file_ids=file_ids,
        benchmark_ids=benchmark_ids,
        result_task_ids=result_task_ids,
        result_detail_count=result_detail_count,
    )


async def load_db_state() -> DbState:
    async with pg_manager.get_async_session_context() as session:
        kb_ids = set((await session.execute(select(KnowledgeBase.db_id))).scalars().all())
        file_ids = set((await session.execute(select(KnowledgeFile.file_id))).scalars().all())
        benchmark_ids = set((await session.execute(select(EvaluationBenchmark.benchmark_id))).scalars().all())
        result_task_ids = set((await session.execute(select(EvaluationResult.task_id))).scalars().all())
        detail_count = (await session.execute(select(func.count(EvaluationResultDetail.id)))).scalar_one()

    return DbState(
        kb_ids=kb_ids,
        file_ids=file_ids,
        benchmark_ids=benchmark_ids,
        result_task_ids=result_task_ids,
        result_detail_count=int(detail_count or 0),
    )


def _diff(name: str, json_set: set[str], db_set: set[str], limit: int = 30) -> list[str]:
    missing = sorted(json_set - db_set)
    extra = sorted(db_set - json_set)
    lines: list[str] = []
    lines.append(f"{name}: json={len(json_set)} db={len(db_set)}")
    if missing:
        preview = ", ".join(missing[:limit])
        lines.append(f"  missing_in_db({len(missing)}): {preview}")
    if extra:
        preview = ", ".join(extra[:limit])
        lines.append(f"  extra_in_db({len(extra)}): {preview}")
    return lines


async def main() -> None:
    engine_url = pg_manager.async_engine.url.render_as_string(hide_password=True)
    print(f"db_url={engine_url}")

    json_state = load_json_state()
    db_state = await load_db_state()

    for line in _diff("knowledge_bases.db_id", json_state.kb_ids, db_state.kb_ids):
        print(line)
    for line in _diff("knowledge_files.file_id", json_state.file_ids, db_state.file_ids):
        print(line)
    for line in _diff("evaluation_benchmarks.benchmark_id", json_state.benchmark_ids, db_state.benchmark_ids):
        print(line)
    for line in _diff("evaluation_results.task_id", json_state.result_task_ids, db_state.result_task_ids):
        print(line)

    print(
        "evaluation_result_details: "
        f"json_count={json_state.result_detail_count} db_count={db_state.result_detail_count}"
    )


if __name__ == "__main__":
    asyncio.run(main())
