"""实际记录器与公开适配器共同消费工具结果，以 PG 行和协议结果作 oracle。"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from test.integration.services.agent_input_fixtures import start_input_run
from test.integration.services.agent_input_fixtures import sessions as sessions
from yuxi.modules.agents.models.messages import TOOL_AUDIT_MESSAGE_TYPE, Message
from yuxi.modules.agents.services.message_recorder import RunMessageRecorder
from yuxi.modules.agents.services.openai_events import OpenAIEventAdapter

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


@pytest.mark.parametrize(
    ("content", "message", "expected_output", "expected_text", "expected_error"),
    [
        ({"reason": "bad"}, None, '{"reason": "bad"}', '{"reason": "bad"}', '{"reason": "bad"}'),
        (
            [{"type": "text", "text": "错误详情"}],
            None,
            [{"type": "input_text", "text": "错误详情"}],
            '[{"type": "text", "text": "错误详情"}]',
            '[{"type": "text", "text": "错误详情"}]',
        ),
        ("", None, "", "", "工具执行失败"),
        ("", "明确错误", "", "", "明确错误"),
    ],
)
async def test_failed_tool_audit_and_public_output_use_same_normalized_result(
    sessions, content, message, expected_output, expected_text, expected_error
):
    """序列化结构化/空结果与明确原因一次；公开快照和审计从同一 Run 回读。"""
    run = await start_input_run(sessions)
    recorder = RunMessageRecorder(run_id=run.id, thread_id=run.thread_id, worker_id="owner")
    adapter = OpenAIEventAdapter(run_id=run.id, turn_id=run.turn_id, thread_id=run.thread_id, worker_id="owner")
    source = {"status": "error", "content": content}
    events = [
        ("messages", {"event": "message-start", "id": "model"}),
        (
            "messages",
            {"event": "content-block-finish", "index": 0, "content": {"type": "tool_call", "id": "call", "name": "test", "args": {}}},
        ),
        ("messages", {"event": "message-finish"}),
        ("tools", {"event": "tool-started", "tool_call_id": "call", "tool_name": "test", "input": {}}),
        ("tools", {"event": "tool-finished", "tool_call_id": "call", "output": source, "message": message}),
    ]
    published = []
    timestamp = datetime.now(UTC).timestamp() * 1000
    for seq, (method, data) in enumerate(events):
        event = {
            "seq": seq,
            "method": method,
            "params": {
                "timestamp": timestamp + seq,
                "namespace": [],
                "data": (data, {"run_id": "model"}) if method == "messages" else data,
            },
        }
        published.extend(await adapter.consume(await recorder.consume(event)))
    output = next(
        event["item"]
        for event in published
        if event.get("item", {}).get("type") == "function_call_output" and event["item"]["status"] == "failed"
    )
    assert output["output"] == expected_output
    assert output["error"] == expected_error
    async with sessions() as oracle:
        audit = await oracle.scalar(
            select(Message).where(Message.run_id == run.id, Message.operation_id == "call", Message.message_type == TOOL_AUDIT_MESSAGE_TYPE)
        )
        assert audit.turn_id == run.turn_id and audit.execution_status == "failed"
        assert audit.content == expected_text and audit.extra_metadata["error_message"] == expected_error
        assert audit.extra_metadata["output"] == source
        stored = audit.extra_metadata["public_items"]["output"]
        assert stored["output"] == expected_output and stored["error"] == expected_error
    assert source == {"status": "error", "content": content}
