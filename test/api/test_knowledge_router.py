"""
Integration tests for knowledge router endpoints.
"""

from __future__ import annotations

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

    forbidden_get = await test_client.get(
        f"/api/knowledge/databases/{db_id}", headers=standard_user["headers"]
    )
    assert forbidden_get.status_code == 403
