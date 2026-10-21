"""图谱请求用例保留裁决顺序、唯一登记与执行阶段边界。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.modules.knowledge.services import graph_build
from yuxi.shared.errors import InvalidOperationError, ResourceNotFoundError, StateConflictError

pytestmark = pytest.mark.asyncio


@pytest.fixture
def graph_boundary(monkeypatch):
    """只替代真实 I/O，保留提交用例和领域错误。"""
    jobs = SimpleNamespace(find_job_by_payload=AsyncMock(return_value=None))
    kb = SimpleNamespace(get_knowledge_base_info=AsyncMock(return_value=SimpleNamespace(name="知识库")))
    execution = SimpleNamespace(get_status=AsyncMock(return_value={"locked": True}), reset=AsyncMock(return_value={"status": "success"}))
    submit = AsyncMock(return_value=(SimpleNamespace(id="job"), True))
    monkeypatch.setattr(graph_build, "job_tracker", jobs)
    monkeypatch.setattr(graph_build, "knowledge_base", kb)
    monkeypatch.setattr(graph_build, "KnowledgeGraphService", lambda: execution)
    monkeypatch.setattr(graph_build, "submit_job", submit)
    return jobs, kb, execution, submit


@pytest.mark.parametrize("action", ["build", "reconcile", "reset"])
async def test_active_job_rejects_before_graph_or_submission(graph_boundary, action):
    """活动任务优先拒绝，不能先改配置、存储或登记第二个任务。"""
    jobs, kb, execution, submit = graph_boundary
    jobs.find_job_by_payload.return_value = SimpleNamespace(status="pending")
    with pytest.raises(StateConflictError, match="正在运行"):
        if action == "build":
            await graph_build.start_graph_build("kb")
        elif action == "reconcile":
            await graph_build.reconcile_graph_build("kb", mode="all_vectors")
        else:
            await graph_build.reset_graph_build("kb", clear_extraction_result=True, clear_config=False)
    kb.get_knowledge_base_info.assert_not_awaited()
    execution.get_status.assert_not_awaited()
    execution.reset.assert_not_awaited()
    submit.assert_not_awaited()


async def test_mode_validation_precedes_active_job_check(graph_boundary):
    """非法修复范围保留最高错误优先级，不访问持久任务。"""
    jobs, _, _, submit = graph_boundary
    with pytest.raises(InvalidOperationError, match="mode 必须"):
        await graph_build.reconcile_graph_build("kb", mode="invalid")
    jobs.find_job_by_payload.assert_not_awaited()
    submit.assert_not_awaited()


async def test_missing_kb_and_unlocked_configuration_reject_before_submission(graph_boundary):
    """不存在和未锁配置分别返回原错误，不创建任务。"""
    _, kb, execution, submit = graph_boundary
    kb.get_knowledge_base_info.return_value = None
    with pytest.raises(ResourceNotFoundError, match="知识库 kb 不存在"):
        await graph_build.start_graph_build("kb")
    execution.get_status.assert_not_awaited()
    kb.get_knowledge_base_info.return_value = SimpleNamespace(name="知识库")
    execution.get_status.return_value = {"locked": False}
    with pytest.raises(InvalidOperationError, match="请先确认"):
        await graph_build.start_graph_build("kb")
    submit.assert_not_awaited()


@pytest.mark.parametrize("action", ["build", "reconcile"])
async def test_registration_race_still_rejects_without_executing(graph_boundary, action):
    """预检通过后仍以唯一登记结果裁决，不在请求内执行图谱。"""
    _, _, execution, submit = graph_boundary
    submit.return_value = (SimpleNamespace(id="existing"), False)
    with pytest.raises(StateConflictError, match="已有正在运行"):
        if action == "build":
            await graph_build.start_graph_build("kb")
        else:
            await graph_build.reconcile_graph_build("kb", mode="all_vectors")
    assert submit.await_args.kwargs["payload_match"] == {"kb_id": "kb"}
    assert submit.await_args.kwargs["payload"] == (
        {"kb_id": "kb", "action": "build"} if action == "build" else {"kb_id": "kb", "action": "reconcile", "reconcile_mode": "all_vectors"}
    )
    execution.reset.assert_not_awaited()
