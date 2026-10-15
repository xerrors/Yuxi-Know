"""通过真实 API、PostgreSQL 与 MinIO 验证内置 MCP。"""

import json
import uuid

import pytest
import pytest_asyncio

from yuxi.infrastructure.minio import get_minio_client
from yuxi.infrastructure.minio.client import MinIOClient
from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.modules.knowledge.models import KnowledgeFile

# 所有资源由下方及公共 fixture 创建回收；MCP 不创建 Session，无需扫描共享工作目录。
pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


@pytest_asyncio.fixture
async def mcp_document(test_client, admin_headers, knowledge_base_resource):
    """创建私有测试库中的持久文档，并随 fixture 回收对象与知识库。"""
    kb_id = knowledge_base_resource["kb_id"]
    owner = await test_client.get("/api/auth/me", headers=admin_headers)
    assert owner.status_code == 200
    response = await test_client.put(
        f"/api/knowledge/knowledge-bases/{kb_id}",
        headers=admin_headers,
        json={
            "name": f"pytest_mcp_private_{uuid.uuid4().hex}",
            "description": "MCP private document fixture",
            "share_config": {
                "version": 2,
                "read_scope": {"access_level": "user", "department_ids": [], "user_uids": [owner.json()["uid"]]},
                "manage_scope": None,
            },
        },
    )
    assert response.status_code == 200, response.text
    file_id = f"pytest_mcp_{uuid.uuid4().hex[:12]}"
    object_name = f"{kb_id}/parsed/{file_id}.md"
    minio = get_minio_client()
    uploaded = await minio.aupload_file(
        MinIOClient.KB_BUCKETS["parsed"], object_name, b"First line\nMCP fixture needle\nLast line", content_type="text/markdown"
    )
    pg_manager.initialize()
    try:
        async with pg_manager.get_async_session_context() as db:
            db.add(
                KnowledgeFile(
                    file_id=file_id,
                    kb_id=kb_id,
                    filename="mcp-proof.md",
                    file_type="md",
                    markdown_file=uploaded.url,
                    status="parsed",
                    is_folder=False,
                )
            )
        yield kb_id, file_id
    finally:
        await minio.adelete_file(MinIOClient.KB_BUCKETS["parsed"], object_name)
        await pg_manager.close()


async def call_tool(client, headers, name, arguments, *, error=False):
    """读取真实 MCP 返回，并对成功与错误语义断言。"""
    response = await client.post(
        "/api/mcp",
        headers={**headers, "Accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}},
    )
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["isError"] is error, result
    text = result["content"][0]["text"]
    if not error:
        decoded = json.loads(text)
        assert result["structuredContent"] == ({"knowledge_bases": decoded} if name == "list_kbs" else decoded)
    return text


async def test_mcp_reads_persisted_documents_and_hides_other_users_resources(
    test_client, admin_headers, api_key_factory, mcp_document, standard_user
):
    """新建 Key 经 shipping MCP 回读文档事实，另一用户已知 ID 仍不可见。"""
    kb_id, file_id = mcp_document
    owner = await api_key_factory({"request_id": str(uuid.uuid4()), "name": "MCP document test", "access_level": "knowledge"})
    listed = json.loads(await call_tool(test_client, owner.headers, "list_kbs", {}))
    assert any(kb["kb_id"] == kb_id for kb in listed)
    files = json.loads(await call_tool(test_client, owner.headers, "search_file", {"kb_id": kb_id, "query": "mcp-proof"}))
    assert [f["file_id"] for f in files["files"]] == [file_id]
    opened = json.loads(await call_tool(test_client, owner.headers, "open_kb_document", {"kb_id": kb_id, "file_id": file_id}))
    assert opened["total_lines"] == 3
    assert "MCP fixture needle" in opened["content"]
    direct = await test_client.post(
        "/api/v1/knowledge/tools/open_kb_document", headers=owner.headers, json={"kb_id": kb_id, "file_id": file_id}
    )
    assert direct.status_code == 200
    assert opened == direct.json()
    found = json.loads(
        await call_tool(test_client, owner.headers, "find_kb_document", {"kb_id": kb_id, "file_id": file_id, "patterns": ["needle"]})
    )
    assert found["total_matches"] == 1
    assert found["windows"][0]["matched_lines"] == [2]

    other = await api_key_factory(
        {"request_id": str(uuid.uuid4()), "name": "MCP other user", "access_level": "knowledge"},
        owner_headers=standard_user["headers"],
        cleanup_headers=admin_headers,
    )
    listed = json.loads(await call_tool(test_client, other.headers, "list_kbs", {}))
    assert all(kb["kb_id"] != kb_id for kb in listed)
    for name, args in [("query_kb", {"kb_id": kb_id, "query_text": "needle"}), ("open_kb_document", {"kb_id": kb_id, "file_id": file_id})]:
        failure = await call_tool(test_client, other.headers, name, args, error=True)
        assert "404" in failure and "list_kbs" in failure and "MCP fixture needle" not in failure


async def test_mcp_real_auth_rejects_agents_invalid_and_revoked_keys(test_client, admin_headers, api_key_factory):
    """真实凭据的类型限制与撤销在每次协议请求生效。"""
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "pytest", "version": "1"}},
    }
    accept = {"Accept": "application/json, text/event-stream"}
    for headers in ({}, {"Authorization": "Bearer yxkey_invalid"}, admin_headers):
        response = await test_client.post("/api/mcp", headers={**headers, **accept}, json=body)
        assert response.status_code == 401
    agents = await api_key_factory(
        {"request_id": str(uuid.uuid4()), "name": "MCP agents denial", "access_level": "agents", "app_id": "pytest-mcp"}
    )
    response = await test_client.post("/api/mcp", headers={**agents.headers, **accept}, json=body)
    assert response.status_code == 403
    key = await api_key_factory({"request_id": str(uuid.uuid4()), "name": "MCP revoke test", "access_level": "knowledge"})
    response = await test_client.post("/api/mcp", headers={**key.headers, **accept}, json=body)
    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"] == "Yuxi Knowledge"
    deleted = await test_client.delete(f"/api/user/apikey/{key.key_id}", headers=admin_headers)
    assert deleted.status_code == 200
    response = await test_client.post(
        "/api/mcp", headers={**key.headers, **accept}, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    )
    assert response.status_code == 401
