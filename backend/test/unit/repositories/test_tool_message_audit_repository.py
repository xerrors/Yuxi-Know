from types import SimpleNamespace

import pytest

from yuxi.modules.agents.repositories.tool_audit import ToolMessageAuditRepository
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.messages import Message


class _FakeDb:
    def __init__(self, runs):
        self.runs = runs

    async def get(self, model, run_id):
        assert model is AgentRun
        return self.runs.get(run_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("run_type", ["resume", "chat"])
async def test_resume_source_run_ids_follow_full_same_session_ancestry(run_type):
    ancestor = SimpleNamespace(
        id="ancestor",
        run_type="chat",
        resume_from_run_id=None,
        session_record_id=7,
        turn_id="turn",
        uid="user",
        app_id=None,
    )
    parent = SimpleNamespace(
        id="parent",
        run_type=run_type,
        resume_from_run_id="ancestor",
        session_record_id=7,
        turn_id="turn",
        uid="user",
        app_id=None,
    )
    current = SimpleNamespace(
        id="current",
        run_type=run_type,
        resume_from_run_id="parent",
        session_record_id=7,
        turn_id="turn",
        uid="user",
        app_id=None,
    )
    repository = ToolMessageAuditRepository(_FakeDb({"parent": parent, "ancestor": ancestor}))

    assert await repository._source_run_ids(current) == ["current", "parent", "ancestor"]


@pytest.mark.asyncio
async def test_resume_source_run_ids_reject_cross_session_parent():
    parent = SimpleNamespace(
        id="parent",
        run_type="chat",
        resume_from_run_id=None,
        session_record_id=8,
        turn_id="turn",
        uid="user",
        app_id=None,
    )
    current = SimpleNamespace(
        id="current",
        run_type="resume",
        resume_from_run_id="parent",
        session_record_id=7,
        turn_id="turn",
        uid="user",
        app_id=None,
    )
    repository = ToolMessageAuditRepository(_FakeDb({"parent": parent}))

    with pytest.raises(ValueError, match="agent_session"):
        await repository._source_run_ids(current)


@pytest.mark.asyncio
async def test_resume_source_run_ids_reject_adjacent_turn_even_in_same_thread():
    """相同 Thread 不能把邻近 Turn 的工具声明当作恢复来源。"""
    parent = SimpleNamespace(id="parent", resume_from_run_id=None, session_record_id=7, turn_id="other", uid="user", app_id=None)
    current = SimpleNamespace(id="current", resume_from_run_id="parent", session_record_id=7, turn_id="turn", uid="user", app_id=None)
    with pytest.raises(ValueError, match="Turn"):
        await ToolMessageAuditRepository(_FakeDb({"parent": parent}))._source_run_ids(current)


@pytest.mark.asyncio
@pytest.mark.parametrize("input_turn,rejected", [("adjacent", ["call"]), ("turn", ["other"])])
async def test_rejection_requires_accepted_approval_bound_to_same_turn(monkeypatch, input_turn, rejected):
    """历史 checkpoint 中的工具消息不能绕过当前恢复输入的审批绑定。"""

    class Db:
        async def get(self, model, identity):
            assert model is Message and identity == 10
            return SimpleNamespace(run_id="resume", turn_id=input_turn, extra_metadata={"rejected_tool_calls": rejected})

    repository = ToolMessageAuditRepository(Db())

    async def lock(**kwargs):
        return SimpleNamespace(id="resume", turn_id="turn", input_message_id=10)

    monkeypatch.setattr(repository, "_lock_run", lock)
    with pytest.raises(ValueError, match="已接受审批"):
        await repository.record_approval_rejection(
            run_id="resume", thread_id="thread", worker_id="owner", tool_call_id="call", reason="rejected"
        )
