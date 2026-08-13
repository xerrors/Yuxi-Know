from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import httpx
import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e, pytest.mark.slow]


async def _create_thread(client: httpx.AsyncClient, headers: dict[str, str], agent_id: str) -> str:
    response = await client.post(
        "/api/chat/thread",
        json={
            "agent_id": agent_id,
            "title": f"attachment-state-e2e-{uuid.uuid4().hex[:8]}",
            "metadata": {"_yuxi_e2e": True, "test": "attachment-state-e2e"},
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    thread_id = payload.get("thread_id") or payload.get("id")
    assert thread_id, payload
    return str(thread_id)


async def _upload_attachment(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    thread_id: str,
    file_path: Path,
) -> dict:
    with file_path.open("rb") as handle:
        response = await client.post(
            f"/api/chat/thread/{thread_id}/attachments",
            files={"file": (file_path.name, handle)},
            headers=headers,
        )

    assert response.status_code == 200, response.text
    return dict(response.json())


async def _list_attachments(client: httpx.AsyncClient, headers: dict[str, str], *, thread_id: str) -> list[dict]:
    response = await client.get(f"/api/chat/thread/{thread_id}/attachments", headers=headers)
    assert response.status_code == 200, response.text
    return list(response.json().get("attachments") or [])


async def _get_agent_state(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    thread_id: str,
) -> dict:
    response = await client.get(f"/api/chat/thread/{thread_id}/state", headers=headers)
    assert response.status_code == 200, response.text
    return dict(response.json())


async def _send_chat_message(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    thread_id: str,
    agent_slug: str,
    query: str,
) -> None:
    response = await client.post(
        "/api/agent/runs",
        json={
            "query": query,
            "agent_slug": agent_slug,
            "thread_id": thread_id,
            "meta": {"request_id": f"attachment-state-e2e-{uuid.uuid4()}"},
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    run_id = response.json().get("run_id")
    assert run_id, response.text

    deadline = asyncio.get_running_loop().time() + 240
    last_payload: dict | None = None
    while asyncio.get_running_loop().time() < deadline:
        run_response = await client.get(f"/api/agent/runs/{run_id}", headers=headers)
        assert run_response.status_code == 200, run_response.text
        last_payload = run_response.json().get("run") or {}
        status = str(last_payload.get("status") or "")
        if status in {"completed", "failed", "cancelled", "interrupted"}:
            assert status == "completed", last_payload
            return
        await asyncio.sleep(2)

    pytest.fail(f"Attachment chat run timed out: {last_payload}")


async def test_attachment_upload_is_reflected_in_agent_state(
    tmp_path: Path,
    e2e_client: httpx.AsyncClient,
    e2e_headers: dict[str, str],
    e2e_agent_context: dict[str, str | int],
):
    agent_slug = str(e2e_agent_context["agent_slug"])
    thread_id = await _create_thread(e2e_client, e2e_headers, agent_slug)

    test_file = tmp_path / "attachment-state.md"
    test_file.write_text(
        "# 测试文档\n\n这是一个用于附件状态验证的 Markdown 文件。\n\n- 第一点\n- 第二点\n",
        encoding="utf-8",
    )

    attachment_payload = await _upload_attachment(
        e2e_client,
        e2e_headers,
        thread_id=thread_id,
        file_path=test_file,
    )
    attachments = await _list_attachments(e2e_client, e2e_headers, thread_id=thread_id)
    attachment_names = {item.get("file_name") for item in attachments}
    assert test_file.name in attachment_names, attachments
    assert attachment_payload.get("file_name") == test_file.name, attachment_payload

    await asyncio.sleep(2)
    state_payload = await _get_agent_state(
        e2e_client,
        e2e_headers,
        thread_id=thread_id,
    )
    agent_state = state_payload.get("agent_state") or {}
    assert {"files", "todos", "artifacts"}.issubset(agent_state.keys()), agent_state

    await _send_chat_message(
        e2e_client,
        e2e_headers,
        thread_id=thread_id,
        agent_slug=agent_slug,
        query="你好，请简单介绍一下你自己。",
    )

    await asyncio.sleep(1)
    state_after_chat = await _get_agent_state(
        e2e_client,
        e2e_headers,
        thread_id=thread_id,
    )
    assert "agent_state" in state_after_chat, state_after_chat
