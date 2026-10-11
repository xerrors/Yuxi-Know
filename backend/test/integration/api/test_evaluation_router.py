"""
Integration tests for evaluation router endpoints.
"""

from __future__ import annotations

import uuid

import pytest

import asyncio

import pytest_asyncio
from sqlalchemy import delete

from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.modules.background_jobs.models import BackgroundJobRecord
from yuxi.modules.knowledge.evaluation.service import EvaluationService
from yuxi.modules.knowledge.models import EvaluationRun, KnowledgeBase
from yuxi.modules.knowledge.repositories.evaluation import EvaluationRepository

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest_asyncio.fixture(autouse=True)
async def reset_evaluation_pool():
    """每个用例绑定当前事件循环的连接池，并在结束时释放。"""
    await pg_manager.close()
    pg_manager.initialize()
    try:
        yield
    finally:
        await pg_manager.close()


async def _upload_test_dataset(test_client, admin_headers: dict[str, str], kb_id: str) -> tuple[str, str]:
    dataset_name = f"pytest_dataset_{uuid.uuid4().hex[:8]}"
    line = '{"query":"什么是单元测试？","gold_answer":"用于验证代码行为的自动化测试"}\n'

    response = await test_client.post(
        f"/api/evaluation/knowledge-bases/{kb_id}/datasets/upload",
        data={"name": dataset_name, "description": "pytest dataset for download"},
        files={"file": ("pytest_dataset.jsonl", line.encode("utf-8"), "application/x-ndjson")},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text

    payload = response.json()
    assert payload.get("message") == "success"
    dataset_id = payload.get("data", {}).get("dataset_id")
    assert dataset_id
    return dataset_id, line


async def test_download_dataset_requires_admin(test_client, standard_user):
    response = await test_client.get(
        "/api/evaluation/datasets/dataset_fake/download",
        headers=standard_user["headers"],
    )
    assert response.status_code == 403


async def test_admin_can_download_dataset(test_client, admin_headers, knowledge_base_resource):
    dataset_id, expected_line = await _upload_test_dataset(test_client, admin_headers, knowledge_base_resource["kb_id"])

    response = await test_client.get(
        f"/api/evaluation/datasets/{dataset_id}/download",
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert "application/x-ndjson" in response.headers.get("content-type", "")
    assert "attachment" in response.headers.get("content-disposition", "").lower()

    content = response.content.decode("utf-8")
    assert expected_line.strip() in content


async def test_download_dataset_not_found(test_client, admin_headers):
    response = await test_client.get(
        f"/api/evaluation/datasets/dataset_not_found_{uuid.uuid4().hex[:8]}/download",
        headers=admin_headers,
    )
    assert response.status_code == 404, response.text


@pytest.mark.parametrize("foreign_run", [False, True], ids=["missing", "foreign"])
async def test_evaluation_results_reject_job_fallback(test_client, admin_headers, knowledge_base_resource, foreign_run):
    """缺失或跨库运行返回 404，同名作业不能代替评估结果。"""
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    foreign_kb_id = f"pytest_visibility_{uuid.uuid4().hex}"
    pg_manager.initialize()
    try:
        async with pg_manager.get_async_session_context() as session:
            session.add(
                BackgroundJobRecord(
                    id=run_id,
                    name="private background job",
                    type="rag_evaluation",
                    status="success",
                    message="private job result",
                )
            )
            if foreign_run:
                session.add(KnowledgeBase(kb_id=foreign_kb_id, name=foreign_kb_id, kb_type="milvus"))
                await session.flush()
                session.add(EvaluationRun(run_id=run_id, kb_id=foreign_kb_id, name="private run", status="completed"))

        response = await test_client.get(
            f"/api/evaluation/knowledge-bases/{knowledge_base_resource['kb_id']}/runs/{run_id}",
            headers=admin_headers,
        )
        assert response.status_code == 404, response.text
        assert response.json() == {"detail": f"Run not found for {run_id}"}
    finally:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(delete(BackgroundJobRecord).where(BackgroundJobRecord.id == run_id))
            await session.execute(delete(KnowledgeBase).where(KnowledgeBase.kb_id == foreign_kb_id))


async def _create_failed_dataset(*, kb_id: str, dataset_id: str, name: str) -> None:
    """通过当前事务入口创建可恢复的失败数据集。"""
    async with pg_manager.get_async_session_context() as session:
        await EvaluationRepository.create_dataset_in_session(
            session,
            {
                "dataset_id": dataset_id,
                "kb_id": kb_id,
                "name": name,
                "description": "for resume integration test",
                "item_count": 0,
                "has_gold_chunks": True,
                "has_gold_answers": True,
                "build_metadata": {
                    "source": "generated",
                    "status": "failed",
                    "params": {
                        "count": 5,
                        "neighbors_count": 1,
                        "concurrency_count": 1,
                        "llm_model_spec": "test:model",
                        "generation_mode": "vector",
                        "graph_expand_top_k": 1,
                    },
                },
                "created_by": "admin",
            },
        )


async def test_resume_dataset_generation_enqueues_job(test_client, admin_headers, knowledge_base_resource):
    dataset_id = f"dataset_{uuid.uuid4().hex[:8]}"
    await _create_failed_dataset(
        kb_id=knowledge_base_resource["kb_id"],
        dataset_id=dataset_id,
        name="Pytest Resume Dataset",
    )

    try:
        response = await test_client.post(
            f"/api/evaluation/knowledge-bases/{knowledge_base_resource['kb_id']}/datasets/{dataset_id}/resume",
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload.get("message") == "success"
        assert payload.get("data", {}).get("job_id")
        assert payload.get("data", {}).get("message") == "评估数据集生成任务已恢复"
    finally:
        from yuxi.modules.background_jobs.service import job_tracker

        # Best-effort cleanup of any job enqueued during the test
        jobs = (await job_tracker.list_jobs()).get("jobs", [])
        for job in jobs:
            if (job.get("payload") or {}).get("dataset_id") == dataset_id:
                await job_tracker.delete_job(job["id"])
                break


async def test_resume_dataset_generation_concurrent_calls_share_job(knowledge_base_resource):
    """并发恢复调用共享同一任务（真实 DB + 真实 job_tracker，测试进程未启动 worker，任务保持 pending，时序确定）。"""
    dataset_id = f"dataset_{uuid.uuid4().hex[:8]}"
    await _create_failed_dataset(
        kb_id=knowledge_base_resource["kb_id"],
        dataset_id=dataset_id,
        name="Pytest Resume Concurrent Dataset",
    )

    try:
        service = EvaluationService()
        results = await asyncio.gather(
            service.resume_dataset_generation(knowledge_base_resource["kb_id"], dataset_id, "admin"),
            service.resume_dataset_generation(knowledge_base_resource["kb_id"], dataset_id, "admin"),
        )
        job_ids = {result["job_id"] for result in results}
        assert len(job_ids) == 1
    finally:
        from yuxi.modules.background_jobs.service import job_tracker

        jobs = (await job_tracker.list_jobs()).get("jobs", [])
        for job in jobs:
            if (job.get("payload") or {}).get("dataset_id") == dataset_id:
                await job_tracker.delete_job(job["id"])
