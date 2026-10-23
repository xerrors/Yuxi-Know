from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from arq.worker import RetryJob

import yuxi.modules.agents.services.run_lifecycle as lifecycle
import yuxi.bootstrap.worker as worker_bootstrap
import yuxi.modules.agents.services.event_writer as event_writer
import yuxi.modules.agents.services.leases as leases
import yuxi.modules.agents.services.runner as runner
from yuxi.modules.agents.services.execution import RunExecutionResult


@pytest.fixture(autouse=True)
def api_key_derivation_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-that-is-at-least-32-chars")
    monkeypatch.setenv("API_KEY_DERIVATION_SECRET", "test-api-key-derivation-secret-32-chars")


class _RaisingAsyncIter:
    def __init__(self, exc: Exception):
        self._exc = exc

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise self._exc

    async def aclose(self):
        """模拟可关闭的执行流。"""


@pytest.mark.parametrize("cancellation", ["signal", "outer", "consumer_body"])
async def test_stream_cancellation_closes_execution_before_owner_cleanup(cancellation):
    """用户信号、基础设施取消及消费侧取消均不得留下旧执行副作用。"""
    entered, release, closed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    effects = []
    ctx = runner.RunContext(run_id="run-cancel", worker_id="owner")

    async def stream():
        """用独立屏障检测取消后仍继续执行的旧任务。"""
        try:
            if cancellation == "consumer_body":
                yield b"first"
            entered.set()
            await release.wait()
            effects.append("old execution continued")
            yield b"late"
        finally:
            closed.set()

    producer = stream()

    async def consume():
        """以 Worker 的相同 close 边界消费，退出代表允许外层释放 owner。"""
        async with runner.aclosing(runner._consume_stream_with_cancel(producer, ctx)) as chunks:
            async for _ in chunks:
                entered.set()
                await release.wait()

    consumer = asyncio.create_task(consume())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        if cancellation == "signal":
            ctx.cancel_event.set()
        else:
            consumer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(consumer, 1)
        assert closed.is_set(), "释放 owner 时旧执行尚未关闭"
        release.set()
        await asyncio.sleep(0)
        assert effects == []
    finally:
        release.set()
        consumer.cancel()
        await asyncio.gather(consumer, return_exceptions=True)
        await asyncio.sleep(0)
        await producer.aclose()


async def test_cancel_waiter_is_reused_for_all_stream_chunks():
    """完整输出保持顺序，一个 Run 的取消等待器只启动一次。"""
    waiter_starts = 0

    class Context:
        """只提供消费器需要的取消协议。"""

        async def wait_cancelled(self):
            """持续等待，记录逻辑等待器的创建次数。"""
            nonlocal waiter_starts
            waiter_starts += 1
            await asyncio.Event().wait()

    async def stream():
        """生成连续事件。"""
        for index in range(50):
            yield index

    results = [row async for row in runner._consume_stream_with_cancel(stream(), Context())]
    assert results == list(range(50))
    assert waiter_starts == 1


async def test_repeated_cancel_waits_for_async_execution_cleanup():
    """二次取消不能越过异步收尾屏障而释放执行 owner。"""
    entered, cleanup_started, release_cleanup, closed = (asyncio.Event() for _ in range(4))
    ctx = runner.RunContext(run_id="repeat-cancel", worker_id="owner")

    async def stream():
        """用异步屏障模拟节点和执行流的清理。"""
        try:
            entered.set()
            await asyncio.Event().wait()
            yield b"unreachable"
        finally:
            cleanup_started.set()
            await release_cleanup.wait()
            closed.set()

    async def consume():
        """外层退出是 owner 允许释放的时点。"""
        async with runner.aclosing(runner._consume_stream_with_cancel(stream(), ctx)) as chunks:
            async for _ in chunks:
                pass

    consumer = asyncio.create_task(consume())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        consumer.cancel()
        await asyncio.wait_for(cleanup_started.wait(), 1)
        consumer.cancel()
        await asyncio.sleep(0)
        assert not consumer.done(), "二次取消提前释放了仍在清理的 owner"
        release_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(consumer, 1)
        assert closed.is_set(), "执行流的异步清理被二次取消打断"
    finally:
        release_cleanup.set()
        consumer.cancel()
        await asyncio.gather(consumer, return_exceptions=True)


class _ExecutionAsyncIter:
    async def aclose(self):
        """模拟真实 async generator 的显式收尾协议。"""

    def __init__(self, values: list[dict | RunExecutionResult]):
        self._values = list(values)
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._values):
            raise StopAsyncIteration
        value = self._values[self._idx]
        self._idx += 1
        return value


def _terminal_result(status: str = "finished", **chunk) -> RunExecutionResult:
    """模拟执行器已读回 PostgreSQL checkpoint 并提交业务终态。"""
    return RunExecutionResult(
        checkpoint=SimpleNamespace(values={}),
        status={
            "finished": "completed",
            "human_approval_required": "interrupted",
            "ask_user_question_required": "interrupted",
        }.get(status, status),
        committed=True,
    )


def _build_run() -> SimpleNamespace:
    return SimpleNamespace(
        id="run-1",
        status="pending",
        turn_id="turn-1",
        app_id=None,
        input_payload={"model_spec": "provider:model"},
        input_message_id=10,
        run_type="chat",
        agent_slug="ChatbotAgent",
        uid="user-1",
        session_record_id=7,
        thread_id="thread-1",
        runtime_scope_id="thread-1",
        runtime_cleanup_pending=False,
        created_by_run_id=None,
    )


@pytest.mark.asyncio
async def test_validate_run_workdir_binding_checks_shared_tree(monkeypatch):
    run = _build_run()
    run.thread_id = "child-thread"
    run.runtime_scope_id = "root-thread"
    member = SimpleNamespace(tree_root_thread_id="root-thread", project_id="project-1")
    root = SimpleNamespace(
        thread_id="root-thread",
        tree_root_thread_id="root-thread",
        parent_thread_id=None,
        uid=run.uid,
        app_id=None,
        project_id="project-1",
    )
    db = SimpleNamespace(get=AsyncMock(return_value=member), scalar=AsyncMock(return_value=root))

    @asynccontextmanager
    async def fake_session():
        yield db

    async def fake_resolve(**kwargs):
        return SimpleNamespace(session_record_id=run.session_record_id, workdir_path="projects/shared")

    monkeypatch.setattr(worker_bootstrap.pg_manager, "get_async_session_context", fake_session)
    monkeypatch.setattr(runner, "resolve_authorized_workdir", fake_resolve)
    assert (await runner._validate_run_workdir_binding(run)).session_record_id == run.session_record_id
    for field, invalid in (
        ("uid", "foreign-user"),
        ("app_id", "foreign-app"),
        ("project_id", "foreign-project"),
        ("parent_thread_id", "not-root"),
    ):
        original = getattr(root, field)
        setattr(root, field, invalid)
        with pytest.raises(runner.NonRetryableRunError, match="共享沙盒树归属非法"):
            await runner._validate_run_workdir_binding(run)
        setattr(root, field, original)
    member.tree_root_thread_id = "foreign-tree"
    with pytest.raises(runner.NonRetryableRunError, match="共享沙盒树归属非法"):
        await runner._validate_run_workdir_binding(run)
    member.tree_root_thread_id = "root-thread"

    async def changed_workdir(**kwargs):
        binding = await fake_resolve(**kwargs)
        if kwargs["thread_id"] == "root-thread":
            binding.workdir_path = "projects/foreign"
        return binding

    monkeypatch.setattr(runner, "resolve_authorized_workdir", changed_workdir)
    with pytest.raises(runner.NonRetryableRunError, match="Workdir 不一致"):
        await runner._validate_run_workdir_binding(run)


