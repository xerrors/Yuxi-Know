"""
Integration tests for graph router endpoints.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_graph_routes_require_auth(test_client):
    response = await test_client.get("/api/graph/lightrag/databases")
    assert response.status_code == 401


async def test_standard_user_cannot_access_graph_endpoints(test_client, standard_user):
    response = await test_client.get("/api/graph/lightrag/databases", headers=standard_user["headers"])
    assert response.status_code == 403


async def test_admin_can_list_lightrag_databases(test_client, admin_headers, knowledge_database):
    response = await test_client.get("/api/graph/lightrag/databases", headers=admin_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    databases = payload["data"]["databases"]
    assert isinstance(databases, list)
    assert any(db["db_id"] == knowledge_database["db_id"] for db in databases)
