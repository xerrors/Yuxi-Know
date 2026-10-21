"""直接回读执行准入拒绝的持久 Run、Turn、attempt 与清理结果。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, select

from test.integration.services.agent_input_fixtures import SCOPE, start_input_run
from yuxi.modules.agents.repositories.runs import AgentRunRepository
from yuxi.modules.agents.models.messages import Message
from yuxi.modules.agents.models.runs import AgentRun, AgentRunAttempt
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.modules.agents.repositories.sessions import SessionRepository
from yuxi.modules.agents.services import preparation, run_lifecycle, runner
from yuxi.modules.identity.models import User

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]
pytest_plugins = ["test.integration.services.agent_input_fixtures"]


@pytest.mark.parametrize(
    ("fault", "error_type", "message"),
    [
        ("payload", "invalid_input_payload", "run input_payload 必须是对象"),
        ("runtime", "invalid_runtime_payload", "run input_payload.runtime 必须是对象"),
        ("messages", "input_message_not_found", "运行任务缺少输入消息"),
        ("metadata", "invalid_input_metadata", "输入消息 metadata 必须是对象"),
        ("user", "user_not_found", f"user {SCOPE.uid} not found"),
        ("raw", "invalid_input_message", "invalid raw_message for chat input message"),
        ("manifest", "manifest_persist_failed", "运行清单固化失败，执行未开始：manifest unavailable"),
    ],
)
async def test_admission_rejection_persists_original_reason_and_finishes_cleanup(
    sessions, monkeypatch, tmp_path, fault, error_type, message
):
    """非法持久输入由唯一准入出口结算，保留原始错误且图执行始终未开始。"""
    run = await start_input_run(sessions, running=False)
    command = tmp_path / "run-command"
    command.write_text("running")
    graph_started = tmp_path / "graph-started"

    async with sessions() as db:
        current = await db.get(AgentRun, run.id)
        original_message = await db.get(Message, current.input_message_id)
        if fault == "payload":
            current.input_payload = []
        elif fault == "runtime":
            current.input_payload = {"runtime": "invalid"}
        elif fault == "messages":
            current.input_message_id = None
            await db.execute(delete(Message).where(Message.run_id == run.id))
        elif fault == "metadata":
            original_message.extra_metadata = []
        elif fault == "user":
            (await db.scalar(select(User).where(User.uid == SCOPE.uid))).is_deleted = 1
        elif fault == "raw":
            original_message.extra_metadata = {"raw_message": {"type": "human", "content": {"invalid": True}}}
        await db.commit()

    def cancel_command(*_args):
        """以真实文件变化证明持久清理边界已执行。"""
        command.unlink(missing_ok=True)

    def enter_graph(**_kwargs):
        """留下独立可回读标记，任何准入拒绝都不得触达执行流。"""
        graph_started.write_text("unexpected execution")
        raise AssertionError("准入拒绝后不得执行")

    monkeypatch.setattr(run_lifecycle, "get_sandbox_provider", lambda: SimpleNamespace(cancel_run=cancel_command))
    monkeypatch.setattr(runner, "stream_agent_execution", enter_graph)
    monkeypatch.setattr(runner, "start_session_title", lambda **_kwargs: None)
    if fault in {"raw", "manifest"}:
        # 目录授权由真实 Workdir/E2E 另证；本用例隔离 VM，只观察更晚的输入/清单拒绝。
        monkeypatch.setattr(
            runner, "_validate_run_workdir_binding", AsyncMock(return_value=SimpleNamespace(workdir_path="projects/input-project"))
        )
    if fault == "manifest":
        monkeypatch.setattr(runner, "prepare_and_record_run_execution", AsyncMock(side_effect=RuntimeError("manifest unavailable")))

    await runner.process_agent_run({"job_try": 1}, run.id)
    async with sessions() as observer:
        persisted = await observer.get(AgentRun, run.id)
        turn = await observer.get(AgentTurn, run.turn_id)
        attempt = await observer.scalar(select(AgentRunAttempt).where(AgentRunAttempt.run_id == run.id))
        assert persisted.status == turn.status == "failed"
        assert (persisted.error_type, persisted.error_message) == (error_type, message)
        assert persisted.worker_id is None and persisted.lease_expires_at is None
        assert persisted.finished_at is not None and not persisted.runtime_cleanup_pending
        assert persisted.output_message_id is None and persisted.manifest is None
        assert attempt.outcome == "failed" and attempt.error_type == error_type
        assert attempt.finished_at == persisted.finished_at
        assert turn.current_run_id == persisted.id and turn.result_run_id is None
        assert not (await SessionRepository(observer).get_session_by_thread_id("input-thread")).queue_paused
    assert not command.exists() and not graph_started.exists()


async def test_preparation_commits_manifest_once_before_returning(sessions, monkeypatch):
    """实际准备事务提交清单后才返回，重试只允许相同指纹，错误 owner 不能写入。"""
    run = await start_input_run(sessions, running=False)
    manifest = {"manifest_version": 2, "agent": {"slug": "main"}, "model": {"spec": "test:fixed"}}
    prepared = preparation.PreparedRunExecution(manifest=manifest, context=SimpleNamespace(), backend_id="test")
    monkeypatch.setattr(preparation, "prepare_run_execution", AsyncMock(return_value=prepared))
    async with sessions() as db:
        run, acquired = await AgentRunRepository(db).mark_running(run.id, worker_id="manifest-owner", lease_seconds=60)
        assert acquired
        await db.commit()
    arguments = {"run": run, "user": SimpleNamespace(uid=run.uid), "workdir_binding": SimpleNamespace(workdir_path="projects/test")}
    assert await preparation.prepare_and_record_run_execution(**arguments, worker_id="manifest-owner") is prepared
    async with sessions() as observer:
        persisted = await observer.get(AgentRun, run.id)
        assert persisted.manifest == manifest
        assert persisted.manifest_fingerprint == preparation.compute_manifest_fingerprint(manifest)
        recorded_at = persisted.manifest_recorded_at
        assert recorded_at is not None
    assert await preparation.prepare_and_record_run_execution(**arguments, worker_id="manifest-owner") is prepared
    with pytest.raises(ValueError, match="lease owner"):
        await preparation.prepare_and_record_run_execution(**arguments, worker_id="wrong-owner")
    monkeypatch.setattr(
        preparation,
        "prepare_run_execution",
        AsyncMock(return_value=preparation.PreparedRunExecution(manifest={"changed": True}, context=SimpleNamespace(), backend_id="test")),
    )
    with pytest.raises(RuntimeError, match="运行资产已在重试前变化"):
        await preparation.prepare_and_record_run_execution(**arguments, worker_id="manifest-owner")
    async with sessions() as observer:
        persisted = await observer.get(AgentRun, run.id)
        assert persisted.manifest == manifest and persisted.manifest_recorded_at == recorded_at
        assert persisted.status == "running" and persisted.worker_id == "manifest-owner"