@pytest.mark.asyncio
async def test_cancelling_member_releases_its_run_cleanup_responsibility(monkeypatch: pytest.MonkeyPatch):
    run = _build_run()
    release_runtime = AsyncMock()

    async def fake_noop(*args, **kwargs):
        del args, kwargs
        return None

    async def fake_tree_finished(*args, **kwargs):
        del args, kwargs
        return True

    async def fake_mark_terminal(*args, **kwargs):
        del args, kwargs
        return runner.TerminalTransition(status="cancelled", changed=True)

    monkeypatch.setattr(runner, "flush_writer_best_effort", fake_noop)
    monkeypatch.setattr(runner, "_require_runtime_cleanup", release_runtime)
    monkeypatch.setattr(runner, "mark_run_terminal", fake_mark_terminal)
    monkeypatch.setattr(runner, "append_run_event_best_effort", fake_noop)
    monkeypatch.setattr(runner, "publish_run_settlement", fake_noop)

    monkeypatch.setattr(runner, "_get_run", AsyncMock(return_value=run))

    transition = await runner._settle_uncommitted_run(
        status="cancelled",
        run_id=run.id,
        thread_id=run.thread_id,
        current_user=None,
        worker_id="worker-1",
        writer=SimpleNamespace(),
    )

    assert transition == runner.TerminalTransition(status="cancelled", changed=True)
    release_runtime.assert_awaited_once()
    assert release_runtime.call_args.args[0] is run


def _patch_common(monkeypatch: pytest.MonkeyPatch, run_obj: SimpleNamespace):
    @asynccontextmanager
    async def fake_session_ctx():
        yield SimpleNamespace(commit=AsyncMock())

    async def fake_noop(*args, **kwargs):
        del args, kwargs
        return None

    async def fake_cleanup(*args, **kwargs):
        del args, kwargs
        return True

    async def fake_mark_run_running(*args, **kwargs):
        del args, kwargs
        return True

    async def fake_get_run(run_id: str):
        del run_id
        return run_obj

    async def fake_load_user(uid: str):
        del uid
        return SimpleNamespace(id=1, uid="user-1")

    async def fake_load_run_input_messages(run):
        assert run.input_message_id == 10
        return [
            SimpleNamespace(
                id=10,
                source_input_id="input-1",
                content="hello",
                image_content=None,
                extra_metadata={"raw_message": {"type": "human", "content": "hello"}},
            )
        ]

    async def fake_get_agent_state_view(**kwargs):
        del kwargs
        return {"agent_state": None}

    async def fake_not_cancelled(self):
        del self
        return False

    async def fake_tree_finished(*args, **kwargs):
        del args, kwargs
        return True

    monkeypatch.setattr(worker_bootstrap.pg_manager, "get_async_session_context", fake_session_ctx)
    monkeypatch.setattr(runner, "_get_run", fake_get_run)
    monkeypatch.setattr(runner, "_load_user", fake_load_user)
    monkeypatch.setattr(runner.AgentEnvRepository, "get_by_uid", AsyncMock(return_value=None))
    monkeypatch.setattr(runner, "_load_run_input_messages", fake_load_run_input_messages)
    monkeypatch.setattr(runner, "get_agent_state_view", fake_get_agent_state_view)
    monkeypatch.setattr(runner, "mark_run_running", fake_mark_run_running)
    monkeypatch.setattr(runner, "release_run_lease_for_retry", fake_mark_run_running)
    monkeypatch.setattr(lifecycle, "dispatch_next_input", fake_noop)
    monkeypatch.setattr(lifecycle, "finish_turn_observation_if_terminal", fake_noop)
    from test.unit.support.agent_context_fixtures import prepared_execution

    async def fake_prepare_execution(**kwargs):
        run = kwargs["run"]
        execution = prepared_execution(
            model=run.input_payload.get("model_spec"),
            runtime_scope_id=run.runtime_scope_id,
        )
        return execution

    monkeypatch.setattr(runner, "prepare_and_record_run_execution", fake_prepare_execution)
    monkeypatch.setattr(runner, "_record_run_timing_best_effort", fake_noop)
    monkeypatch.setattr(
        runner,
        "_validate_run_workdir_binding",
        AsyncMock(
            return_value=SimpleNamespace(
                workdir_path="projects/11111111-1111-4111-8111-111111111111",
                virtual_path="/home/user/workspace/projects/11111111-1111-4111-8111-111111111111",
            )
        ),
    )
    monkeypatch.setattr(runner, "complete_run_runtime_cleanup", fake_cleanup)
    monkeypatch.setattr(lifecycle, "clear_cancel_signal", fake_noop)
    monkeypatch.setattr(runner, "publish_run_settlement", fake_noop)
    monkeypatch.setattr(runner, "stream_agent_execution", lambda **kwargs: object())
    monkeypatch.setattr(runner.RunContext, "start", fake_noop)
    monkeypatch.setattr(runner.RunContext, "close", fake_noop)
    monkeypatch.setattr(runner.RunContext, "is_cancelled", fake_not_cancelled)
    monkeypatch.setattr(leases, "complete_run_runtime_cleanup", AsyncMock(return_value=True))


@pytest.mark.asyncio
async def test_process_agent_run_rejects_corrupted_runtime_scope_before_execution(
    monkeypatch: pytest.MonkeyPatch,
):
    run_obj = _build_run()
    run_obj.runtime_scope_id = "other-root-thread"
    _patch_common(monkeypatch, run_obj)
    terminal_calls: list[dict] = []
    stream_called = False

    async def reject_binding(_run):
        raise runner.NonRetryableRunError("AgentRun 的 runtime scope 与 Project Workdir 绑定不一致")

    async def fake_mark_terminal(run_id: str, status: str, *args, **kwargs):
        terminal_calls.append({"run_id": run_id, "status": status, "args": args, **kwargs})
        return runner.TerminalTransition(status=status, changed=True)

    def fake_stream_agent_execution(**_kwargs):
        nonlocal stream_called
        stream_called = True
        return _ExecutionAsyncIter([])

    monkeypatch.setattr(runner, "_validate_run_workdir_binding", reject_binding)
    monkeypatch.setattr(runner, "mark_run_terminal", fake_mark_terminal)
    monkeypatch.setattr(runner, "stream_agent_execution", fake_stream_agent_execution)

    await runner.process_agent_run({"job_try": 1}, run_obj.id)

    assert stream_called is False
    assert terminal_calls[0]["status"] == "failed"
    assert terminal_calls[0]["error_type"] == "invalid_runtime_scope"


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_run_environment_snapshot_survives_updates_and_is_released(monkeypatch, fails):
    """线程与异步子任务复用启动快照，成功或失败退出均释放密钥。"""
    from yuxi.modules.agents.runtime.sandbox import sandbox_run_env

    run = _build_run()
    _patch_common(monkeypatch, run)
    saved = SimpleNamespace(env={"RUN_VALUE": "before"})
    monkeypatch.setattr(runner.AgentEnvRepository, "get_by_uid", AsyncMock(return_value=saved))
    observed = []

    async def stream(**kwargs):
        """更新来源配置后，两个执行通道仍读取同一份快照。"""
        saved.env["RUN_VALUE"] = "after"
        observed.append(await asyncio.to_thread(lambda: dict(sandbox_run_env.get())))
        observed.append(dict(sandbox_run_env.get()))
        if fails:
            raise ValueError("fixture execution failed")
        run.status = "completed"
        yield _terminal_result()

    monkeypatch.setattr(runner, "stream_agent_execution", stream)
    monkeypatch.setattr(runner, "_settle_uncommitted_run", AsyncMock())
    assert sandbox_run_env.get() is None
    await runner.process_agent_run({"job_try": 1}, run.id)
    assert observed == [{"RUN_VALUE": "before"}, {"RUN_VALUE": "before"}]
    assert sandbox_run_env.get() is None

    observed.clear()
    run.status = "pending"
    await runner.process_agent_run({"job_try": 1}, run.id)
    assert observed == [{"RUN_VALUE": "after"}, {"RUN_VALUE": "after"}]
    assert sandbox_run_env.get() is None


