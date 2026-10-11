"""Knowledge Public 工具入口的真实 HTTP 权限与调用契约。"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from test.support.knowledge import default_embedding_model_spec
from yuxi.infrastructure.minio import get_minio_client
from yuxi.infrastructure.minio.client import MinIOClient
from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.modules.knowledge.models import KnowledgeBase, KnowledgeFile

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_knowledge_key_tool_route_boundary_without_kb(test_client, api_key_factory):
    """不依赖向量服务，证明 Knowledge Key 仅能调用登记的只读工具。"""
    created = await api_key_factory(
        {"request_id": str(uuid.uuid4()), "name": "Knowledge tool boundary", "access_level": "knowledge"}
    )
    listed = await test_client.get("/api/v1/knowledge/tools/list_kbs", headers=created.headers)
    assert listed.status_code == 200, listed.text
    assert isinstance(listed.json(), list)

    for path in (
        "/api/v1/agents",
        "/api/knowledge/knowledge-bases",
        "/api/knowledge/knowledge-bases/external",
        "/api/user/apikey/",
        "/api/graph/list",
        "/api/evaluation/knowledge-bases/unused/datasets",
    ):
        blocked = await test_client.get(path, headers=created.headers)
        assert blocked.status_code == 403, (path, blocked.text)
    absent = await test_client.post(
        "/api/v1/knowledge/tools/download_kb_file",
        json={"kb_id": "missing", "file_id": "missing"},
        headers=created.headers,
    )
    assert absent.status_code == 404, absent.text


async def test_agents_key_cannot_access_public_knowledge_api(test_client, api_key_factory):
    """Agents 与 Knowledge 两种受限 Key 的 API 面互不包含。"""
    created = await api_key_factory(
        {
            "request_id": str(uuid.uuid4()),
            "name": "Agents API boundary test",
            "access_level": "agents",
            "app_id": "knowledge-boundary-test",
        }
    )
    tool_response = await test_client.get("/api/v1/knowledge/tools/list_kbs", headers=created.headers)
    assert tool_response.status_code == 403, tool_response.text


@pytest_asyncio.fixture
async def readable_knowledge_tool_data(knowledge_base_resource):
    """在真实 PostgreSQL 与 MinIO 中准备可读文档。"""
    kb_id = knowledge_base_resource["kb_id"]
    file_id = f"pytest_tool_{uuid.uuid4().hex[:12]}"
    object_name = f"{kb_id}/parsed/{file_id}.md"
    minio = get_minio_client()
    uploaded = await minio.aupload_file(
        MinIOClient.KB_BUCKETS["parsed"],
        object_name,
        b"First line\nNeedle in document\nLast line",
        content_type="text/markdown",
    )
    pg_manager.initialize()
    try:
        async with pg_manager.get_async_session_context() as session:
            kb = await session.scalar(select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id))
            assert kb is not None
            session.add(
                KnowledgeFile(
                    file_id=file_id,
                    kb_id=kb_id,
                    filename="tool-proof.md",
                    file_type="md",
                    markdown_file=uploaded.url,
                    status="parsed",
                    is_folder=False,
                )
            )
        yield file_id
    finally:
        await minio.adelete_file(MinIOClient.KB_BUCKETS["parsed"], object_name)
        await pg_manager.close()


async def test_jwt_can_call_five_read_only_knowledge_tools(test_client, admin_headers, knowledge_base_resource):
    """登录用户 JWT 可调用五个查询工具，缺失资源不会泄露。"""
    kb_id = knowledge_base_resource["kb_id"]
    prefix = "/api/v1/knowledge/tools"
    unauthenticated = await test_client.get(f"{prefix}/list_kbs")
    assert unauthenticated.status_code == 401, unauthenticated.text

    listed = await test_client.get(f"{prefix}/list_kbs", headers=admin_headers)
    assert listed.status_code == 200, listed.text
    assert any(item["kb_id"] == kb_id for item in listed.json())

    queried = await test_client.post(
        f"{prefix}/query_kb",
        json={"kb_id": kb_id, "query_text": "hello"},
        headers=admin_headers,
    )
    assert queried.status_code == 200, queried.text
    assert queried.json()["kb_id"] == kb_id

    removed = await test_client.post(f"{prefix}/get_mindmap", json={"kb_name": "any"}, headers=admin_headers)
    assert removed.status_code == 404

    searched = await test_client.post(
        f"{prefix}/search_file",
        json={"query": "missing-needle"},
        headers=admin_headers,
    )
    assert searched.status_code == 200, searched.text
    assert isinstance(searched.json()["files"], list)

    for name, payload, expected in (
        ("open_kb_document", {"kb_id": kb_id, "file_id": "missing-file"}, 400),
        ("find_kb_document", {"kb_id": kb_id, "file_id": "missing-file", "patterns": ["hello"]}, 400),
    ):
        response = await test_client.post(f"{prefix}/{name}", json=payload, headers=admin_headers)
        assert response.status_code == expected, (name, response.text)


async def test_document_tools_return_persisted_results(test_client, admin_headers, knowledge_base_resource, readable_knowledge_tool_data):
    """保留的文档工具经真实 HTTP 回读 PostgreSQL 和 MinIO 文档内容。"""
    kb_id = knowledge_base_resource["kb_id"]
    file_id = readable_knowledge_tool_data
    prefix = "/api/v1/knowledge/tools"

    searched = await test_client.post(
        f"{prefix}/search_file",
        json={"kb_id": kb_id, "query": "tool-proof"},
        headers=admin_headers,
    )
    assert searched.status_code == 200, searched.text
    [file] = searched.json()["files"]
    assert file["file_id"] == file_id
    assert file["kb_id"] == kb_id
    assert file["filename"] == "tool-proof.md"

    opened = await test_client.post(
        f"{prefix}/open_kb_document",
        json={"kb_id": kb_id, "file_id": file_id},
        headers=admin_headers,
    )
    assert opened.status_code == 200, opened.text
    assert opened.json()["file_id"] == file_id
    assert opened.json()["total_lines"] == 3
    assert "Needle in document" in opened.json()["content"]

    found = await test_client.post(
        f"{prefix}/find_kb_document",
        json={"kb_id": kb_id, "file_id": file_id, "patterns": ["Needle"]},
        headers=admin_headers,
    )
    assert found.status_code == 200, found.text
    assert found.json()["file_id"] == file_id
    assert found.json()["total_matches"] == 1
    assert "Needle in document" in found.json()["windows"][0]["content"]

    invalid_regex = await test_client.post(
        f"{prefix}/find_kb_document",
        json={"kb_id": kb_id, "file_id": file_id, "patterns": ["["], "use_regex": True},
        headers=admin_headers,
    )
    assert invalid_regex.status_code == 400, invalid_regex.text
    assert "无效正则表达式" in invalid_regex.json()["detail"]


async def test_knowledge_key_can_call_tools_but_not_unlisted_operations(
    test_client, knowledge_base_resource, api_key_factory
):
    """受限 Key 只进入列明的只读工具，下载与管理保持拒绝。"""
    created = await api_key_factory(
        {"request_id": str(uuid.uuid4()), "name": "Knowledge tools", "access_level": "knowledge"}
    )
    key_headers = created.headers
    kb_id = knowledge_base_resource["kb_id"]
    listed = await test_client.get("/api/v1/knowledge/tools/list_kbs", headers=key_headers)
    assert listed.status_code == 200, listed.text
    assert any(item["kb_id"] == kb_id for item in listed.json())

    queried = await test_client.post(
        "/api/v1/knowledge/tools/query_kb",
        json={"kb_id": kb_id, "query_text": "hello"},
        headers=key_headers,
    )
    assert queried.status_code == 200, queried.text

    for name, payload, expected in (
        ("open_kb_document", {"kb_id": kb_id, "file_id": "missing-file"}, 400),
        ("find_kb_document", {"kb_id": kb_id, "file_id": "missing-file", "patterns": ["hello"]}, 400),
        ("search_file", {"query": "missing-needle"}, 200),
    ):
        response = await test_client.post(f"/api/v1/knowledge/tools/{name}", json=payload, headers=key_headers)
        assert response.status_code == expected, (name, response.text)

    blocked = await test_client.post(
        "/api/v1/knowledge/tools/download_kb_file",
        json={"kb_id": kb_id, "file_id": "missing"},
        headers=key_headers,
    )
    assert blocked.status_code == 404, blocked.text
    blocked = await test_client.get("/api/knowledge/knowledge-bases", headers=key_headers)
    assert blocked.status_code == 403, blocked.text


async def test_tool_query_hides_invisible_knowledge_base(test_client, admin_headers, standard_user, api_key_factory):
    """私有库的已知 ID 对另一用户的查询与搜索均不可见。"""
    owner = await test_client.get("/api/auth/me", headers=admin_headers)
    assert owner.status_code == 200, owner.text
    created = await test_client.post(
        "/api/knowledge/knowledge-bases",
        json={
            "name": f"pytest_private_tool_{uuid.uuid4().hex[:8]}",
            "description": "private tool test",
            "embedding_model_spec": default_embedding_model_spec(),
            "kb_type": "milvus",
            "additional_params": {},
            "share_config": {
                "version": 2,
                "read_scope": {"access_level": "user", "department_ids": [], "user_uids": [owner.json()["uid"]]},
                "manage_scope": None,
            },
        },
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    kb_id = created.json()["kb_id"]
    try:
        owner_list = await test_client.get("/api/v1/knowledge/tools/list_kbs", headers=admin_headers)
        assert owner_list.status_code == 200, owner_list.text
        assert any(item.get("kb_id") == kb_id for item in owner_list.json())
        user_list = await test_client.get("/api/v1/knowledge/tools/list_kbs", headers=standard_user["headers"])
        assert user_list.status_code == 200, user_list.text
        assert all(item.get("kb_id") != kb_id for item in user_list.json())

        key_created = await api_key_factory(
            {
                "request_id": str(uuid.uuid4()),
                "name": "Restricted tool test",
                "access_level": "knowledge",
            },
            owner_headers=standard_user["headers"],
        )
        key_headers = key_created.headers
        credentials = (
            ("jwt", standard_user["headers"]),
            ("knowledge-key", key_headers),
        )
        for label, headers in credentials:
            listed = await test_client.get("/api/v1/knowledge/tools/list_kbs", headers=headers)
            assert listed.status_code == 200, (label, listed.text)
            assert all(item.get("kb_id") != kb_id for item in listed.json())
            for route, payload in (
                ("query_kb", {"kb_id": kb_id, "query_text": "hello"}),
                ("search_file", {"kb_id": kb_id}),
            ):
                response = await test_client.post(f"/api/v1/knowledge/tools/{route}", json=payload, headers=headers)
                assert response.status_code == 404, (label, route, response.text)
    finally:
        deleted = await test_client.delete(f"/api/knowledge/knowledge-bases/{kb_id}", headers=admin_headers)
        assert deleted.status_code == 200, deleted.text


async def test_tool_file_search_by_id_preserves_pagination(test_client, admin_headers, knowledge_base_resource):
    """按 ID 列文件可省略查询词，并保留分页与未知资源拒绝。"""
    kb_id = knowledge_base_resource["kb_id"]
    response = await test_client.post(
        "/api/v1/knowledge/tools/search_file",
        json={"kb_id": kb_id, "offset": 0, "limit": 100},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert isinstance(response.json()["files"], list)
    assert response.json()["offset"] == 0
    assert response.json()["limit"] == 100
    missing = await test_client.post(
        "/api/v1/knowledge/tools/search_file",
        json={"kb_id": "missing-kb", "query": "anything"},
        headers=admin_headers,
    )
    assert missing.status_code == 404, missing.text
