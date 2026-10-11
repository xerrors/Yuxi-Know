"""统一记录器的混合生命周期、提交边界与规整事件契约。"""

from contextlib import asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

import yuxi.modules.agents.services.message_recorder as service
from yuxi.modules.agents.services.message_recorder import RunMessageRecorder
from yuxi.modules.agents.services.openai_events import OpenAIEventAdapter


@pytest.fixture
def recorded_messages(monkeypatch):
    """以事务副本模拟提交后的消息事实，不替代 PostgreSQL 约束验证。"""
    committed = {}

    @asynccontextmanager
    async def session():
        pending = deepcopy(committed)
        yield pending
        committed.clear()
        committed.update(pending)

    class ModelRepository:
        """保存模型聚合结果，供提交后回读。"""

        def __init__(self, db):
            """借用当前事务副本。"""
            self.db = db

        async def start(self, **kwargs):
            """创建模型开始事实，重复开始保持原值。"""
            key = ("model", kwargs["operation_id"])
            created = key not in self.db
            self.db.setdefault(key, {**kwargs, "execution_status": "running"})
            return SimpleNamespace(id=1), created

        async def finish(self, **kwargs):
            """保存模型终态与完整聚合内容。"""
            self.db[("model", kwargs["operation_id"])].update(kwargs, execution_status="completed")

    class ToolRepository:
        """保存工具开始与完整结果，供公开投影独立回读。"""

        def __init__(self, db):
            """借用当前事务副本。"""
            self.db = db

        async def start(self, **kwargs):
            """创建工具开始事实，重复开始保持原值。"""
            key = ("tool", kwargs["tool_call_id"])
            created = key not in self.db
            self.db.setdefault(key, {**kwargs, "execution_status": "running"})
            return SimpleNamespace(id=2), created

        async def complete(self, **kwargs):
            """保存工具输出与完成状态。"""
            self.db[("tool", kwargs["tool_call_id"])].update(kwargs, execution_status="completed")

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session)
    monkeypatch.setattr(service, "ModelMessageAuditRepository", ModelRepository)
    monkeypatch.setattr(service, "ToolMessageAuditRepository", ToolRepository)
    return committed


def native(seq, data, *, method="messages", namespace=None, model_id="model"):
    """构造固定原生事件，不从生产实现生成预期结果。"""
    return {
        "method": method,
        "seq": seq,
        "params": {
            "timestamp": 1_777_000_123_456 + seq,
            "namespace": namespace or [],
            "data": (data, {"run_id": model_id}) if method == "messages" else data,
        },
    }


@pytest.mark.asyncio
async def test_same_recorder_keeps_interleaved_model_and_tool_states_separate(monkeypatch, recorded_messages):
    """交错模型来源与同名工具身份保持各自内容、usage 和单调耗时。"""
    clock = iter([100.0, 100.1, 100.2, 100.3, 100.4, 100.5])
    monkeypatch.setattr(service, "monotonic", lambda: next(clock))
    recorder = RunMessageRecorder(run_id="run", thread_id="thread", worker_id="worker")
    events = [
        native(0, {"event": "message-start", "id": "shared"}, namespace=["first"]),
        native(1, {"event": "message-start", "id": "second"}, namespace=["second"]),
        native(
            2,
            {"event": "content-block-delta", "delta": {"fields": {"type": "text-delta", "text": "一"}}},
            namespace=["first"],
        ),
        native(3, {"event": "content-block-delta", "delta": {"type": "text-delta", "text": "续"}}, namespace=["first"]),
        native(4, {"event": "content-block-delta", "delta": {"type": "text-delta", "text": "二"}}, namespace=["second"]),
        native(5, {"event": "message-finish", "usage": {"input_tokens": 5}}, namespace=["first"]),
        native(
            6,
            {"event": "tool-started", "tool_call_id": "shared", "tool_name": "search", "input": {"q": "实际输入"}},
            method="tools",
        ),
        native(7, {"event": "message-finish", "usage": {"output_tokens": 3}}, namespace=["second"]),
        native(8, {"event": "tool-finished", "tool_call_id": "shared", "output": "工具结果"}, method="tools"),
    ]
    for event in events:
        await recorder.consume(event)

    first, second, tool = (recorded_messages[key] for key in [("model", "shared"), ("model", "second"), ("tool", "shared")])
    assert first["content"] == "一续" and first["usage"] == {"input_tokens": 5}
    assert second["content"] == "二" and second["usage"] == {"output_tokens": 3}
    assert tool["content"] == "工具结果" and tool["tool_input"] == {"q": "实际输入"}
    assert [row["duration_ms"] for row in (first, second, tool)] == [200, 300, 200]
    assert [row["sequence"] for row in (first, second, tool)] == [0, 1, 6]
    for row in (first, second, tool):
        assert row["run_id"] == "run" and row["thread_id"] == "thread" and row["worker_id"] == "worker"
        assert row["execution_status"] == "completed"


