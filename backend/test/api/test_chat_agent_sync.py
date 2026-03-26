"""
Integration tests for chat_agent_sync non-streaming endpoint.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _get_agent_and_config_id(test_client, headers):
    agents_response = await test_client.get("/api/chat/agent", headers=headers)
    assert agents_response.status_code == 200, agents_response.text
    agents = agents_response.json().get("agents", [])

    if not agents:
        pytest.skip("No agents are registered in the system.")

    agent_id = agents[0].get("id")
    if not agent_id:
        pytest.skip("Agent payload missing id field.")

    configs_response = await test_client.get(f"/api/chat/agent/{agent_id}/configs", headers=headers)
    assert configs_response.status_code == 200, configs_response.text
    configs = configs_response.json().get("configs", [])
    if not configs:
        pytest.skip("No agent configs are available in the system.")

    config_id = configs[0].get("id")
    if not config_id:
        pytest.skip("Agent config payload missing id field.")

    return agent_id, config_id


async def test_chat_agent_sync_requires_authentication(test_client):
    """非流式端点需要认证"""
    response = await test_client.post("/api/chat/agent/sync", json={"query": "hello", "agent_config_id": 1})
    assert response.status_code == 401


async def test_chat_agent_sync_basic_conversation(test_client, admin_headers):
    """测试非流式对话基本功能"""
    _, agent_config_id = await _get_agent_and_config_id(test_client, admin_headers)

    # 调用非流式端点
    response = await test_client.post(
        "/api/chat/agent/sync",
        json={"query": "Hello, say 'Hi' back to me", "agent_config_id": agent_config_id},
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    payload = response.json()

    # 验证响应结构
    assert "status" in payload, f"Missing 'status' in response: {payload}"
    assert payload["status"] in ("finished", "error", "interrupted"), f"Unexpected status: {payload['status']}"
    assert "request_id" in payload, f"Missing 'request_id' in response: {payload}"

    # 如果成功完成，验证响应内容
    if payload["status"] == "finished":
        assert "response" in payload, f"Missing 'response' in finished status: {payload}"
        assert isinstance(payload["response"], str), f"response should be str, got: {type(payload['response'])}"
        assert len(payload["response"]) > 0, "response should not be empty"
        # thread_id 应该存在
        assert "thread_id" in payload, f"Missing 'thread_id' in response: {payload}"
        # time_cost 应该存在
        assert "time_cost" in payload, f"Missing 'time_cost' in response: {payload}"
        assert isinstance(payload["time_cost"], float), f"time_cost should be float: {type(payload['time_cost'])}"


async def test_chat_agent_sync_with_thread_id(test_client, admin_headers):
    """测试非流式对话指定 thread_id"""
    _, agent_config_id = await _get_agent_and_config_id(test_client, admin_headers)

    import uuid

    thread_id = str(uuid.uuid4())

    response = await test_client.post(
        "/api/chat/agent/sync",
        json={
            "query": "Hello",
            "agent_config_id": agent_config_id,
            "thread_id": thread_id,
        },
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    payload = response.json()

    # 验证 thread_id 是否保持一致
    if payload["status"] == "finished":
        assert payload.get("thread_id") == thread_id, (
            f"thread_id mismatch: expected {thread_id}, got {payload.get('thread_id')}"
        )

        threads_response = await test_client.get("/api/chat/threads", headers=admin_headers)
        assert threads_response.status_code == 200, threads_response.text
        threads = threads_response.json()
        target_thread = next((item for item in threads if item.get("id") == thread_id), None)
        assert target_thread is not None, f"thread not found in thread list: {thread_id}"
        assert (target_thread.get("metadata") or {}).get("agent_config_id") == agent_config_id, (
            "agent_config_id mismatch: "
            f"expected {agent_config_id}, got {(target_thread.get('metadata') or {}).get('agent_config_id')}"
        )


async def test_chat_agent_sync_with_meta(test_client, admin_headers):
    """测试非流式对话传递 meta 参数"""
    _, agent_config_id = await _get_agent_and_config_id(test_client, admin_headers)

    import uuid

    request_id = str(uuid.uuid4())

    response = await test_client.post(
        "/api/chat/agent/sync",
        json={
            "query": "Hello",
            "agent_config_id": agent_config_id,
            "meta": {"request_id": request_id},
        },
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    payload = response.json()

    # 验证 request_id 是否保持一致
    assert payload.get("request_id") == request_id, (
        f"request_id mismatch: expected {request_id}, got {payload.get('request_id')}"
    )


async def test_chat_agent_sync_vs_streaming_consistency(test_client, admin_headers):
    """对比测试：非流式与流式端点行为一致性"""
    _, agent_config_id = await _get_agent_and_config_id(test_client, admin_headers)

    query = "What is 1+1?"

    # 调用流式端点
    import uuid

    thread_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())

    streaming_response = await test_client.post(
        "/api/chat/agent",
        json={
            "query": query,
            "agent_config_id": agent_config_id,
            "thread_id": thread_id,
            "meta": {"request_id": request_id},
        },
        headers=admin_headers,
    )

    assert streaming_response.status_code == 200, streaming_response.text

    # 收集流式响应
    streaming_content = []
    async for line in streaming_response.aiter_lines():
        if line:
            import json as json_lib

            try:
                data = json_lib.loads(line)
                if data.get("response"):
                    streaming_content.append(data["response"])
            except Exception:
                pass

    # 调用非流式端点
    thread_id2 = str(uuid.uuid4())
    request_id2 = str(uuid.uuid4())

    sync_response = await test_client.post(
        "/api/chat/agent/sync",
        json={
            "query": query,
            "agent_config_id": agent_config_id,
            "thread_id": thread_id2,
            "meta": {"request_id": request_id2},
        },
        headers=admin_headers,
    )

    assert sync_response.status_code == 200, sync_response.text
    sync_payload = sync_response.json()

    # 两者都应该成功
    assert sync_payload["status"] == "finished", f"Sync failed: {sync_payload}"

    # 非流式响应应该有内容
    assert "response" in sync_payload, f"Missing response in sync payload: {sync_payload}"
    assert len(streaming_content) > 0, "Streaming should have collected content"
