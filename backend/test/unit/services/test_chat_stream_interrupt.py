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
    result = svc.build_pending_interrupt_payload(
        [SimpleNamespace(value={"questions": questions, "source": "ask_user_question"})], "thread-1"
    )
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
    result = svc.build_pending_interrupt_payload([approval], "thread-1")
    assert result == {"status": "human_approval_required", "approval": approval, "thread_id": "thread-1"}


def _cooperation_interrupt(interrupt_id: str, **wait) -> SimpleNamespace:
    """构造带恢复 ID 的协作等待中断。"""
    return SimpleNamespace(id=interrupt_id, value={"kind": "cooperation", **wait})


def test_parallel_cooperation_waits_keep_every_interrupt_id():
    """并行等待聚合为一次恢复，每个等待保留自身中断 ID 与目标。"""
    first = _cooperation_interrupt("i-1", target_inputs=["in-1"], deadline="2026-10-24T00:00:00+00:00")
    second = _cooperation_interrupt("i-2", target_sessions=["s-1"], after_cursor=3, deadline="2026-10-24T00:01:00+00:00")
    result = svc.build_pending_interrupt_payload([first, second], "thread-1")
    assert result == {
        "status": "cooperation_waiting",
        "thread_id": "thread-1",
        "waits": [
            {"interrupt_id": "i-1", "target_inputs": ["in-1"], "deadline": "2026-10-24T00:00:00+00:00"},
            {"interrupt_id": "i-2", "target_sessions": ["s-1"], "after_cursor": 3, "deadline": "2026-10-24T00:01:00+00:00"},
        ],
    }
    waitpoint = svc._waitpoint_from_interrupt(result, "run-1")
    assert waitpoint["kind"] == "cooperation" and waitpoint["run_id"] == "run-1"
    assert waitpoint["waits"] == result["waits"]


@pytest.mark.parametrize(
    "second_payload",
    [
        {"action_requests": [{"name": "execute"}], "review_configs": [{"allowed_decisions": ["approve"]}]},
        {"questions": [{"question_id": "q", "question": "？", "options": []}], "source": "ask_user_question"},
    ],
)
def test_mixed_parallel_waits_fail_instead_of_dropping_interrupts(second_payload):
    """混合等待类型没有统一恢复入口，显式失败而不是静默保存其中一个。"""
    wait = _cooperation_interrupt("i-1", target_inputs=["in-1"], deadline="2026-10-24T00:00:00+00:00")
    with pytest.raises(ValueError, match="只有全部为协作等待才能聚合恢复"):
        svc.build_pending_interrupt_payload([wait, SimpleNamespace(value=second_payload)], "thread-1")


@pytest.mark.parametrize(
    "payload",
    [
        {"action_requests": [{"name": "execute"}], "review_configs": [{"allowed_decisions": ["approve"]}]},
        {"questions": [{"question_id": "q", "question": "？", "options": []}], "source": "ask_user_question"},
    ],
)
def test_multiple_human_interrupts_fail_instead_of_publishing_only_first(payload):
    """多个独立人工等待没有共享恢复协议，不能暴露一个看似可恢复的等待点。"""
    with pytest.raises(ValueError, match="只有全部为协作等待才能聚合恢复"):
        svc.build_pending_interrupt_payload([SimpleNamespace(value=payload), SimpleNamespace(value=payload)], "thread-1")


def test_cooperation_wait_without_interrupt_id_fails():
    """缺少中断 ID 的等待无法按 ID 恢复，不能进入持久等待点。"""
    with pytest.raises(ValueError, match="中断 ID"):
        svc.build_pending_interrupt_payload(
            [SimpleNamespace(value={"kind": "cooperation", "target_inputs": ["in-1"], "deadline": "soon"})], "thread-1"
        )


def test_extract_interrupts_collects_all_pending_waits():
    """并行任务的多个中断全部提取，不依赖返回顺序。"""
    first = _cooperation_interrupt("i-1", target_inputs=["in-1"], deadline="soon")
    second = _cooperation_interrupt("i-2", target_sessions=["s-1"], after_cursor=0, deadline="soon")
    state = SimpleNamespace(tasks=[SimpleNamespace(interrupts=[first], result=None), SimpleNamespace(interrupts=[second], result=None)])
    assert svc._extract_interrupts(state) == [first, second]
    assert svc._extract_interrupts(SimpleNamespace(tasks=[], values={})) == []


def test_extract_interrupts_ignores_completed_task_but_keeps_reinterrupted_task():
    """业务结果才证明工具已完成；恢复后再次中断的空结果仍需保留。"""
    completed = _cooperation_interrupt("completed", target_inputs=["old"], deadline="soon")
    pending = _cooperation_interrupt("pending", target_inputs=["next"], deadline="soon")
    state = SimpleNamespace(
        tasks=[
            SimpleNamespace(interrupts=[completed], result={"messages": ["completed tool result"]}),
            SimpleNamespace(interrupts=[pending], result={}),
        ],
        values={},
    )
    assert svc._extract_interrupts(state) == [pending]
    state.tasks = [state.tasks[0]]
    state.values = {"__interrupt__": [completed]}
    assert svc._extract_interrupts(state) == []
