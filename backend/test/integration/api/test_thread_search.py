"""真实 HTTP 验证历史对话搜索：结果必须携带完整线程字段，并能按标题命中。"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import asyncpg
import httpx
import pytest

from test.live_api_cleanup import make_test_conversation_metadata, make_test_conversation_title

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _postgres_dsn() -> str:
    return os.getenv("POSTGRES_URL", "postgresql+asyncpg://postgres:postgres@postgres:5432/yuxi").replace(
        "+asyncpg", ""
    )


async def _create_thread(test_client: httpx.AsyncClient, headers: dict[str, str], *, title: str) -> str:
    agents_resp = await test_client.get("/api/agent", headers=headers)
    assert agents_resp.status_code == 200, agents_resp.text
    agents = agents_resp.json().get("agents", [])
    assert agents, "对话搜索 integration 需要至少一个可见 Agent。"
    agent_id = agents[0].get("agent_id") or agents[0].get("slug")

    create_resp = await test_client.post(
        "/api/chat/thread",
        json={"agent_id": agent_id, "title": title, "metadata": make_test_conversation_metadata("thread-search")},
        headers=headers,
    )
    assert create_resp.status_code == 200, create_resp.text
    payload = create_resp.json()
    thread_id = payload.get("thread_id") or payload.get("id")
    assert thread_id, f"创建对话响应缺少 thread 标识: {payload}"
    return str(thread_id)


async def _insert_message(thread_id: str, content: str) -> None:
    conn = await asyncpg.connect(_postgres_dsn())
    try:
        conversation = await conn.fetchrow("SELECT id FROM conversations WHERE thread_id = $1", thread_id)
        assert conversation, f"测试对话不存在: {thread_id}"
        await conn.execute(
            """
            INSERT INTO messages (conversation_id, role, content, message_type, delivery_status, created_at)
            VALUES ($1, 'user', $2, 'text', 'delivered', $3)
            """,
            conversation["id"],
            content,
            datetime.now(UTC).replace(tzinfo=None),
        )
    finally:
        await conn.close()


async def _delete_thread(test_client: httpx.AsyncClient, headers: dict[str, str], thread_id: str) -> None:
    await test_client.delete(f"/api/chat/thread/{thread_id}", headers=headers)


async def test_thread_search_content_match_returns_full_thread_fields(test_client, admin_headers):
    """正文命中的搜索结果必须能通过 ThreadResponse 的全部必填字段。"""
    thread_id = await _create_thread(test_client, admin_headers, title=make_test_conversation_title("search-body"))
    token = uuid.uuid4().hex
    try:
        await _insert_message(thread_id, f"搜索正文命中 {token}")

        response = await test_client.get(f"/api/chat/threads/search?q={token}", headers=admin_headers)
        assert response.status_code == 200, response.text
        matched = [item for item in response.json()["items"] if item["id"] == thread_id]
        assert matched, f"正文命中结果缺少目标对话: {response.json()}"

        item = matched[0]
        assert item["thread_id"] == thread_id
        assert item["workdir_path"]
        assert item["matched_count"] >= 1
        assert token in item["snippets"][0]["content"]
    finally:
        await _delete_thread(test_client, admin_headers, thread_id)


async def test_thread_search_matches_conversation_title_without_message_hit(test_client, admin_headers):
    """只匹配标题的对话也必须能被搜到，且不伪造消息命中数。"""
    token = uuid.uuid4().hex
    thread_id = await _create_thread(test_client, admin_headers, title=make_test_conversation_title(f"title-{token}"))
    try:
        response = await test_client.get(f"/api/chat/threads/search?q={token}", headers=admin_headers)
        assert response.status_code == 200, response.text
        matched = [item for item in response.json()["items"] if item["id"] == thread_id]
        assert matched, f"标题命中结果缺少目标对话: {response.json()}"

        item = matched[0]
        assert item["matched_count"] == 0
        assert item["snippets"] == []
    finally:
        await _delete_thread(test_client, admin_headers, thread_id)


async def test_thread_search_does_not_leak_other_users_threads(test_client, admin_headers, standard_user):
    """搜索只能在本人可见范围内命中，标题与正文都不能跨用户泄露。"""
    other_headers = standard_user["headers"]
    token = uuid.uuid4().hex
    thread_id = await _create_thread(test_client, other_headers, title=make_test_conversation_title(f"private-{token}"))
    try:
        await _insert_message(thread_id, f"私有正文 {token}")

        response = await test_client.get(f"/api/chat/threads/search?q={token}", headers=admin_headers)
        assert response.status_code == 200, response.text
        assert [item for item in response.json()["items"] if item["id"] == thread_id] == []
    finally:
        await _delete_thread(test_client, other_headers, thread_id)
