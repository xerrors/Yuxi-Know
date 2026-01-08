"""
Integration tests for knowledge router endpoints.
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_admin_can_manage_knowledge_databases(test_client, admin_headers, knowledge_database):
    db_id = knowledge_database["db_id"]

    list_response = await test_client.get("/api/knowledge/databases", headers=admin_headers)
    assert list_response.status_code == 200, list_response.text
    databases = list_response.json().get("databases", [])
    assert any(entry["db_id"] == db_id for entry in databases)

    get_response = await test_client.get(f"/api/knowledge/databases/{db_id}", headers=admin_headers)
    assert get_response.status_code == 200, get_response.text
    assert get_response.json()["db_id"] == db_id

    update_response = await test_client.put(
        f"/api/knowledge/databases/{db_id}",
        json={"name": knowledge_database["name"], "description": "Updated by pytest"},
        headers=admin_headers,
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["database"]["description"] == "Updated by pytest"


async def test_knowledge_routes_enforce_permissions(test_client, standard_user, knowledge_database):
    db_id = knowledge_database["db_id"]

    forbidden_create = await test_client.post(
        "/api/knowledge/databases",
        json={
            "database_name": "unauthorized_db",
            "description": "Should not succeed",
            "embed_model_name": "siliconflow/BAAI/bge-m3",
        },
        headers=standard_user["headers"],
    )
    assert forbidden_create.status_code == 403

    forbidden_list = await test_client.get("/api/knowledge/databases", headers=standard_user["headers"])
    assert forbidden_list.status_code == 403

    forbidden_get = await test_client.get(f"/api/knowledge/databases/{db_id}", headers=standard_user["headers"])
    assert forbidden_get.status_code == 403


async def test_admin_can_create_vector_db_with_reranker(test_client, admin_headers):
    """测试创建向量库并配置 reranker 参数（通过 query_params.options）"""
    db_name = f"pytest_rerank_{uuid.uuid4().hex[:6]}"
    payload = {
        "database_name": db_name,
        "description": "Vector DB with reranker",
        "embed_model_name": "siliconflow/BAAI/bge-m3",
        "kb_type": "milvus",
        "additional_params": {},
    }

    create_response = await test_client.post("/api/knowledge/databases", json=payload, headers=admin_headers)
    assert create_response.status_code == 200, create_response.text

    db_payload = create_response.json()
    db_id = db_payload["db_id"]

    try:
        # 获取查询参数配置
        params_response = await test_client.get(f"/api/knowledge/databases/{db_id}/query-params", headers=admin_headers)
        assert params_response.status_code == 200, params_response.text

        params_payload = params_response.json()
        options = params_payload.get("params", {}).get("options", [])
        option_keys = {option.get("key") for option in options}

        # 验证新的参数名称
        assert "final_top_k" in option_keys
        assert "use_reranker" in option_keys
        assert "recall_top_k" in option_keys
        assert "reranker_model" in option_keys

        # 验证参数配置
        final_top_k_option = next((opt for opt in options if opt.get("key") == "final_top_k"), None)
        assert final_top_k_option is not None
        assert final_top_k_option.get("default") == 10

        use_reranker_option = next((opt for opt in options if opt.get("key") == "use_reranker"), None)
        assert use_reranker_option is not None
        assert use_reranker_option.get("default") is False

        # 保存查询参数（模拟前端配置）
        update_params = {
            "final_top_k": 5,
            "use_reranker": True,
            "recall_top_k": 20,
        }
        update_response = await test_client.put(
            f"/api/knowledge/databases/{db_id}/query-params", json=update_params, headers=admin_headers
        )
        assert update_response.status_code == 200, update_response.text

        # 再次获取参数，验证保存成功
        params_response2 = await test_client.get(
            f"/api/knowledge/databases/{db_id}/query-params", headers=admin_headers
        )
        assert params_response2.status_code == 200, params_response2.text

        params_payload2 = params_response2.json()
        options2 = params_payload2.get("params", {}).get("options", [])

        # 验证保存的值
        final_top_k_option2 = next((opt for opt in options2 if opt.get("key") == "final_top_k"), None)
        assert final_top_k_option2 is not None
        assert final_top_k_option2.get("default") == 5  # 保存的值

        use_reranker_option2 = next((opt for opt in options2 if opt.get("key") == "use_reranker"), None)
        assert use_reranker_option2 is not None
        assert use_reranker_option2.get("default") is True  # 保存的值

    finally:
        await test_client.delete(f"/api/knowledge/databases/{db_id}", headers=admin_headers)
