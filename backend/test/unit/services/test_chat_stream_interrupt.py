"""测试执行器中的等待点恢复与中断投影。"""

from types import SimpleNamespace

import pytest

from yuxi.modules.agents.services.execution import (
    _build_ask_user_question_payload,
    _build_tool_approval_payload,
)
import yuxi.modules.agents.services.execution as svc


def test_build_tool_approval_payload_rejects_mismatched_lists():
    assert _build_tool_approval_payload({"action_requests": [{}], "review_configs": []}, "thread-1") is None


def test_question_projection_preserves_checkpoint_structure_and_ids():
    """服务层只投影标准等待点，不重新规范化或生成回答键。"""
    questions = [
        {
            "question_id": "destination",
            "question": "你想去哪个城市？",
            "options": [],
            "multi_select": False,
            "allow_other": True,
        },
        {
            "question_id": "style",
            "question": "选择风格",
            "options": [{"label": "简洁", "value": "simple", "description": "简洁布局"}],
            "multi_select": True,
            "allow_other": False,
            "operation": "确认风格",
        },
    ]
    result = svc.build_pending_interrupt_payload(SimpleNamespace(value={"questions": questions, "source": "ask_user_question"}), "thread-1")
    assert result == {
        "status": "ask_user_question_required",
        "questions": questions,
        "source": "ask_user_question",
        "thread_id": "thread-1",
    }
    assert result["questions"] is questions


@pytest.mark.parametrize("payload", [{}, {"questions": []}, {"questions": None}, {"questions": "[]"}])
def test_question_projection_rejects_missing_questions_instead_of_inventing_placeholder(payload):
    """无效中断不能伪装为可回答的占位题。"""
    with pytest.raises(ValueError, match="缺少标准 questions"):
        _build_ask_user_question_payload(payload, "thread-1")


def test_approval_projection_keeps_approval_protocol():
    """提问契约收敛不影响工具审批。"""
    approval = {
        "action_requests": [{"name": "execute", "args": {"command": "pwd"}}],
        "review_configs": [{"action_name": "execute", "allowed_decisions": ["approve", "reject"]}],
    }
    result = svc.build_pending_interrupt_payload(approval, "thread-1")
    assert result == {"status": "human_approval_required", "approval": approval, "thread_id": "thread-1"}
