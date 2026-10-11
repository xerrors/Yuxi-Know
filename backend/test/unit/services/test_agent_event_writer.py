from __future__ import annotations

from unittest.mock import AsyncMock


import yuxi.modules.agents.services.event_writer as event_writer


async def test_public_writer_flushes_function_call_boundary(monkeypatch):
    """完整参数已经生成的实际函数调用立即对外，不生成参数增量。"""
    append = AsyncMock()
    monkeypatch.setattr(event_writer, "append_run_stream_events", append)
    writer = event_writer.PublicEventWriter("run")
    call = {"type": "agent.session.turn.item.added", "item": {"type": "function_call", "arguments": {"q": "x"}}}
    await writer.append(call)
    append.assert_awaited_once_with("run", [call])
    assert event_writer.contains_model_output(call)
    assert not event_writer.contains_model_output({"type": "yuxi.session.turn.state"})


async def test_public_writer_preserves_each_event_and_flushes_first_semantic_output(monkeypatch):
    """空 item 不吞首 token，批量仅合并写入且 done 及时冲刷增量。"""
    batches = []

    async def append(run_id, events):
        assert run_id == "run"
        batches.append(events)

    monkeypatch.setattr(event_writer, "append_run_stream_events", append)
    writer = event_writer.PublicEventWriter("run", interval_ms=100000, max_chars=512)
    added = {"type": "agent.session.turn.item.added", "item": {"type": "message"}}
    first = {"type": "agent.session.turn.output_text.delta", "delta": "first"}
    second = {"type": "agent.session.turn.output_text.delta", "delta": "second"}
    done = {"type": "agent.session.turn.output_text.done", "text": "firstsecond"}
    for event in (added, first, second, done):
        await writer.append(event)
    assert batches == [[added], [first], [second, done]]