@pytest.mark.asyncio
async def test_process_agent_run_keeps_source_without_legacy_invocation_metadata(monkeypatch: pytest.MonkeyPatch):
    run_obj = _build_run()
    _patch_common(monkeypatch, run_obj)

    captured: dict[str, object] = {}
    terminal_statuses: list[str] = []

    async def fake_load_run_input_messages(run):
        assert run.input_message_id == 10
        return [
            SimpleNamespace(
                id=10,
                source_input_id="input-1",
                content="hello",
                image_content=None,
                extra_metadata={
                    "raw_message": {"type": "human", "content": "hello"},
                    "source": "agent_call",
                    "agent_invocation_meta": {"trace_id": "trace-1"},
                    "evaluation": {"dataset_name": "legacy-top-level"},
                    "custom_variables": {"system_prompt": "legacy"},
                },
            )
        ]

    async def fake_mark_terminal(run_id: str, status: str, error_type=None, error_message=None, **kwargs):
        del run_id, kwargs
        terminal_statuses.append(status)
        return runner.TerminalTransition(status=status, changed=True)

    def fake_stream_agent_execution(**kwargs):
        captured.update(kwargs)
        run_obj.status = "completed"
        return _ExecutionAsyncIter([_terminal_result()])

    monkeypatch.setattr(runner, "_load_run_input_messages", fake_load_run_input_messages)
    monkeypatch.setattr(runner, "mark_run_terminal", fake_mark_terminal)
    monkeypatch.setattr(runner, "stream_agent_execution", fake_stream_agent_execution)

    await runner.process_agent_run({"job_try": 1}, "run-1")

    meta = captured["meta"]
    assert meta["source"] == "agent_call"
    assert "agent_invocation_meta" not in meta
    assert "evaluation" not in meta
    assert "custom_variables" not in meta
    assert terminal_statuses == []


async def test_next_fifo_input_dispatches_before_optional_turn_trace(monkeypatch: pytest.MonkeyPatch):
    """Langfuse 根导出等待时，已完成 Run 仍先领取下一条持久输入。"""
    run_obj = _build_run()
    _patch_common(monkeypatch, run_obj)
    order = []

    async def stream():
        """模拟已在输出事务中完成的当前 Run。"""
        run_obj.status = "completed"
        yield _terminal_result()

    async def dispatch(**_kwargs):
        order.append("dispatch")

    async def trace(_turn_id):
        order.append("trace")

    monkeypatch.setattr(runner, "stream_agent_execution", lambda **_kwargs: stream())
    monkeypatch.setattr(lifecycle, "dispatch_next_input", dispatch)
    monkeypatch.setattr(lifecycle, "finish_turn_observation_if_terminal", trace)

    await runner.process_agent_run({"job_try": 1}, run_obj.id)

    assert order == ["dispatch", "trace"]


@pytest.mark.asyncio
async def test_terminal_cleanup_failure_keeps_end_event_unpublished(monkeypatch: pytest.MonkeyPatch):
    """cleanup 失败必须保留 durable fence，不能先向客户端宣告 execution tree 已结束。"""
    run_obj = _build_run()
    _patch_common(monkeypatch, run_obj)
    end_event = AsyncMock()

    async def fail_cleanup(_run, _message):
        raise runner.RuntimeCleanupPendingError("runtime cleanup pending")

    monkeypatch.setattr(runner, "_require_runtime_cleanup", fail_cleanup)
    monkeypatch.setattr(runner, "publish_run_settlement", end_event)

    def committed_stream(**_kwargs):
        run_obj.status = "completed"
        return _ExecutionAsyncIter([_terminal_result()])

    monkeypatch.setattr(runner, "stream_agent_execution", committed_stream)

    with pytest.raises(runner.RuntimeCleanupPendingError):
        await runner.process_agent_run({"job_try": 1}, "run-1")

    end_event.assert_not_awaited()


@pytest.mark.parametrize(
    "events",
    [
        [{"status": "finished", "thread_id": "thread-1", "terminal_committed": True}],
        [RunExecutionResult(checkpoint=None, status="completed", committed=True)],
        [],
    ],
)
async def test_worker_rejects_success_without_final_checkpoint(monkeypatch: pytest.MonkeyPatch, events):
    """字典终态、空 checkpoint 或流提前耗尽都不能完成 Run。"""
    run_obj = _build_run()
    _patch_common(monkeypatch, run_obj)
    terminals = []

    async def mark_terminal(run_id, status, error_type=None, error_message=None, **kwargs):
        terminals.append((run_id, status, error_message or kwargs.get("error_message")))
        return runner.TerminalTransition(status=status, changed=True)

    monkeypatch.setattr(runner, "mark_run_terminal", mark_terminal)
    monkeypatch.setattr(runner, "stream_agent_execution", lambda **_kwargs: _ExecutionAsyncIter(events))

    await runner.process_agent_run({"job_try": 1}, run_obj.id)

    assert terminals and terminals[0][1] == "failed"
    assert any(reason in terminals[0][2] for reason in ("checkpoint", "明确归属", "执行结果"))


async def test_worker_rejects_waitpoint_without_postgres_terminal(monkeypatch: pytest.MonkeyPatch):
    """checkpoint 中断事件不能代替 PostgreSQL 的等待终态。"""
    run_obj = _build_run()
    _patch_common(monkeypatch, run_obj)
    terminals = []

    async def mark_terminal(run_id, status, error_type=None, error_message=None, **kwargs):
        terminals.append((run_id, status, error_message or kwargs.get("error_message")))
        return runner.TerminalTransition(status=status, changed=True)

    wait_result = RunExecutionResult(
        checkpoint=SimpleNamespace(values={}),
        status="interrupted",
        committed=False,
    )
    monkeypatch.setattr(runner, "mark_run_terminal", mark_terminal)
    monkeypatch.setattr(runner, "stream_agent_execution", lambda **_kwargs: _ExecutionAsyncIter([wait_result]))

    await runner.process_agent_run({"job_try": 1}, run_obj.id)

    assert terminals and terminals[0][1] == "failed"
    assert "PostgreSQL interrupted" in terminals[0][2]


@pytest.mark.asyncio
async def test_read_run_token_usage_from_state_rejects_other_run(monkeypatch: pytest.MonkeyPatch):
    @asynccontextmanager
    async def fake_session_ctx():
        yield object()

    async def fake_get_agent_state_view(**kwargs):
        del kwargs
        return {
            "agent_state": {
                "token_usage": {
                    "current_run_id": "old-run",
                    "run": {"schema_version": 2, "models": {}, "total": {"total_tokens": 99}},
                }
            }
        }

    monkeypatch.setattr(worker_bootstrap.pg_manager, "get_async_session_context", fake_session_ctx)
    monkeypatch.setattr(runner, "get_agent_state_view", fake_get_agent_state_view)

    usage = await runner._read_run_token_usage_from_state(
        run_id="run-1",
        thread_id="thread-1",
        current_user=SimpleNamespace(uid="user-1"),
    )

    assert usage is None


