"""独立官方协议 oracle 与原生块的映射，不读取生产 mapper 生成 expected。"""

from copy import deepcopy
import json
from pathlib import Path
from datetime import UTC, datetime
from types import SimpleNamespace

import jsonschema
import pytest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from test.support.agent_stream_fixtures import native
from yuxi.modules.agents.services.openai_events import OpenAIEventAdapter
from yuxi.modules.agents.services.message_recorder import tool_event_output
from yuxi.modules.agents.tool_results import normalize_tool_result

SCHEMA = json.loads((Path(__file__).parents[2] / "support/openai_agents_events.schema.json").read_text())


def test_native_event_identity_is_unique_across_execution_owners():
    """同 Run 接管后的原生 seq 从零开始，不能与旧执行的事件身份冲突。"""
    first = OpenAIEventAdapter(run_id="run", turn_id="turn", thread_id="thread", worker_id="first")
    second = OpenAIEventAdapter(run_id="run", turn_id="turn", thread_id="thread", worker_id="second")
    event = first.extension("turn.state", "0:state", state={})
    assert event == first.extension("turn.state", "0:state", state={})
    assert event["event_id"] != second.extension("turn.state", "0:state", state={})["event_id"]


@pytest.fixture
def adapter(monkeypatch):
    """纯协议用稳定存储身份隔离事务；持久一致性由 E2E 验证。"""
    adapter = OpenAIEventAdapter(run_id="run", turn_id="turn", thread_id="thread", worker_id="owner")
    saved = {}

    async def save(operation, role, key, item, content_index=None):
        identity = f"{operation}:{role}:{key}"
        index = saved.get(identity, {}).get("yuxi", {}).get("output_index", len(saved))
        result = {
            **deepcopy(item),
            "id": identity,
            "turn_id": "turn",
            "yuxi": {**item.get("yuxi", {}), "output_index": index, "run_id": "run", "message_id": operation},
        }
        saved[identity] = result
        return deepcopy(result)

    monkeypatch.setattr(adapter, "_save", save)
    return adapter


async def collect(adapter, events):
    """独立 schema 严格验证每个标准事件，扩展明确使用 yuxi 名称。"""
    output = []
    for event in events:
        if event["method"] == "tools" and event["params"]["data"].get("event") == "tool-finished":
            data = event["params"]["data"]
            value = tool_event_output(data)
            event = {
                **event,
                "params": {
                    **event["params"],
                    "data": {**data, "output": value, "result": normalize_tool_result(value, message=data.get("message"))},
                },
            }
        batch = await adapter.consume(event)
        for value in batch:
            if value["type"].startswith("agent."):
                jsonschema.validate(value, SCHEMA)
            else:
                assert value["type"].startswith("yuxi.")
        output.extend(batch)
    return output


@pytest.mark.asyncio
async def test_multiple_blocks_done_replaces_full_text_and_reasoning_is_extension(adapter):
    output = await collect(
        adapter,
        [
            native(0, {"event": "message-start", "id": "model"}),
            native(
                1,
                {"event": "content-block-delta", "index": 0, "delta": {"type": "reasoning-delta", "reasoning": "raw"}},
            ),
            native(
                2,
                {
                    "event": "content-block-finish",
                    "index": 0,
                    "content": {"type": "reasoning", "reasoning": "raw full"},
                },
            ),
            native(3, {"event": "content-block-delta", "index": 1, "delta": {"type": "text-delta", "text": "part"}}),
            native(4, {"event": "content-block-finish", "index": 1, "content": {"type": "text", "text": "whole"}}),
            native(5, {"event": "content-block-finish", "index": 2, "content": {"type": "text", "text": "second"}}),
        ],
    )
    done = [event for event in output if event["type"].endswith("output_text.done")]
    assert [(event["content_index"], event["text"]) for event in done] == [(0, "whole"), (1, "second")]
    assert done[0]["item_id"] == done[1]["item_id"]
    assert len({event["event_id"] for event in output}) == len(output)
    assert any(event["type"] == "yuxi.session.turn.reasoning.done" and event["text"] == "raw full" for event in output)
    assert not any("summary" in event["type"] for event in output)
    assert all("source" not in value["yuxi"] for value in output)
    item = next(iter(adapter.models.values()))["item"]
    assert item["yuxi"]["completed_content_indices"] == [0, 1]
    assert item["yuxi"]["completed_reasoning_indices"] == [0]


