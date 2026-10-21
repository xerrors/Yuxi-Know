"""恢复标记的持久编码与实例判定契约。"""

import pytest

from yuxi.modules.agents.models.inputs import AgentInput, queue_resume_payload


@pytest.mark.parametrize(
    ("payload", "expected"),
    [({}, False), ({"resume_queue": False}, False), ({"resume_queue": True}, True), ({"resume_queue": "true"}, False)],
)
def test_recovery_marker_uses_existing_boolean_protocol(payload, expected):
    """实例仅接受内部布尔 true，旧的普通输入没有恢复意图。"""
    assert AgentInput(input_payload=payload).resumes_queue is expected


def test_recovery_payload_cannot_be_modified_by_another_input():
    """每条输入获得独立恢复事实，不共享可变标记字典。"""
    first = queue_resume_payload()
    first["resume_queue"] = False
    assert queue_resume_payload() == {"resume_queue": True}