@pytest.mark.asyncio
async def test_uncommitted_failure_marks_usage_unavailable_when_state_read_fails(monkeypatch: pytest.MonkeyPatch):
    terminal_calls: list[dict] = []

    async def fake_read_usage(**kwargs):
        del kwargs
        return None

    async def fake_mark_terminal(run_id: str, status: str, error_type=None, error_message=None, **kwargs):
        terminal_calls.append(
            {
                "run_id": run_id,
                "status": status,
                "error_type": error_type,
                "error_message": error_message,
                **kwargs,
            }
        )
        return runner.TerminalTransition(status=status, changed=True)

    async def fake_append_end_event(*args, **kwargs):
        del args, kwargs

    async def fake_get_run(_run_id: str):
        return None

    monkeypatch.setattr(runner, "_read_run_token_usage_from_state", fake_read_usage)
    monkeypatch.setattr(runner, "_get_run", fake_get_run)
    monkeypatch.setattr(runner, "mark_run_terminal", fake_mark_terminal)
    monkeypatch.setattr(runner, "publish_run_settlement", fake_append_end_event)

    await runner._settle_uncommitted_run(
        "run-1",
        "failed",
        thread_id="thread-1",
        current_user=SimpleNamespace(uid="user-1"),
        worker_id="worker-1:attempt-1",
    )

    assert terminal_calls[0]["token_usage"] == {"available": False}


@pytest.mark.asyncio
async def test_process_agent_run_non_retryable_error_marks_failed(monkeypatch: pytest.MonkeyPatch):
    run_obj = _build_run()
    _patch_common(monkeypatch, run_obj)

    terminal_statuses: list[str] = []
    events: list[str] = []

    async def fake_append_event(run_id: str, batch: list, **kwargs):
        del run_id, kwargs
        events.extend(batch)

    async def fake_mark_terminal(run_id: str, status: str, error_type=None, error_message=None, **kwargs):
        del run_id, kwargs
        terminal_statuses.append(status)
        return runner.TerminalTransition(status=status, changed=True)

    monkeypatch.setattr(event_writer, "append_run_stream_events", fake_append_event)
    monkeypatch.setattr(runner, "mark_run_terminal", fake_mark_terminal)
    monkeypatch.setattr(
        runner,
        "_consume_stream_with_cancel",
        lambda stream, run_ctx: _RaisingAsyncIter(RuntimeError("boom")),
    )

    await runner.process_agent_run({"job_try": 1}, "run-1")

    assert terminal_statuses == ["failed"]


@pytest.mark.asyncio
async def test_preflight_failure_after_lease_closes_context_and_writes_owned_terminal(
    monkeypatch: pytest.MonkeyPatch,
):
    run_obj = _build_run()
    _patch_common(monkeypatch, run_obj)
    closed: list[str] = []
    terminal_calls: list[dict] = []

    async def fail_input_load(_message_id):
        raise RuntimeError("preflight failed")

    async def fake_close(context):
        closed.append(context.worker_id)

    async def fake_mark_terminal(run_id: str, status: str, error_type=None, error_message=None, **kwargs):
        terminal_calls.append(
            {
                "run_id": run_id,
                "status": status,
                "error_type": error_type,
                "error_message": error_message,
                **kwargs,
            }
        )
        return runner.TerminalTransition(status=status, changed=True)

    monkeypatch.setattr(runner, "_load_run_input_messages", fail_input_load)
    monkeypatch.setattr(runner, "mark_run_terminal", fake_mark_terminal)
    monkeypatch.setattr(runner.RunContext, "close", fake_close)

    await runner.process_agent_run({"worker_id": "worker-preflight", "job_try": 1}, "run-1")

    assert terminal_calls[0]["status"] == "failed"
    assert terminal_calls[0]["error_type"] == "worker_error"
    assert terminal_calls[0]["worker_id"].startswith("worker-preflight:")
    assert closed == [terminal_calls[0]["worker_id"]]


@pytest.mark.asyncio
async def test_redis_event_failure_cannot_block_owned_completed_terminal(monkeypatch: pytest.MonkeyPatch):
    run_obj = _build_run()
    _patch_common(monkeypatch, run_obj)
    terminal_calls: list[dict] = []
    closed: list[str] = []

    async def fail_event(*args, **kwargs):
        del args, kwargs
        raise ConnectionError("redis unavailable")

    async def fake_mark_terminal(run_id: str, status: str, error_type=None, error_message=None, **kwargs):
        terminal_calls.append(
            {
                "run_id": run_id,
                "status": status,
                "error_type": error_type,
                "error_message": error_message,
                **kwargs,
            }
        )
        return runner.TerminalTransition(status=status, changed=True)

    async def fake_close(context):
        closed.append(context.worker_id)

    def fake_stream_agent_execution(**kwargs):
        del kwargs
        run_obj.status = "completed"
        return _ExecutionAsyncIter([_terminal_result()])

    monkeypatch.setattr(event_writer, "append_run_stream_events", fail_event)
    monkeypatch.setattr(runner, "mark_run_terminal", fake_mark_terminal)
    monkeypatch.setattr(runner, "release_run_lease_for_retry", AsyncMock(side_effect=AssertionError("no retry")))
    monkeypatch.setattr(runner.RunContext, "close", fake_close)
    monkeypatch.setattr(runner, "stream_agent_execution", fake_stream_agent_execution)

    await runner.process_agent_run({"worker_id": "worker-events", "job_try": 1}, "run-1")

    assert terminal_calls == []
    assert len(closed) == 1 and closed[0].startswith("worker-events:")


@pytest.mark.asyncio
async def test_durable_cancel_without_redis_signal_never_enters_agent_stream(monkeypatch: pytest.MonkeyPatch):
    run_obj = _build_run()
    run_obj.status = "cancel_requested"
    _patch_common(monkeypatch, run_obj)
    terminal_calls: list[dict] = []
    lifecycle: list[str] = []

    async def fake_mark_terminal(run_id: str, status: str, error_type=None, error_message=None, **kwargs):
        lifecycle.append("terminal")
        terminal_calls.append({"run_id": run_id, "status": status, **kwargs})
        run_obj.status = status
        return runner.TerminalTransition(status=status, changed=True)

    def forbidden_stream(**kwargs):
        del kwargs
        raise AssertionError("durably cancelled run must not execute")

    monkeypatch.setattr(runner, "mark_run_terminal", fake_mark_terminal)
    monkeypatch.setattr(runner, "stream_agent_execution", forbidden_stream)

    async def fake_release_sandbox(_run, _message):
        lifecycle.append("release")
        return True

    monkeypatch.setattr(runner, "_require_runtime_cleanup", fake_release_sandbox)

    await runner.process_agent_run({"worker_id": "worker-cancel", "job_try": 1}, "run-1")

    assert [call["status"] for call in terminal_calls] == ["cancelled"]
    assert terminal_calls[0]["worker_id"].startswith("worker-cancel:")
    assert lifecycle == ["terminal", "release"]


@pytest.mark.asyncio
async def test_infrastructure_cancel_releases_pending_and_propagates(monkeypatch: pytest.MonkeyPatch):
    run_obj = _build_run()
    _patch_common(monkeypatch, run_obj)
    released: list[tuple[str, str]] = []
    closed: list[str] = []

    async def release(run_id: str, worker_id: str) -> bool:
        released.append((run_id, worker_id))
        return True

    async def fake_close(context):
        closed.append(context.worker_id)

    monkeypatch.setattr(event_writer, "append_run_stream_events", AsyncMock())
    monkeypatch.setattr(runner, "mark_run_terminal", AsyncMock(side_effect=AssertionError("not user cancel")))
    monkeypatch.setattr(runner, "release_run_lease_for_retry", release)
    monkeypatch.setattr(runner.RunContext, "close", fake_close)
    monkeypatch.setattr(
        runner,
        "_consume_stream_with_cancel",
        lambda stream, context: _RaisingAsyncIter(asyncio.CancelledError("worker shutdown")),
    )

    with pytest.raises(asyncio.CancelledError, match="worker shutdown"):
        await runner.process_agent_run({"worker_id": "worker-shutdown", "job_try": 1}, "run-1")

    assert len(released) == 1
    assert released[0][0] == "run-1"
    assert released[0][1].startswith("worker-shutdown:")
    assert closed == [released[0][1]]


