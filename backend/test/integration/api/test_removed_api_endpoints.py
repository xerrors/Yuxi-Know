"""已移除 API 路由的防复活检查。"""

from __future__ import annotations

import pytest
import uuid

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_removed_agent_session_entrypoints_are_unreachable(test_client, admin_headers):
    """旧聊天、Channel 和 Invocation 入口不再接收执行请求。"""
    requests = (
        ("/api/chat/thread", {"agent_id": "default-chatbot"}),
        ("/api/agent/runs", {"query": "hello", "agent_slug": "default-chatbot"}),
        ("/api/agent-invocation/channel/messages", {"message": {"type": "text", "text": "hello"}}),
        ("/api/agent-invocation/eval/runs", {"query": "hello"}),
        ("/api/agent-invocation/agent-call/runs", {"messages": []}),
    )
    for path, body in requests:
        response = await test_client.post(path, json=body, headers=admin_headers)
        assert response.status_code in {404, 405}, (path, response.text)


async def test_reranker_endpoint_is_offline(test_client, standard_user, admin_headers):
    """已移除的 reranker 路由对匿名、普通用户和管理员均不可达。"""
    for headers in (None, standard_user["headers"], admin_headers):
        response = await test_client.get("/api/settings/rerankers", headers=headers)
        assert response.status_code == 404, response.text


async def test_regenerate_api_key_endpoint_is_removed(test_client, admin_headers):
    response = await test_client.post("/api/user/apikey/1/regenerate", headers=admin_headers)
    assert response.status_code == 404, response.text


@pytest.mark.parametrize(
    "path",
    [
        "/api/graph/neo4j/nodes",
        "/api/graph/neo4j/node",
        "/api/graph/neo4j/info",
        "/api/graph/neo4j/index-entities",
        "/api/graph/neo4j/add-entities",
    ],
)
async def test_neo4j_upload_routes_are_removed(test_client, admin_headers, path):
    method = test_client.post if path.endswith(("index-entities", "add-entities")) else test_client.get
    response = await method(path, headers=admin_headers)
    assert response.status_code == 404


@pytest.mark.parametrize("prefix", ["/api/v1/knowledge", "/api/knowledge"])
@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("GET", ""),
        ("GET", "/missing/files"),
        ("POST", "/missing/retrieve"),
        ("GET", "/missing/files/missing/open"),
        ("POST", "/missing/files/missing/find"),
    ],
)
async def test_external_operations_are_removed(test_client, admin_headers, prefix, method, suffix):
    """两种 external 前缀均不再提供查询操作或兼容转发。"""
    response = await test_client.request(method, f"{prefix}/databases/external{suffix}", headers=admin_headers)
    assert response.status_code == 404, response.text


async def test_public_knowledge_does_not_expose_management_routes(test_client, admin_headers):
    """版本化知识域只公开工具查询入口。"""
    response = await test_client.get("/api/v1/knowledge/knowledge-bases", headers=admin_headers)
    assert response.status_code == 404, response.text


async def test_legacy_knowledge_resource_paths_are_unregistered(test_client, admin_headers):
    """旧数据库资源与独立 Markdown 转换入口均没有兼容路由。"""
    for path in (
        "/api/knowledge/databases",
        "/api/knowledge/databases/accessible",
        "/api/knowledge/databases/kb-missing/documents",
        "/api/evaluation/databases/kb-missing/datasets",
    ):
        response = await test_client.get(path, headers=admin_headers)
        assert response.status_code == 404, (path, response.text)
    conversion = await test_client.post("/api/knowledge/files/markdown", headers=admin_headers)
    assert conversion.status_code == 404, conversion.text


async def test_retired_task_routes_are_not_registered(test_client, admin_headers):
    """旧任务接口不能继续提供后台作业别名。"""
    for method, path in (
        ("GET", "/api/tasks"),
        ("GET", "/api/tasks/retired-id"),
        ("POST", "/api/tasks/retired-id/cancel"),
    ):
        response = await test_client.request(method, path, headers=admin_headers)
        assert response.status_code == 404


async def test_retired_conversation_routes_are_not_registered(test_client, admin_headers):
    """旧会话审计路由不提供兼容入口。"""
    for path in ("/api/dashboard/conversations", "/api/dashboard/conversations/options"):
        response = await test_client.get(path, headers=admin_headers)
        assert response.status_code == 404, response.text


async def test_legacy_direct_thread_attachment_upload_is_removed(test_client, admin_headers):
    response = await test_client.post(
        f"/api/v1/agents/sessions/{uuid.uuid4()}/attachments",
        headers=admin_headers,
        files={"file": ("legacy.txt", b"legacy", "text/plain")},
    )
    assert response.status_code == 405
