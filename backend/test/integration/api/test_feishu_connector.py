"""飞书连接器经真实 HTTP 验证配置、凭据保护和权限拒绝。"""

import os
import uuid

import pytest
from sqlalchemy import text

pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.self_managed_resources]


async def test_feishu_connection_permissions_and_no_local_ingestion(test_client, admin_headers, standard_user, postgres_sessions):
    """连接配置持久化；凭据不回显，未授权用户不能借用其读取资源。"""
    me = await test_client.get("/api/auth/me", headers=admin_headers)
    owner_uid = me.json()["uid"]
    token = f"fake-secret-{uuid.uuid4().hex}"
    response = await test_client.post(
        "/api/knowledge/knowledge-bases",
        headers=admin_headers,
        json={
            "name": f"pytest_feishu_{uuid.uuid4().hex[:8]}",
            "description": "Feishu readonly connection",
            "kb_type": "feishu",
            "additional_params": {"feishu_user_token": token, "feishu_space_id": "123"},
            "share_config": {"version": 2, "read_scope": {"access_level": "user", "user_uids": [owner_uid]}, "manage_scope": None},
        },
    )
    assert response.status_code == 200, response.text
    assert token not in response.text
    kb_id = response.json()["kb_id"]
    try:
        detail = await test_client.get(f"/api/knowledge/knowledge-bases/{kb_id}", headers=admin_headers)
        assert detail.status_code == 200, detail.text
        assert token not in detail.text
        assert detail.json()["additional_params"]["feishu_space_id"] == "123"
        async with postgres_sessions() as session:
            saved = (
                await session.execute(text("SELECT additional_params FROM knowledge_bases WHERE kb_id=:kb_id"), {"kb_id": kb_id})
            ).scalar_one()
            assert saved["feishu_user_token"] == token
            count = (await session.execute(text("SELECT count(*) FROM knowledge_files WHERE kb_id=:kb_id"), {"kb_id": kb_id})).scalar_one()
            assert count == 0
        for tool, payload in (
            ("query_kb", {"query_text": "anything"}),
            ("open_kb_document", {"file_id": "ArbitraryNode"}),
        ):
            denied = await test_client.post(
                f"/api/v1/knowledge/tools/{tool}", headers=standard_user["headers"], json={"kb_id": kb_id, **payload}
            )
            assert denied.status_code == 404, denied.text
            assert token not in denied.text
        upload = await test_client.post(
            f"/api/knowledge/knowledge-bases/{kb_id}/documents/add",
            headers=admin_headers,
            json={"items": ["not-a-local-file"]},
        )
        assert upload.status_code == 400, upload.text
        assert "不支持" in upload.text
        updated = await test_client.put(
            f"/api/knowledge/knowledge-bases/{kb_id}",
            headers=admin_headers,
            json={"name": response.json()["name"], "description": "Updated connection", "additional_params": {"feishu_space_id": "456"}},
        )
        assert updated.status_code == 200, updated.text
        assert token not in updated.text
        async with postgres_sessions() as session:
            saved = (
                await session.execute(text("SELECT additional_params FROM knowledge_bases WHERE kb_id=:kb_id"), {"kb_id": kb_id})
            ).scalar_one()
            assert saved["feishu_user_token"] == token
            assert saved["feishu_space_id"] == "456"
    finally:
        deleted = await test_client.delete(f"/api/knowledge/knowledge-bases/{kb_id}", headers=admin_headers)
        assert deleted.status_code == 200, deleted.text


async def test_feishu_live_search_and_read(test_client, admin_headers, postgres_sessions):
    """使用显式传入的测试凭证回读远端文档，最后确认未产生本地文件。"""
    token = os.environ.get("FEISHU_TEST_USER_TOKEN")
    space_id = os.environ.get("FEISHU_TEST_SPACE_ID")
    query = os.environ.get("FEISHU_TEST_QUERY")
    expected = os.environ.get("FEISHU_TEST_EXPECTED_TEXT")
    if not all((token, space_id, query, expected)):
        pytest.skip("真实飞书测试需显式提供 FEISHU_TEST_USER_TOKEN、SPACE_ID、QUERY、EXPECTED_TEXT")
    me = await test_client.get("/api/auth/me", headers=admin_headers)
    owner_uid = me.json()["uid"]
    created = await test_client.post(
        "/api/knowledge/knowledge-bases",
        headers=admin_headers,
        json={
            "name": f"pytest_feishu_live_{uuid.uuid4().hex[:8]}",
            "description": "Live readonly probe",
            "kb_type": "feishu",
            "additional_params": {"feishu_user_token": token, "feishu_space_id": space_id},
            "share_config": {"version": 2, "read_scope": {"access_level": "user", "user_uids": [owner_uid]}, "manage_scope": None},
        },
    )
    assert created.status_code == 200, f"创建失败: HTTP {created.status_code}"
    assert token not in created.text
    kb_id = created.json()["kb_id"]
    try:
        searched = await test_client.post(
            "/api/v1/knowledge/tools/query_kb", headers=admin_headers, json={"kb_id": kb_id, "query_text": query}
        )
        assert searched.status_code == 200, searched.text
        results = searched.json()["results"]
        assert results
        read = await test_client.post(
            "/api/v1/knowledge/tools/open_kb_document",
            headers=admin_headers,
            json={"kb_id": kb_id, "file_id": results[0]["file_id"]},
        )
        assert read.status_code == 200, read.text
        assert expected in read.json()["content"]
        async with postgres_sessions() as session:
            count = (await session.execute(text("SELECT count(*) FROM knowledge_files WHERE kb_id=:kb_id"), {"kb_id": kb_id})).scalar_one()
            assert count == 0
    finally:
        deleted = await test_client.delete(f"/api/knowledge/knowledge-bases/{kb_id}", headers=admin_headers)
        assert deleted.status_code == 200, deleted.text