async def test_execution_timeout_fails_run_instead_of_releasing_for_retry(monkeypatch):
    """业务时限到期必须持久失败，不能当作 worker 退出重新排队。"""
    run = _build_run()
    _patch_common(monkeypatch, run)
    entered, closed = asyncio.Event(), asyncio.Event()

    async def blocked_stream(**_):
        """模拟已进入但不会自行结束的模型流。"""
        try:
            entered.set()
            await asyncio.Event().wait()
            yield b"unreachable"
        finally:
            closed.set()

    async def settle(run_id, status, **kwargs):
        """保存单测的业务结果，校验执行先完成关闭。"""
        assert run_id == run.id and entered.is_set() and closed.is_set()
        run.status = status
        run.error_type = kwargs["error_type"]
        return runner.TerminalTransition(status=status, changed=True)

    monkeypatch.setattr(runner, "RUN_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(runner, "stream_agent_execution", blocked_stream)
    monkeypatch.setattr(runner, "_settle_uncommitted_run", settle)
    monkeypatch.setattr(runner, "release_run_lease_for_retry", AsyncMock(side_effect=AssertionError("超时不释放为 pending")))
    await runner.process_agent_run({"worker_id": "timeout-worker", "job_try": 1}, run.id)
    assert (run.status, run.error_type) == ("failed", "execution_timeout")


@pytest.mark.asyncio
async def test_release_failure_does_not_mask_infrastructure_cancel(monkeypatch: pytest.MonkeyPatch):
    run_obj = _build_run()
    _patch_common(monkeypatch, run_obj)

    async def fail_release(_run_id: str, _worker_id: str) -> bool:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(event_writer, "append_run_stream_events", AsyncMock())
    monkeypatch.setattr(runner, "release_run_lease_for_retry", fail_release)
    monkeypatch.setattr(
        runner,
        "_consume_stream_with_cancel",
        lambda stream, context: _RaisingAsyncIter(asyncio.CancelledError("worker shutdown")),
    )

    with pytest.raises(asyncio.CancelledError, match="worker shutdown"):
        await runner.process_agent_run({"worker_id": "worker-shutdown", "job_try": 1}, "run-1")


@pytest.mark.asyncio
async def test_run_context_stream_checks_only_local_cancel_event(
    monkeypatch: pytest.MonkeyPatch,
):
    """模型事件循环不得把取消检查放大为逐事件 PostgreSQL 查询。"""
    run_context = runner.RunContext(run_id="run-1", worker_id="worker-1:attempt-1")
    durable_read = AsyncMock(side_effect=AssertionError("stream check must not query PostgreSQL"))
    monkeypatch.setattr(runner, "_is_cancel_requested", durable_read)

    assert await run_context.is_cancelled() is False
    run_context.cancel_event.set()
    assert await run_context.is_cancelled() is True
    durable_read.assert_not_awaited()


@pytest.mark.asyncio
async def test_durable_cancel_watcher_stops_execution_when_postgres_fact_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
):
    run_context = runner.RunContext(run_id="run-1", worker_id="worker-1:attempt-1")
    monkeypatch.setattr(runner, "_is_cancel_requested", AsyncMock(side_effect=RuntimeError("db unavailable")))

    await run_context._watch_durable_cancel()

    assert run_context.cancel_event.is_set()


@pytest.mark.asyncio
async def test_process_agent_run_retryable_error_retries_then_completes(monkeypatch: pytest.MonkeyPatch):
    run_obj = _build_run()
    _patch_common(monkeypatch, run_obj)

    terminal_statuses: list[str] = []
    events: list[dict] = []
    lifecycle: list[str] = []
    attempts = {"count": 0}

    async def fake_append_event(run_id: str, batch: list, **kwargs):
        del run_id, kwargs
        events.extend(batch)

    async def fake_mark_terminal(run_id: str, status: str, error_type=None, error_message=None, **kwargs):
        del run_id, kwargs
        terminal_statuses.append(status)
        return runner.TerminalTransition(status=status, changed=True)

    def fake_consume(stream, run_ctx):
        del stream, run_ctx
        attempts["count"] += 1
        if attempts["count"] == 1:
            return _RaisingAsyncIter(runner.RetryableRunError("temporary failure"))
        run_obj.status = "completed"
        return _ExecutionAsyncIter([_terminal_result()])

    monkeypatch.setattr(event_writer, "append_run_stream_events", fake_append_event)
    monkeypatch.setattr(runner, "mark_run_terminal", fake_mark_terminal)
    monkeypatch.setattr(runner, "_consume_stream_with_cancel", fake_consume)

    async def fake_release_lease(*_args, **_kwargs):
        lifecycle.append("lease-and-descendants")
        return True

    async def fake_release_runtime(*_args, **_kwargs):
        lifecycle.append("runtime")
        return True

    monkeypatch.setattr(runner, "release_run_lease_for_retry", fake_release_lease)
    monkeypatch.setattr(runner, "complete_run_runtime_cleanup", fake_release_runtime)

    with pytest.raises(runner.RetryableRunError) as retry:
        await runner.process_agent_run({"job_try": 1}, "run-1")

    assert isinstance(retry.value, RetryJob)
    assert terminal_statuses == []
    assert lifecycle == ["lease-and-descendants", "runtime"]

    await runner.process_agent_run({"job_try": 2}, "run-1")
    assert terminal_statuses == []


@pytest.mark.asyncio
async def test_uncommitted_failure_losing_to_cancellation_does_not_publish(monkeypatch: pytest.MonkeyPatch):
    events: list[tuple[str, dict]] = []

    async def fake_mark_terminal(run_id: str, status: str, error_type=None, error_message=None, **kwargs):
        del run_id, status, kwargs
        return runner.TerminalTransition(status="cancelled", changed=False)

    async def fake_append_event(run_id: str, batch: list, **kwargs):
        del run_id, kwargs
        events.extend(batch)

    monkeypatch.setattr(runner, "mark_run_terminal", fake_mark_terminal)
    monkeypatch.setattr(event_writer, "append_run_stream_events", fake_append_event)
    monkeypatch.setattr(runner, "_get_run", AsyncMock(return_value=None))
    monkeypatch.setattr(runner, "_read_run_token_usage_from_state", AsyncMock(return_value=None))

    transition = await runner._settle_uncommitted_run(
        "run-1",
        "failed",
        thread_id="thread-1",
        current_user=SimpleNamespace(uid="user-1"),
        worker_id="worker-1:attempt-1",
    )

    assert transition == runner.TerminalTransition(status="cancelled", changed=False)
    assert events == []