@pytest.mark.parametrize("kind", ["model", "tool"])
@pytest.mark.asyncio
async def test_duplicate_start_preserves_collected_state_and_monotonic_clock(monkeypatch, recorded_messages, kind):
    """重复模型或工具开始事件都不清空聚合值，也不重置单调时钟。"""
    ticks = [100.0, 100.1, 100.4] if kind == "model" else [100.0, 100.1, 100.25]
    clock = iter(ticks)
    monkeypatch.setattr(service, "monotonic", lambda: next(clock))
    recorder = RunMessageRecorder(run_id="run", thread_id="thread", worker_id="worker")

    if kind == "model":
        metadata = {"run_id": "model-run", "stream_event": {"seq": 1, "timestamp": 1_777_000_123_456}}
        start = {"event": "message-start", "role": "ai", "id": "model-message"}
        await recorder.consume(_model_native_event(start, metadata))
        await recorder.consume(
            _model_native_event(
                {"event": "content-block-delta", "delta": {"type": "text-delta", "text": "before"}},
                metadata,
            )
        )
        await recorder.consume(_model_native_event(start, metadata))
        await recorder.consume(
            _model_native_event(
                {"event": "content-block-delta", "delta": {"type": "text-delta", "text": " after"}},
                metadata,
            )
        )
        await recorder.consume(
            _model_native_event(
                {"event": "message-finish", "usage": {}},
                {"run_id": "model-run", "stream_event": {"seq": 2, "timestamp": 1_777_000_123_789}},
            )
        )
        message = recorded_messages[("model", "model-message")]
        assert message["content"] == "before after"
        assert message["duration_ms"] == 400
        return

    start = native(
        1,
        {"event": "tool-started", "tool_call_id": "call", "tool_name": "search", "input": {}},
        method="tools",
    )
    await recorder.consume(start)
    await recorder.consume(start)
    await recorder.consume(
        native(
            2,
            {"event": "tool-finished", "tool_call_id": "call", "output": {"type": "tool", "content": "done", "status": "success"}},
            method="tools",
        )
    )
    tool = recorded_messages[("tool", "call")]
    assert tool["tool_input"] == {}
    assert tool["duration_ms"] == 250