@pytest.mark.asyncio
@pytest.mark.parametrize("failed", [False, True])
async def test_tool_only_uses_function_items_and_command_call_identity(adapter, failed):
    output = await collect(
        adapter,
        [
            native(0, {"event": "message-start", "id": "model"}),
            native(
                1,
                {
                    "event": "content-block-finish",
                    "index": 0,
                    "content": {"type": "tool_call", "id": "call", "name": "web_search", "args": {"q": "x"}},
                },
            ),
            native(2, {"event": "message-finish"}),
            native(
                3,
                {"event": "tool-started", "tool_call_id": "call", "tool_name": "web_search", "input": {"q": "x"}},
                "tools",
            ),
            native(
                4,
                {
                    "event": "tool-finished",
                    "tool_call_id": "call",
                    "output": Command(
                        update={
                            "messages": [
                                ToolMessage(content="unrelated", tool_call_id="other"),
                                ToolMessage(content="result", tool_call_id="call", status="error" if failed else "success"),
                            ]
                        }
                    ),
                },
                "tools",
            ),
        ],
    )
    added = [event["item"] for event in output if event["type"].endswith("item.added")]
    done = [event["item"] for event in output if event["type"].endswith("item.done")]
    assert [item["type"] for item in added] == ["function_call", "function_call_output"]
    assert added[0]["arguments"] == {"q": "x"}
    assert done[0]["id"] == added[0]["id"]
    assert done[1]["id"] == added[1]["id"]
    assert done[1]["output"] == "result"
    assert done[1]["status"] == ("failed" if failed else "completed")
    assert not any("arguments.delta" in event["type"] or "web_search" in event["type"] for event in output)


@pytest.mark.asyncio
async def test_missing_message_start_fails_instead_of_binding_adjacent_item(adapter):
    with pytest.raises(ValueError, match="message-start"):
        await adapter.consume(native(5, {"event": "content-block-delta", "delta": {"type": "text-delta", "text": "bad"}}))


@pytest.mark.asyncio
async def test_tool_error_waits_for_committed_run_outcome(adapter):
    """GraphInterrupt 与异常共享原生 tool-error，不能提前伪造 failed。"""
    assert await adapter.consume(native(1, {"event": "tool-error", "tool_call_id": "call", "message": "interrupt"}, "tools")) == []


@pytest.mark.asyncio
async def test_failure_preserves_completed_commentary_and_only_saves_active_partial(adapter):
    """后续模型失败不能使已完成的正文在刷新后降级。"""
    await collect(
        adapter,
        [
            native(0, {"event": "message-start", "id": "first"}),
            native(1, {"event": "content-block-finish", "content": {"type": "text", "text": "complete"}}),
            native(2, {"event": "message-finish"}),
        ],
    )
    events = [
        native(3, {"event": "message-start", "id": "second"}),
        native(4, {"event": "content-block-delta", "delta": {"type": "text-delta", "text": "partial"}}),
    ]
    for event in events:
        event["params"]["data"][1]["run_id"] = "second"
    await collect(adapter, events)
    await adapter.persist_incomplete()
    items = [model["item"] for model in adapter.models.values()]
    assert [(item["status"], item["content"][0]["text"]) for item in items] == [
        ("completed", "complete"),
        ("incomplete", "partial"),
    ]


@pytest.mark.asyncio
async def test_rejected_message_finish_keeps_displayed_text_available_for_cancel_snapshot(adapter, monkeypatch):
    """完成快照被取消拒绝时，未提交的 completed 不能阻止部分正文收敛。"""
    await collect(
        adapter,
        [
            native(0, {"event": "message-start", "id": "model"}),
            native(1, {"event": "content-block-delta", "delta": {"type": "text-delta", "text": "shown"}}),
        ],
    )
    save = adapter._save

    async def reject_completed(operation, role, key, item, content_index=None):
        """模拟真实 Run 已进入 cancel_requested 后拒绝普通输出写入。"""
        if item["status"] == "completed":
            raise ValueError("输出已被取消")
        return await save(operation, role, key, item, content_index)

    monkeypatch.setattr(adapter, "_save", reject_completed)
    with pytest.raises(ValueError, match="输出已被取消"):
        await adapter.consume(native(2, {"event": "message-finish"}))
    await adapter.persist_incomplete()
    item = next(iter(adapter.models.values()))["item"]
    assert item["status"] == "incomplete"
    assert item["content"] == [{"type": "output_text", "text": "shown"}]


@pytest.mark.parametrize(
    "name,status",
    [
        ("created", "queued"),
        ("in_progress", "in_progress"),
        ("completed", "completed"),
        ("failed", "failed"),
        ("cancelled", "cancelled"),
    ],
)
def test_turn_lifecycle_events_keep_required_protocol_fields(name, status):
    """普通 Session 的标准 Turn 事件保留官方 nullable 字段。"""
    from yuxi.modules.agents.services import subscriptions as events

    now = datetime(2026, 10, 7, tzinfo=UTC)
    run = SimpleNamespace(
        id="run",
        thread_id="thread",
        agent_slug="main",
        started_at=now,
        error_message=None,
        created_by_run_id=None,
        error_type=None,
    )
    turn = SimpleNamespace(id="turn", thread_id="thread", created_at=now, finished_at=now, result_run_id="run", current_run_id="run")
    event = events._turn_event(None, run, turn, name, status, now, ["input"])
    jsonschema.validate(event, SCHEMA)
    assert event["turn"]["subagent_id"] is None