@pytest.mark.asyncio
async def test_process_member_run_uses_own_thread_and_shared_runtime(monkeypatch: pytest.MonkeyPatch):
    run_obj = _build_run()
    run_obj.run_type = "chat"
    run_obj.agent_slug = "worker"
    run_obj.thread_id = "child-thread"
    run_obj.runtime_scope_id = "child-thread"
    run_obj.created_by_run_id = "parent-run"
    run_obj.input_payload = {
        "model_spec": "provider:model",
        "runtime": {
            "parent_thread_id": "parent-thread",
        },
    }
    _patch_common(monkeypatch, run_obj)

    from test.unit.support.agent_context_fixtures import prepared_execution

    prepared = prepared_execution(
        model="prepared:model",
        tool_approval_mode="always_trust",
        runtime_scope_id="prepared-root",
        workdir_relative_path="projects/prepared",
        workdir_path="/home/user/workspace/projects/prepared",
    )
    monkeypatch.setattr(runner, "prepare_and_record_run_execution", AsyncMock(return_value=prepared))
    captured: dict[str, object] = {}
    terminal_statuses: list[str] = []

    async def fake_append_event(run_id: str, events: list, **kwargs):
        del run_id, events, kwargs

    async def fake_mark_terminal(run_id: str, status: str, error_type=None, error_message=None, **kwargs):
        del run_id, kwargs
        terminal_statuses.append(status)
        return runner.TerminalTransition(status=status, changed=True)

    def fake_stream_agent_execution(**kwargs):
        captured.update(kwargs)
        run_obj.status = "completed"
        return _ExecutionAsyncIter([_terminal_result(thread_id="child-thread")])

    monkeypatch.setattr(event_writer, "append_run_stream_events", fake_append_event)
    monkeypatch.setattr(runner, "mark_run_terminal", fake_mark_terminal)
    monkeypatch.setattr(runner, "stream_agent_execution", fake_stream_agent_execution)

    await runner.process_agent_run({"job_try": 1}, "run-1")

    meta = captured["meta"]
    assert meta["run_type"] == "chat"
    assert "parent_thread_id" not in meta
    assert meta["runtime_scope_id"] == "prepared-root"
    assert meta["workdir_relative_path"] == "projects/prepared"
    assert meta["workdir_path"] == "/home/user/workspace/projects/prepared"
    assert meta["model_spec"] == "prepared:model"
    assert meta["tool_approval_mode"] == "always_trust"
    assert captured["agent_slug"] == "worker"
    assert captured["thread_id"] == "child-thread"
    assert captured["input_messages"][0].content == "hello"
    assert captured["input_messages"][0].langchain_message.content == "hello"
    assert "image_content" not in captured
    assert terminal_statuses == []


@pytest.mark.asyncio
async def test_process_agent_run_rejects_unknown_run_type(monkeypatch: pytest.MonkeyPatch):
    run_obj = _build_run()
    run_obj.run_type = "unknown"
    _patch_common(monkeypatch, run_obj)

    terminal_errors: list[dict] = []

    async def fake_mark_terminal(run_id: str, status: str, error_type=None, error_message=None, **kwargs):
        terminal_errors.append(
            {
                "run_id": run_id,
                "status": status,
                "error_type": error_type,
                "error_message": error_message,
            }
        )
        return runner.TerminalTransition(status=status, changed=True)

    def fail_stream_agent_execution(**kwargs):
        del kwargs
        raise AssertionError("unknown run_type must not enter chat stream")

    monkeypatch.setattr(runner, "mark_run_terminal", fake_mark_terminal)
    monkeypatch.setattr(runner, "stream_agent_execution", fail_stream_agent_execution)

    await runner.process_agent_run({"job_try": 1}, "run-1")

    assert terminal_errors == [
        {
            "run_id": "run-1",
            "status": "failed",
            "error_type": "invalid_run_type",
            "error_message": "不支持的 run_type: unknown",
        }
    ]


@pytest.mark.asyncio
async def test_process_agent_run_rejects_invalid_raw_input_message(monkeypatch: pytest.MonkeyPatch):
    run_obj = _build_run()
    _patch_common(monkeypatch, run_obj)

    terminal_errors: list[dict] = []

    async def fake_load_run_input_messages(run):
        assert run.input_message_id == 10
        return [
            SimpleNamespace(
                id=10,
                source_input_id="input-1",
                content="hello",
                image_content=None,
                extra_metadata={"raw_message": {"type": "human", "content": object()}},
            )
        ]

    async def fake_mark_terminal(run_id: str, status: str, error_type=None, error_message=None, **kwargs):
        terminal_errors.append(
            {
                "run_id": run_id,
                "status": status,
                "error_type": error_type,
                "error_message": error_message,
            }
        )
        return runner.TerminalTransition(status=status, changed=True)

    def fail_stream_agent_execution(**kwargs):
        del kwargs
        raise AssertionError("invalid input message must not enter chat stream")

    monkeypatch.setattr(runner, "_load_run_input_messages", fake_load_run_input_messages)
    monkeypatch.setattr(runner, "mark_run_terminal", fake_mark_terminal)
    monkeypatch.setattr(runner, "stream_agent_execution", fail_stream_agent_execution)

    await runner.process_agent_run({"job_try": 1}, "run-1")

    assert terminal_errors == [
        {
            "run_id": "run-1",
            "status": "failed",
            "error_type": "invalid_input_message",
            "error_message": "invalid raw_message for chat input message",
        }
    ]


@pytest.mark.asyncio
async def test_timing_persistence_failure_does_not_fail_agent_execution(monkeypatch: pytest.MonkeyPatch):
    """执行计时只用于观测；写回失败不改变已经完成的 Agent 执行。"""

    class FailingRepository:
        def __init__(self, _db):
            pass

        async def record_prepared(self, *_args, **_kwargs):
            raise RuntimeError("timing storage unavailable")

    @asynccontextmanager
    async def fake_session():
        yield object()

    monkeypatch.setattr(worker_bootstrap.pg_manager, "get_async_session_context", fake_session)
    monkeypatch.setattr(runner, "AgentRunRepository", FailingRepository)

    await runner._record_run_timing_best_effort("run-1", "worker-1:token", "prepared")


def test_run_owner_token_has_stable_worker_prefix_and_unique_attempt_suffix():
    ctx = {"worker_id": "worker-stable"}

    first = runner._run_owner_token(ctx)
    second = runner._run_owner_token(ctx)

    assert first.startswith("worker-stable:")
    assert second.startswith("worker-stable:")
    assert first != second


@pytest.mark.asyncio
async def test_cancel_intent_keeps_heartbeat_until_execution_finishes(monkeypatch):
    """取消后的工具收尾仍续租，避免被失联回收提前释放名额。"""
    monkeypatch.setattr(runner, "RUN_HEARTBEAT_SECONDS", 0)
    renew = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(runner, "renew_run_lease", renew)
    monkeypatch.setattr(runner, "run_attempt_finished", AsyncMock(return_value=True))
    context = runner.RunContext(run_id="run-1", worker_id="worker-1")
    context.cancel_event.set()
    await context._heartbeat_lease()
    assert renew.await_count == 2
    assert not context.lease_lost


@pytest.mark.asyncio
async def test_run_context_stops_when_heartbeat_cannot_renew(monkeypatch: pytest.MonkeyPatch):
    renew = AsyncMock(return_value=False)
    monkeypatch.setattr(runner, "RUN_HEARTBEAT_SECONDS", 0)
    monkeypatch.setattr(runner, "renew_run_lease", renew)
    monkeypatch.setattr(runner, "run_attempt_finished", AsyncMock(return_value=False))
    run_ctx = runner.RunContext(run_id="run-1", worker_id="worker-1:attempt-1")

    await run_ctx._heartbeat_lease()

    renew.assert_awaited_once_with("run-1", "worker-1:attempt-1")
    assert run_ctx.lease_lost is True
    assert run_ctx.cancel_event.is_set()