@pytest.mark.asyncio
async def test_command_result_is_committed_once_before_public_projection(monkeypatch, recorded_messages):
    """记录器提交同一结果后才返回事件，公开适配失败也保留已提交工具事实。"""
    recorder = RunMessageRecorder(run_id="run", thread_id="thread", worker_id="worker")
    await recorder.consume(native(0, {"event": "tool-started", "tool_call_id": "call", "tool_name": "search", "input": {}}, method="tools"))
    command = Command(
        update={
            "messages": [
                ToolMessage(content="相邻结果", tool_call_id="other"),
                ToolMessage(content="目标结果", tool_call_id="call"),
            ]
        }
    )
    source = native(1, {"event": "tool-finished", "tool_call_id": "call", "output": command}, method="tools", namespace=["tools"])
    extract = service.tool_event_output
    extractions = []

    def extract_once(data):
        """只监测重复规整，最终事实另由结果回读证明。"""
        extractions.append(data["tool_call_id"])
        return extract(data)

    monkeypatch.setattr(service, "tool_event_output", extract_once)
    normalized = await recorder.consume(source)
    output = normalized["params"]["data"]["output"]
    assert source["params"]["data"]["output"] is command
    assert source["seq"] == normalized["seq"] == 1
    assert normalized["params"]["timestamp"] == source["params"]["timestamp"]
    assert normalized["params"]["namespace"] == ["tools"]
    assert output["tool_call_id"] == "call" and output["content"] == "目标结果"
    assert recorded_messages[("tool", "call")]["output"] == output
    assert recorded_messages[("tool", "call")]["execution_status"] == "completed"

    adapter = OpenAIEventAdapter(run_id="run", turn_id="turn", thread_id="thread", worker_id="worker")
    adapter.calls["call"] = ("model", "call:call", {"id": "declared-call", "yuxi": {"output_index": 0}})

    async def save_item(operation, role, key, item, content_index=None):
        """公开结果只能使用已经提交的工具输出。"""
        assert recorded_messages[("tool", "call")]["output"]["content"] == item.get("output", "目标结果")
        return {**item, "id": f"{operation}:{key}", "yuxi": {"output_index": 1}}

    monkeypatch.setattr(adapter, "_save", save_item)
    public = await adapter.consume(normalized)
    assert public[-1]["item"]["output"] == "目标结果"
    assert public[-1]["item"]["call_id"] == "call"
    assert extractions == ["call"]

    async def reject_public(*args, **kwargs):
        """模拟公开快照拒绝写入。"""
        raise ValueError("public rejected")

    monkeypatch.setattr(adapter, "_save", reject_public)
    with pytest.raises(ValueError, match="public rejected"):
        await adapter.consume(normalized)
    assert recorded_messages[("tool", "call")]["content"] == "目标结果"
    assert recorded_messages[("tool", "call")]["execution_status"] == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,data",
    [
        ("values", {}),
        ("custom", {"event": "other"}),
        ("tools", {"event": "tool-progress"}),
        ("messages", {"event": "message-finish"}),
    ],
)
async def test_non_lifecycle_events_do_not_open_transactions(monkeypatch, method, data):
    """非持久化边界与无开始事实的模型结束不增加事务。"""

    def unexpected_session():
        """任何无关数据库访问直接暴露目标缺陷。"""
        raise AssertionError("unexpected transaction")

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", unexpected_session)
    event = native(0, data, method=method)
    recorder = RunMessageRecorder(run_id="run", thread_id="thread", worker_id="worker")
    assert await recorder.consume(event) is event


@pytest.mark.asyncio
async def test_foreign_thread_does_not_create_model_fact(recorded_messages):
    """记录入口只接受当前 Thread 的模型来源。"""
    event = native(0, {"event": "message-start", "id": "foreign"})
    event["params"]["data"][1]["thread_id"] = "other"
    recorder = RunMessageRecorder(run_id="run", thread_id="thread", worker_id="worker")
    assert await recorder.consume(event) is event
    assert recorded_messages == {}


def _model_native_event(message, metadata):
    """把明确 fixture 来源放入原生 ProtocolEvent 的固定位置。"""
    source = metadata.get("stream_event", {})
    return {
        "method": "messages",
        "seq": source.get("seq"),
        "params": {
            "namespace": source.get("namespace", []),
            "timestamp": source.get("timestamp"),
            "data": (message, {key: value for key, value in metadata.items() if key != "stream_event"}),
        },
    }


class _FakeDb:
    pass


