from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from yuxi.services.chat_service import stream_agent_chat
from yuxi.services.input_message_service import build_chat_input_message
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import User

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e, pytest.mark.slow]


async def _create_thread(client: httpx.AsyncClient, headers: dict[str, str], agent_slug: str) -> str:
    response = await client.post(
        "/api/chat/thread",
        json={
            "agent_id": agent_slug,
            "title": f"agent-sync-e2e-{uuid.uuid4().hex[:8]}",
            "metadata": {"_yuxi_e2e": True, "test": "agent-sync-e2e"},
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    thread_id = payload.get("thread_id") or payload.get("id")
    assert thread_id, payload
    return str(thread_id)


async def _create_sync_agent(client: httpx.AsyncClient, headers: dict[str, str], uid: str) -> str:
    default_response = await client.get("/api/agent/default", headers=headers)
    assert default_response.status_code == 200, default_response.text
    default_context = ((default_response.json().get("agent") or {}).get("config_json") or {}).get("context") or {}

    slug = f"e2e-sync-agent-{uuid.uuid4().hex[:8]}"
    context: dict[str, Any] = {
        "system_prompt": "你是端到端测试专用智能体。严格按用户要求简短回答，不调用任何工具。",
        "tools": [],
        "knowledges": [],
        "mcps": [],
        "skills": [],
        "subagents": [],
    }
    if default_context.get("model"):
        context["model"] = default_context["model"]

    response = await client.post(
        "/api/agent",
        json={
            "name": f"E2E 同步 Agent {slug[-8:]}",
            "slug": slug,
            "backend_id": "ChatbotAgent",
            "description": "真实同步 Agent E2E 临时智能体",
            "config_json": {"context": context},
            "share_config": {
                "version": 2,
                "read_scope": {"access_level": "user", "department_ids": [], "user_uids": [uid]},
                "manage_scope": None,
            },
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert (response.json().get("agent") or {}).get("slug") == slug
    return slug


async def _delete_agent(client: httpx.AsyncClient, headers: dict[str, str], slug: str) -> None:
    response = await client.delete(f"/api/agent/{slug}", headers=headers)
    assert response.status_code in {200, 404}, response.text


async def _load_user(uid: str) -> User:
    pg_manager.initialize()
    async with pg_manager.get_async_session_context() as db:
        result = await db.execute(select(User).where(User.uid == uid))
        user = result.scalar_one_or_none()
        assert user is not None, f"user {uid} not found"
        return user


async def _consume_sync_stream(*, agent_slug: str, thread_id: str, uid: str, request_id: str) -> list[dict[str, Any]]:
    current_user = await _load_user(uid)
    pg_manager.initialize()
    input_message = build_chat_input_message("请不要调用工具。请用一句中文回答：同步 Agent 端到端测试正常。")
    chunks: list[dict[str, Any]] = []

    async with pg_manager.get_async_session_context() as db:
        stream = stream_agent_chat(
            agent_slug=agent_slug,
            thread_id=thread_id,
            meta={"request_id": request_id, "source": "agent-sync-e2e"},
            input_message=input_message,
            current_user=current_user,
            db=db,
        )
        async for chunk_bytes in stream:
            for line in chunk_bytes.decode("utf-8").splitlines():
                if line.strip():
                    chunks.append(json.loads(line))

    return chunks


async def test_sync_agent_stream_persists_messages(
    e2e_client: httpx.AsyncClient,
    e2e_headers: dict[str, str],
    e2e_agent_context: dict[str, str],
):
    uid = e2e_agent_context["uid"]
    agent_slug = await _create_sync_agent(e2e_client, e2e_headers, uid)
    request_id = f"agent-sync-e2e-{uuid.uuid4()}"

    try:
        thread_id = await _create_thread(e2e_client, e2e_headers, agent_slug)

        chunks = await _consume_sync_stream(
            agent_slug=agent_slug,
            thread_id=thread_id,
            uid=uid,
            request_id=request_id,
        )

        statuses = {str(chunk.get("status") or "") for chunk in chunks}
        assert "init" in statuses, chunks
        assert "finished" in statuses, chunks
        assert "error" not in statuses, chunks
        assert any(chunk.get("response") for chunk in chunks if chunk.get("status") == "loading"), chunks

        history_response = await e2e_client.get(f"/api/chat/thread/{thread_id}/history", headers=e2e_headers)
        assert history_response.status_code == 200, history_response.text
        history = history_response.json()
        history_items = history.get("history") or []
        history_text = json.dumps(history, ensure_ascii=False)
        assert request_id in history_text, history
        assert "同步 Agent 端到端测试正常" in history_text, history
        assert any(item.get("type") == "human" for item in history_items), history
        assert any(item.get("type") == "ai" and item.get("content") for item in history_items), history
    finally:
        await _delete_agent(e2e_client, e2e_headers, agent_slug)