@pytest.mark.asyncio
async def test_run_context_fails_closed_when_terminal_attempt_check_fails(monkeypatch: pytest.MonkeyPatch):
    """无法确认本 attempt 的终态时，继续按丢失 ownership 停止执行。"""
    monkeypatch.setattr(runner, "RUN_HEARTBEAT_SECONDS", 0)
    monkeypatch.setattr(runner, "renew_run_lease", AsyncMock(return_value=False))
    monkeypatch.setattr(runner, "run_attempt_finished", AsyncMock(side_effect=RuntimeError("database unavailable")))
    context = runner.RunContext(run_id="run-1", worker_id="worker-1:attempt-1")

    await context._heartbeat_lease()

    assert context.lease_lost and context.cancel_event.is_set()


@pytest.mark.asyncio
async def test_manifest_persist_failure_fails_run_before_execution(monkeypatch: pytest.MonkeyPatch):
    """manifest 固化失败时 Run 显式失败，且不得进入执行流。"""
    run_obj = _build_run()
    _patch_common(monkeypatch, run_obj)
    terminal_calls: list[dict] = []
    stream_called = asyncio.Event()

    async def fake_persist_manifest(**kwargs):
        del kwargs
        raise RuntimeError("manifest db unavailable")

    async def fake_mark_terminal(run_id: str, status: str, error_type=None, error_message=None, **kwargs):
        terminal_calls.append(
            {
                "run_id": run_id,
                "status": status,
                "error_type": error_type,
                "error_message": error_message,
                **kwargs,
            }
        )
        return runner.TerminalTransition(status=status, changed=True)

    def fake_stream_agent_execution(**kwargs):
        del kwargs
        stream_called.set()
        return _ExecutionAsyncIter([])

    monkeypatch.setattr(runner, "prepare_and_record_run_execution", fake_persist_manifest)
    monkeypatch.setattr(runner, "mark_run_terminal", fake_mark_terminal)
    monkeypatch.setattr(runner, "stream_agent_execution", fake_stream_agent_execution)

    await runner.process_agent_run({"job_try": 1}, "run-1")

    assert not stream_called.is_set()
    assert len(terminal_calls) == 1
    assert terminal_calls[0]["status"] == "failed"
    assert terminal_calls[0]["error_type"] == "manifest_persist_failed"
    assert "执行未开始" in terminal_calls[0]["error_message"]


@pytest.mark.asyncio
async def test_cancel_during_manifest_preparation_settles_without_waiting_for_lease(monkeypatch):
    """配置准备期间取消不能被误判为固化失败并留待 lease 超时。"""
    run = _build_run()
    _patch_common(monkeypatch, run)
    cancelled = False

    async def persist(**kwargs):
        """模拟取消先提交，随后 manifest 写入因状态改变失败。"""
        nonlocal cancelled
        cancelled = True
        raise RuntimeError("manifest requires running")

    async def is_cancelled(*args):
        return cancelled

    finish = AsyncMock(return_value=runner.TerminalTransition(status="cancelled", changed=True))
    monkeypatch.setattr(runner, "prepare_and_record_run_execution", persist)
    monkeypatch.setattr(runner, "_is_cancel_requested", is_cancelled)
    monkeypatch.setattr(runner, "_confirmed_user_cancel", is_cancelled)
    monkeypatch.setattr(runner, "_settle_uncommitted_run", finish)
    monkeypatch.setattr(runner, "mark_run_terminal", AsyncMock(side_effect=AssertionError("不能转为 failed")))
    monkeypatch.setattr(runner, "stream_agent_execution", lambda **kwargs: pytest.fail("取消后不能开始执行"))
    await runner.process_agent_run({"job_try": 1}, run.id)
    finish.assert_awaited_once()
    assert finish.call_args.kwargs["run_id"] == run.id


@pytest.mark.parametrize("status", ["completed", "interrupted", "failed"])
async def test_execution_releases_own_runtime_before_settlement(monkeypatch, status):
    """执行结果先持久终态，再一次清理当前 Run，最后发布。"""
    run = _build_run()
    _patch_common(monkeypatch, run)
    order = []

    async def stream():
        if status == "failed":
            yield RunExecutionResult(checkpoint=None, status="failed", committed=False)
        else:
            run.status = status
            yield _terminal_result(status)

    async def release(actual, _message):
        assert actual is run
        order.append("release")

    async def publish(run_id, actual_status, **_kwargs):
        assert run_id == run.id and run.status == actual_status == status
        order.append("published")

    monkeypatch.setattr(runner, "stream_agent_execution", lambda **kw: stream())
    monkeypatch.setattr(runner, "_require_runtime_cleanup", release)
    monkeypatch.setattr(runner, "publish_run_settlement", publish)

    async def commit(_run_id, target, **_kwargs):
        """只有未提交失败需要 worker 形成终态，完成结果不得二次结算。"""
        assert status == "failed" and target == status
        run.status = target
        order.append("commit")
        return runner.TerminalTransition(status=target, changed=True)

    monkeypatch.setattr(runner, "mark_run_terminal", commit)
    await runner.process_agent_run({"job_try": 1}, run.id)
    assert order == (["commit"] if status == "failed" else []) + ["release", "published"]


@pytest.mark.parametrize("container", ["metadata", "payload", "yuxi"])
async def test_worker_rejects_unrouted_public_output(monkeypatch, container):
    """嵌套业务 payload 不能代替明确的执行归属。"""
    run = _build_run()
    _patch_common(monkeypatch, run)
    terminal = AsyncMock(return_value=runner.TerminalTransition(status="failed", changed=True))
    output = {
        "type": "agent.session.turn.output_text.delta",
        "delta": "foreign",
        container: {"session_id": run.thread_id, "turn_id": run.turn_id, "run_id": run.id},
    }
    monkeypatch.setattr(runner, "mark_run_terminal", terminal)
    monkeypatch.setattr(runner, "stream_agent_execution", lambda **kw: _ExecutionAsyncIter([output]))
    await runner.process_agent_run({"job_try": 1}, run.id)
    assert terminal.await_args.args[:2] == (run.id, "failed")
    assert "明确归属" in terminal.await_args.kwargs["error_message"]


async def test_worker_only_publishes_valid_events_and_never_settles_usage_from_them(monkeypatch):
    """Run 使用量由业务事务结算，流中的其他 Run 用量不能成为最终事实。"""
    run = _build_run()
    _patch_common(monkeypatch, run)
    public = {
        "type": "yuxi.session.turn.state",
        "event_id": "e",
        "session_id": run.thread_id,
        "turn_id": run.turn_id,
        "yuxi": {"run_id": run.id},
        "agent_state": {"token_usage": {"current_run_id": "other", "run": {"total": 505}}},
    }

    async def stream():
        yield public
        run.status = "completed"
        yield _terminal_result()

    published = []

    async def append(run_id, events):
        published.extend(events)

    monkeypatch.setattr(runner, "stream_agent_execution", lambda **kw: stream())
    monkeypatch.setattr(event_writer, "append_run_stream_events", append)
    monkeypatch.setattr(runner, "mark_run_terminal", AsyncMock(side_effect=AssertionError("already committed")))
    await runner.process_agent_run({"job_try": 1}, run.id)
    assert published == [public]


async def test_nonretryable_output_conflict_after_user_cancel_settles_cancelled(monkeypatch):
    """取消已提交时，普通输出 owner 冲突也必须收敛取消，不能转失败或留到 lease 过期。"""
    run = _build_run()
    _patch_common(monkeypatch, run)
    cancelled = False

    async def stream():
        """模拟模型释放时输出提交撞上已提交取消。"""
        nonlocal cancelled
        cancelled = True
        raise ValueError("只有 running owner 可以持久化输出")
        yield

    async def is_cancelled(*args):
        """直接表达本测试的 durable 用户取消状态。"""
        return cancelled

    finish = AsyncMock(return_value=runner.TerminalTransition(status="cancelled", changed=True))
    monkeypatch.setattr(runner, "stream_agent_execution", lambda **kwargs: stream())
    monkeypatch.setattr(runner, "_confirmed_user_cancel", is_cancelled)
    monkeypatch.setattr(runner, "_settle_uncommitted_run", finish)
    await runner.process_agent_run({"job_try": 1}, run.id)
    finish.assert_awaited_once()