@pytest.mark.asyncio
async def test_collector_projects_real_v3_message_lifecycle(monkeypatch):
    """真实 v3 start/delta/finish 形状必须保留来源键、顺序、时间和 usage。"""
    db = _FakeDb()
    calls: list[tuple[str, dict]] = []

    @asynccontextmanager
    async def session_context():
        yield db

    class FakeRepository:
        def __init__(self, _db):
            pass

        async def start(self, **kwargs):
            calls.append(("start", kwargs))
            return SimpleNamespace(id=1), True

        async def finish(self, **kwargs):
            calls.append(("finish", kwargs))
            return SimpleNamespace(id=1)

    monotonic_values = iter([100.0, 100.321])
    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(service, "ModelMessageAuditRepository", FakeRepository)
    monkeypatch.setattr(service, "monotonic", lambda: next(monotonic_values))

    collector = RunMessageRecorder(
        run_id="run-1",
        thread_id="thread-1",
        worker_id="worker-1",
    )
    metadata = {
        "run_id": "langchain-model-run-1",
        "stream_event": {
            "method": "messages",
            "namespace": ["model:abc"],
            "seq": 7,
            "timestamp": 1_777_000_123_456,
        },
    }
    await collector.consume(
        _model_native_event(
            {
                "event": "message-start",
                "role": "ai",
                "id": "lc_run--model-message-1",
                "metadata": {"provider": "openai"},
            },
            metadata,
        )
    )
    await collector.consume(
        _model_native_event(
            {
                "event": "content-block-delta",
                "index": 0,
                "delta": {"type": "text-delta", "text": "hello"},
            },
            metadata,
        )
    )
    await collector.consume(
        _model_native_event(
            {
                "event": "content-block-finish",
                "index": 0,
                "content": {"type": "text", "text": "hello"},
            },
            metadata,
        )
    )
    finish_metadata = {
        **metadata,
        "stream_event": {**metadata["stream_event"], "seq": 8, "timestamp": 1_777_000_123_789},
    }
    await collector.consume(
        _model_native_event(
            {
                "event": "message-finish",
                "usage": {"input_tokens": 8, "output_tokens": 2, "total_tokens": 10},
                "metadata": {"model_name": "deterministic-chat"},
            },
            finish_metadata,
        )
    )

    assert calls[0][0] == "start"
    assert calls[0][1]["operation_id"] == "lc_run--model-message-1"
    assert calls[0][1]["sequence"] == 7
    assert calls[0][1]["metadata"]["model_run_id"] == "langchain-model-run-1"
    assert calls[1] == (
        "finish",
        {
            "run_id": "run-1",
            "thread_id": "thread-1",
            "worker_id": "worker-1",
            "operation_id": "lc_run--model-message-1",
            "content": "hello",
            "finished_at": calls[1][1]["finished_at"],
            "duration_ms": 321,
            "usage": {"input_tokens": 8, "output_tokens": 2, "total_tokens": 10},
            "metadata": {
                "namespace": ["model:abc"],
                "content": [{"type": "text", "text": "hello"}],
                "tool_calls": [],
                "finished_sequence": 8,
                "finish_metadata": {"model_name": "deterministic-chat"},
            },
        },
    )


@pytest.mark.asyncio
async def test_collector_rejects_start_without_protocol_sequence():
    collector = RunMessageRecorder(
        run_id="run-1",
        thread_id="thread-1",
        worker_id="worker-1",
    )

    with pytest.raises(ValueError, match="seq"):
        await collector.consume(
            _model_native_event(
                {"event": "message-start", "role": "ai", "id": "message-1"},
                {"run_id": "model-run-1", "stream_event": {"timestamp": 1_777_000_123_456}},
            )
        )


@pytest.mark.asyncio
async def test_active_lifecycle_rejects_replacement_operation_id(monkeypatch):
    """同一 lifecycle key 不得用新 operation id 覆盖进程内状态。"""
    db = _FakeDb()

    @asynccontextmanager
    async def session_context():
        yield db

    class FakeRepository:
        def __init__(self, _db):
            pass

        async def start(self, **_kwargs):
            return SimpleNamespace(id=1), True

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(service, "ModelMessageAuditRepository", FakeRepository)

    collector = RunMessageRecorder(
        run_id="run-1",
        thread_id="thread-1",
        worker_id="worker-1",
    )
    metadata = {
        "run_id": "model-run-1",
        "stream_event": {"seq": 1, "timestamp": 1_777_000_123_456},
    }
    await collector.consume(_model_native_event({"event": "message-start", "role": "ai", "id": "message-1"}, metadata))

    with pytest.raises(ValueError, match="operation id"):
        await collector.consume(_model_native_event({"event": "message-start", "role": "ai", "id": "message-2"}, metadata))


