"""
Integration tests for batch question resume payload validation.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_resume_rejects_non_dict_answer(test_client, admin_headers):
    response = await test_client.post(
        "/api/chat/agent/dummy-agent/resume",
        json={"thread_id": "thread-test", "answer": "approve"},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert "answer 必须是对象映射" in response.text


async def test_resume_rejects_empty_answer_map(test_client, admin_headers):
    response = await test_client.post(
        "/api/chat/agent/dummy-agent/resume",
        json={"thread_id": "thread-test", "answer": {}},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert "answer 不能为空" in response.text


async def test_resume_rejects_empty_question_id(test_client, admin_headers):
    response = await test_client.post(
        "/api/chat/agent/dummy-agent/resume",
        json={"thread_id": "thread-test", "answer": {"": "选项A"}},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert "question_id 不能为空" in response.text


async def test_resume_rejects_empty_answer_text(test_client, admin_headers):
    response = await test_client.post(
        "/api/chat/agent/dummy-agent/resume",
        json={"thread_id": "thread-test", "answer": {"q1": "  "}},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert "answer 不能为空" in response.text


async def test_resume_accepts_batch_answer_map(test_client, admin_headers):
    response = await test_client.post(
        "/api/chat/agent/dummy-agent/resume",
        json={"thread_id": "thread-test", "answer": {"q1": "选项A", "q2": ["选项B", "选项C"]}},
        headers=admin_headers,
    )

    # 通过参数校验后会进入流式逻辑，dummy-agent 不存在时也会以 200 返回 error chunk。
    assert response.status_code == 200