@pytest.mark.parametrize("cleanup_pending", [False, True])
async def test_terminal_redelivery_finishes_after_cleanup_and_conditional_publication(monkeypatch, cleanup_pending):
    """重投终态仅在补偿清理时重发，并在新快照上先派发后导出观察。"""
    run = _build_run()
    _patch_common(monkeypatch, run)
    run.status = "completed"
    run.runtime_cleanup_pending = cleanup_pending
    events = []
    loaded = 0

    async def get_run(_run_id):
        """清理完成后的读取返回独立新快照，不复用旧 cleanup 标记。"""
        nonlocal loaded
        loaded += 1
        if loaded > 1:
            return SimpleNamespace(**{**vars(run), "runtime_cleanup_pending": False})
        return run

    async def cleanup(_run, _message):
        """保留传入对象旧标记，用新快照证明派发依据。"""
        events.append("cleanup")

    async def publish(*_args, **_kwargs):
        """记录终态发布位置。"""
        events.append("publish")

    async def dispatch(**_kwargs):
        """记录下一输入派发位置。"""
        events.append("dispatch")

    async def trace(_turn_id):
        """记录观察导出位置。"""
        events.append("trace")

    monkeypatch.setattr(runner, "_get_run", get_run)
    monkeypatch.setattr(runner, "_require_runtime_cleanup", cleanup)
    monkeypatch.setattr(runner, "publish_run_settlement", publish)
    monkeypatch.setattr(lifecycle, "dispatch_next_input", dispatch)
    monkeypatch.setattr(lifecycle, "finish_turn_observation_if_terminal", trace)
    await runner.process_agent_run({"job_try": 1}, run.id)
    assert events == (["cleanup", "publish"] if cleanup_pending else []) + ["dispatch", "trace"]
    assert loaded == (2 if cleanup_pending else 1)


@pytest.mark.parametrize(
    ("fault", "error_type", "message", "expected_steps"),
    [
        ("payload", "invalid_input_payload", "run input_payload 必须是对象", []),
        ("runtime", "invalid_runtime_payload", "run input_payload.runtime 必须是对象", []),
        ("messages", "input_message_not_found", "运行任务缺少输入消息", ["messages"]),
        ("metadata", "invalid_input_metadata", "输入消息 metadata 必须是对象", ["messages"]),
        ("run_type", "invalid_run_type", "不支持的 run_type: unknown", ["messages"]),
        ("user", "user_not_found", "user user-1 not found", ["messages", "user"]),
        ("workdir", "invalid_runtime_scope", "Workdir authorization rejected", ["messages", "user", "workdir"]),
        ("resume", "resume_input_not_found", "resume run 缺少 resume 输入", ["messages", "user", "workdir"]),
        ("raw", "invalid_input_message", "invalid raw_message for chat input message", ["messages", "user", "workdir"]),
        (
            "manifest",
            "manifest_persist_failed",
            "运行清单固化失败，执行未开始：manifest rejected",
            ["messages", "user", "workdir", "heartbeat", "title", "manifest"],
        ),
    ],
)
async def test_admission_rejections_preserve_order_and_business_reason(monkeypatch, fault, error_type, message, expected_steps):
    """相邻后续条件也非法时仍保留原拒绝优先序，任何拒绝都不进入执行。"""
    run = _build_run()
    _patch_common(monkeypatch, run)
    steps, settled, settled_usage = [], [], []
    existing_usage = {"available": True, "total": {"total_tokens": 23}}
    metadata = {"raw_message": {"type": "human", "content": "hello"}}
    input_message = SimpleNamespace(id=10, source_input_id="input-1", content="hello", image_content=None, extra_metadata=metadata)
    if fault == "payload":
        run.input_payload = []
    if fault == "runtime":
        run.input_payload["runtime"] = "bad runtime"
    if fault in {"messages", "metadata", "run_type"}:
        run.run_type = "unknown"
    if fault == "metadata":
        input_message.extra_metadata = []
    if fault in {"workdir", "resume"}:
        run.run_type = "resume"
    if fault == "raw":
        input_message.extra_metadata = {"raw_message": {"type": "human", "content": object()}}

    async def load_messages(_run):
        """记录持久输入读取边界。"""
        steps.append("messages")
        return [] if fault in {"runtime", "messages"} else [input_message]

    async def load_user(_uid):
        """记录用户读取，供相邻拒绝检查比较顺序。"""
        steps.append("user")
        return None if fault in {"run_type", "user"} else SimpleNamespace(uid="user-1")

    async def authorize(_run):
        """表达真实授权边界的失败，解析 resume 之前必须先授权。"""
        steps.append("workdir")
        if fault in {"user", "workdir"}:
            raise RuntimeError("Workdir authorization rejected")
        return SimpleNamespace(workdir_path="projects/test")

    async def start(_context):
        """记录心跳在 manifest 之前启动。"""
        steps.append("heartbeat")

    async def prepare(**_kwargs):
        """后续准备故意失败，前置错误必须先被拒绝。"""
        steps.append("manifest")
        raise RuntimeError("manifest rejected")

    async def terminal(_run_id, status, **kwargs):
        """保存结算的业务结果，供单测断言错误与顺序。"""
        settled.append((status, kwargs["error_type"], kwargs["error_message"]))
        settled_usage.append(kwargs["token_usage"])
        run.status = status
        return runner.TerminalTransition(status=status, changed=True)

    monkeypatch.setattr(runner, "_read_run_token_usage_from_state", AsyncMock(return_value=existing_usage))
    monkeypatch.setattr(runner, "_load_run_input_messages", load_messages)
    monkeypatch.setattr(runner, "_load_user", load_user)
    monkeypatch.setattr(runner, "_validate_run_workdir_binding", authorize)
    monkeypatch.setattr(runner.RunContext, "start", start)
    monkeypatch.setattr(runner, "start_session_title", lambda **_kwargs: steps.append("title"))
    monkeypatch.setattr(runner, "prepare_and_record_run_execution", prepare)
    monkeypatch.setattr(runner, "mark_run_terminal", terminal)
    monkeypatch.setattr(runner, "stream_agent_execution", lambda **_kwargs: pytest.fail("准入拒绝后不能进入执行"))
    await runner.process_agent_run({"job_try": 1}, run.id)
    assert settled == [("failed", error_type, message)]
    assert steps == expected_steps
    assert settled_usage == [existing_usage if fault in {"workdir", "resume", "raw", "manifest"} else {"available": False}]


async def test_admission_settlement_failure_keeps_outer_retry_policy(monkeypatch):
    """共享拒绝出口自身失败仍进入既有外层基础设施重试。"""
    run = _build_run()
    _patch_common(monkeypatch, run)
    run.input_payload = []
    settle = AsyncMock(side_effect=ConnectionError("settlement database unavailable"))
    release = AsyncMock(return_value=True)
    monkeypatch.setattr(runner, "_settle_uncommitted_run", settle)
    monkeypatch.setattr(runner, "release_run_lease_for_retry", release)
    with pytest.raises(runner.RetryableRunError, match="settlement database unavailable"):
        await runner.process_agent_run({"job_try": 1}, run.id)
    assert run.status == "pending"
    release.assert_awaited_once()