def _tool_native_event(source):
    """工具 fixture 保留内容和来源，使用原生 params 结构。"""
    return {
        "method": source.get("method"),
        "seq": source.get("seq"),
        "params": {
            "namespace": source.get("namespace", []),
            "timestamp": source.get("timestamp"),
            "data": source.get("data"),
        },
    }


@pytest.mark.asyncio
async def test_collector_projects_tool_start_and_successful_finish(monkeypatch):
    """Tool lifecycle 保存 effective input、严格顺序、输出和 monotonic 耗时。"""
    db = _FakeDb()
    calls: list[tuple[str, dict]] = []

    @asynccontextmanager
    async def session_context():
        yield db

    class FakeRepository:
        def __init__(self, _db):
            pass

        async def start(self, **kwargs):
            calls.append(("start", kwargs))
            return SimpleNamespace(id=1), True

        async def complete(self, **kwargs):
            calls.append(("complete", kwargs))
            return SimpleNamespace(id=1)

        async def fail(self, **kwargs):
            calls.append(("fail", kwargs))
            return SimpleNamespace(id=1)

    monotonic_values = iter([100.0, 100.275])
    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(service, "ToolMessageAuditRepository", FakeRepository)
    monkeypatch.setattr(service, "monotonic", lambda: next(monotonic_values))

    collector = RunMessageRecorder(
        run_id="run-1",
        thread_id="thread-1",
        worker_id="worker-1",
    )
    await collector.consume(
        _tool_native_event(
            {
                "method": "tools",
                "namespace": [],
                "seq": 11,
                "timestamp": 1_777_000_123_456,
                "data": {
                    "event": "tool-started",
                    "tool_call_id": "call-1",
                    "tool_name": "search",
                    "input": {"query": "effective input"},
                },
            }
        )
    )
    output = {
        "type": "tool",
        "tool_call_id": "call-1",
        "content": [{"type": "text", "text": "result"}],
        "status": "success",
        "private_lifecycle_field": "audit-only",
    }
    await collector.consume(
        _tool_native_event(
            {
                "method": "tools",
                "namespace": [],
                "seq": 12,
                "timestamp": 1_777_000_123_789,
                "data": {"event": "tool-finished", "tool_call_id": "call-1", "output": output},
            }
        )
    )

    assert calls[0] == (
        "start",
        {
            "run_id": "run-1",
            "thread_id": "thread-1",
            "worker_id": "worker-1",
            "tool_call_id": "call-1",
            "tool_name": "search",
            "tool_input": {"query": "effective input"},
            "sequence": 11,
            "started_at": calls[0][1]["started_at"],
            "metadata": {"namespace": []},
        },
    )
    assert calls[1] == (
        "complete",
        {
            "run_id": "run-1",
            "thread_id": "thread-1",
            "worker_id": "worker-1",
            "tool_call_id": "call-1",
            "output": output,
            "content": '[{"type": "text", "text": "result"}]',
            "finished_at": calls[1][1]["finished_at"],
            "duration_ms": 275,
            "finished_sequence": 12,
        },
    )


def test_tool_output_without_content_does_not_enter_compatibility_projection():
    """原始 lifecycle envelope 不得作为普通 ToolCall 输出。"""
    assert (
        service._tool_output_content({"type": "tool", "status": "success", "private_lifecycle_field": "audit-only"})
        == ""
    )


