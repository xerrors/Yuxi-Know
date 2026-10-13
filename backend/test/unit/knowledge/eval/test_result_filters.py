from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from yuxi.api.routers.knowledge.evaluation import get_evaluation_run_results
from yuxi.modules.knowledge.evaluation import service as evaluation_module
from yuxi.modules.knowledge.evaluation.service import EvaluationService


@pytest.mark.asyncio
async def test_router_rejects_unknown_result_filter_before_service_call():
    """路由在调用服务前拒绝未知筛选值。"""
    with pytest.raises(HTTPException) as exc_info:
        await get_evaluation_run_results(
            "kb_test",
            "run_1234abcd",
            result_filter="unknown",
            current_user=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "无效的评估结果筛选条件"


@pytest.mark.asyncio
@pytest.mark.parametrize("row", [None, SimpleNamespace(kb_id="other_kb")], ids=["missing", "foreign"])
async def test_run_results_reject_missing_or_foreign_run_even_with_matching_job(monkeypatch, row):
    """后台作业不能替代所属知识库的评估运行。"""

    class RunRepository:
        async def get_run(self, run_id):
            """返回缺失或其他知识库的运行。"""
            return row

    async def matching_job(job_id):
        """制造可触发旧兜底的同名后台作业。"""
        return {"id": job_id, "status": "running", "progress": 50, "message": "private job"}

    monkeypatch.setattr(evaluation_module.job_tracker, "get_job", matching_job)
    service = EvaluationService.__new__(EvaluationService)
    service.eval_repo = RunRepository()

    with pytest.raises(ValueError, match="Run not found"):
        await service.get_run_results("kb_test", "run_1234abcd")
