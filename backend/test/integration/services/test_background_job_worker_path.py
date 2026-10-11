"""真实 ARQ worker 恢复未发布 PostgreSQL 后台作业 的 assembled path。"""

from __future__ import annotations

import asyncio
import os

import pytest
import pytest_asyncio
from sqlalchemy import delete

from yuxi.modules.knowledge.evaluation.service import EvaluationService
from yuxi.modules.knowledge.repositories.evaluation import EvaluationRepository
from yuxi.modules.background_jobs.repository import BackgroundJobRepository
import yuxi.modules.background_jobs.dispatch as job_service
from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.modules.background_jobs.models import BackgroundJobRecord
from yuxi.modules.knowledge.models import KnowledgeBase

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


@pytest_asyncio.fixture(autouse=True)
async def close_test_postgres_pool():
    """每个 pytest 事件循环退出前关闭当前循环的 PostgreSQL 连接。"""

    yield
    await pg_manager.close()


def _gate_identity(kind: str = "success") -> tuple[str, str]:
    suffix = os.getenv("BACKGROUND_JOB_GATE_ID", "local").replace("-", "_")[:24]
    return f"kb_job_worker_{suffix}_{kind}", f"background-job-worker-{suffix}-{kind}"


async def _delete_gate_facts(kb_id: str) -> None:
    datasets = await EvaluationRepository().list_datasets(kb_id)
    job_ids = [str((dataset.build_metadata or {}).get("job_id") or "") for dataset in datasets]
    async with pg_manager.get_async_session_context() as session:
        if job_ids:
            await session.execute(delete(BackgroundJobRecord).where(BackgroundJobRecord.id.in_(job_ids)))
        await session.execute(delete(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id))


async def test_prepare_job_with_failed_initial_arq_publication(monkeypatch) -> None:
    """在 worker 停止时留下已提交但尚未发布的 Job intent。"""
    kb_id, dataset_name = _gate_identity()
    await _delete_gate_facts(kb_id)
    async with pg_manager.get_async_session_context() as session:
        session.add(KnowledgeBase(kb_id=kb_id, name=dataset_name, kb_type="milvus"))

    async def fail_initial_publication(_job_id: str) -> None:
        raise ConnectionError("simulated Redis publication failure")

    monkeypatch.setattr(job_service, "publish_job", fail_initial_publication)
    submitted = await EvaluationService().generate_dataset(
        kb_id=kb_id,
        name=dataset_name,
        description="deterministic worker path",
        count=0,
        neighbors_count=1,
        concurrency_count=1,
        llm_model_spec="unused:model",
        created_by="integration",
    )

    job = await BackgroundJobRepository().get_by_id(submitted["job_id"])
    dataset = await EvaluationRepository().get_dataset(submitted["dataset_id"])
    assert job.status == "pending"
    assert (dataset.build_metadata or {}).get("status") == "pending"


async def test_shipping_worker_startup_recovers_pending_publication() -> None:
    """消费前测写入的 Job intent；system-tests 按 gate ID 跨 worker 容器重建串联。"""
    kb_id, _dataset_name = _gate_identity()
    datasets = await EvaluationRepository().list_datasets(kb_id)
    assert len(datasets) == 1
    dataset = datasets[0]
    job_id = str((dataset.build_metadata or {}).get("job_id") or "")
    assert job_id

    try:
        for _attempt in range(150):
            job = await BackgroundJobRepository().get_by_id(job_id)
            dataset = await EvaluationRepository().get_dataset(dataset.dataset_id)
            if job and job.status == "success" and (dataset.build_metadata or {}).get("status") == "completed":
                break
            await asyncio.sleep(0.1)
        else:
            raise AssertionError("后台作业 did not converge through worker startup publication")

        assert job.attempt_count == 1
        assert job.worker_id is None
        assert (dataset.build_metadata or {}).get("job_id") == job_id
    finally:
        await _delete_gate_facts(kb_id)


async def test_shipping_worker_failure_runs_domain_hook() -> None:
    """真实 worker 失败必须在同一终态事务中收敛数据集领域状态。"""
    kb_id, dataset_name = _gate_identity("failure")
    await _delete_gate_facts(kb_id)
    async with pg_manager.get_async_session_context() as session:
        session.add(KnowledgeBase(kb_id=kb_id, name=dataset_name, kb_type="dify"))

    submitted = await EvaluationService().generate_dataset(
        kb_id=kb_id,
        name=dataset_name,
        description="deterministic failure-hook path",
        count=1,
        neighbors_count=1,
        concurrency_count=1,
        llm_model_spec="unused:model",
        created_by="integration",
    )

    try:
        for _attempt in range(150):
            job = await BackgroundJobRepository().get_by_id(submitted["job_id"])
            dataset = await EvaluationRepository().get_dataset(submitted["dataset_id"])
            metadata = dataset.build_metadata or {}
            if job and job.status == "failed" and metadata.get("status") == "failed":
                break
            await asyncio.sleep(0.1)
        else:
            raise AssertionError("后台作业 failure hook did not converge through the shipping worker")

        assert job.attempt_count == 1
        assert job.worker_id is None
        assert metadata.get("job_id") == job.id
        assert metadata.get("progress") == 100
        assert metadata.get("error_message")
    finally:
        await _delete_gate_facts(kb_id)