@pytest.mark.asyncio
async def test_collector_treats_error_tool_message_as_failed_finish(monkeypatch):
    """ToolNode 包装为 tool-finished 的 error ToolMessage 仍必须保存为失败。"""
    db = _FakeDb()
    calls: list[tuple[str, dict]] = []

    @asynccontextmanager
    async def session_context():
        yield db

    class FakeRepository:
        def __init__(self, _db):
            pass

        async def start(self, **kwargs):
            calls.append(("start", kwargs))
            return SimpleNamespace(id=1), True

        async def fail(self, **kwargs):
            calls.append(("fail", kwargs))
            return SimpleNamespace(id=1)

    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(service, "ToolMessageAuditRepository", FakeRepository)
    monkeypatch.setattr(service, "monotonic", lambda: 100.0)

    collector = RunMessageRecorder(
        run_id="run-1",
        thread_id="thread-1",
        worker_id="worker-1",
    )
    await collector.consume(
        _tool_native_event(
            {
                "method": "tools",
                "seq": 1,
                "timestamp": 1_777_000_123_456,
                "data": {
                    "event": "tool-started",
                    "tool_call_id": "call-error",
                    "tool_name": "search",
                    "input": {},
                },
            }
        )
    )
    output = {
        "type": "tool",
        "tool_call_id": "call-error",
        "content": "invalid arguments",
        "status": "error",
    }
    await collector.consume(
        _tool_native_event(
            {
                "method": "tools",
                "seq": 2,
                "timestamp": 1_777_000_123_789,
                "data": {"event": "tool-finished", "tool_call_id": "call-error", "output": output},
            }
        )
    )

    assert calls[1][0] == "fail"
    assert calls[1][1]["error_message"] == "invalid arguments"
    assert calls[1][1]["content"] == "invalid arguments"


@pytest.mark.asyncio
async def test_raw_tool_error_waits_for_run_terminal(monkeypatch):
    """裸 tool-error 可能是 LangGraph interrupt，不能提前把 pending ToolCall 判为失败。"""
    db = _FakeDb()
    observed: list[dict] = []

    @asynccontextmanager
    async def session_context():
        yield db

    class FakeRepository:
        def __init__(self, _db):
            pass

        async def start(self, **_kwargs):
            return SimpleNamespace(id=1), True

        async def observe_error(self, **kwargs):
            observed.append(kwargs)
            return SimpleNamespace(id=1)

    monotonic_values = iter([100.0, 100.2])
    monkeypatch.setattr(service.pg_manager, "get_async_session_context", session_context)
    monkeypatch.setattr(service, "ToolMessageAuditRepository", FakeRepository)
    monkeypatch.setattr(service, "monotonic", lambda: next(monotonic_values))

    collector = RunMessageRecorder(
        run_id="run-1",
        thread_id="thread-1",
        worker_id="worker-1",
    )
    await collector.consume(
        _tool_native_event(
            {
                "method": "tools",
                "seq": 1,
                "timestamp": 1_777_000_123_456,
                "data": {
                    "event": "tool-started",
                    "tool_call_id": "call-interrupt",
                    "tool_name": "ask_user_question",
                    "input": {"questions": []},
                },
            }
        )
    )
    await collector.consume(
        _tool_native_event(
            {
                "method": "tools",
                "seq": 2,
                "timestamp": 1_777_000_123_789,
                "data": {
                    "event": "tool-error",
                    "tool_call_id": "call-interrupt",
                    "message": "Interrupt",
                },
            }
        )
    )

    assert observed[0]["error_message"] == "Interrupt"
    assert observed[0]["duration_ms"] == 200
    assert observed[0]["finished_sequence"] == 2


@pytest.mark.asyncio
async def test_collector_rejects_tool_start_without_object_input():
    collector = RunMessageRecorder(
        run_id="run-1",
        thread_id="thread-1",
        worker_id="worker-1",
    )

    with pytest.raises(ValueError, match="input 必须是对象"):
        await collector.consume(
            _tool_native_event(
                {
                    "method": "tools",
                    "seq": 1,
                    "timestamp": 1_777_000_123_456,
                    "data": {
                        "event": "tool-started",
                        "tool_call_id": "call-1",
                        "tool_name": "search",
                        "input": "not-an-object",
                    },
                }
            )
        )
