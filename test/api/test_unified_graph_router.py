"""
Integration tests for the unified graph router endpoints.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_graph_routes_require_auth(test_client):
    """Test that graph endpoints require authentication."""
    response = await test_client.get("/api/graph/list")
    assert response.status_code == 401


async def test_standard_user_cannot_access_graph_endpoints(test_client, standard_user):
    """Test that standard users cannot access graph endpoints."""
    response = await test_client.get("/api/graph/list", headers=standard_user["headers"])
    assert response.status_code == 403


async def test_get_graphs_list(test_client, admin_headers):
    """Test retrieving the list of all graphs."""
    response = await test_client.get("/api/graph/list", headers=admin_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    graphs = payload["data"]
    assert isinstance(graphs, list)

    # Check for Neo4j default graph
    neo4j_graph = next((g for g in graphs if g["id"] == "neo4j"), None)
    assert neo4j_graph is not None
    assert neo4j_graph["type"] == "neo4j"

    # Note: LightRAG graphs might be empty if none created, but we check structure


async def test_get_subgraph_neo4j(test_client, admin_headers):
    """Test unified subgraph query for Neo4j."""
    # Query with a wildcard or a known node. Using "*" to get a sample.
    response = await test_client.get(
        "/api/graph/subgraph", params={"db_id": "neo4j", "node_label": "*", "max_nodes": 10}, headers=admin_headers
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert "nodes" in data
    assert "edges" in data
    assert isinstance(data["nodes"], list)


async def test_get_subgraph_lightrag(test_client, admin_headers, knowledge_database):
    """Test unified subgraph query for LightRAG."""
    db_id = knowledge_database["db_id"]
    response = await test_client.get(
        "/api/graph/subgraph", params={"db_id": db_id, "node_label": "*", "max_nodes": 10}, headers=admin_headers
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert "nodes" in data
    assert "edges" in data


async def test_get_stats_neo4j(test_client, admin_headers):
    """Test stats endpoint for Neo4j."""
    response = await test_client.get("/api/graph/stats", params={"db_id": "neo4j"}, headers=admin_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert "total_nodes" in data
    assert "total_edges" in data
    assert "entity_types" in data


async def test_get_stats_lightrag(test_client, admin_headers, knowledge_database):
    """Test stats endpoint for LightRAG."""
    db_id = knowledge_database["db_id"]
    response = await test_client.get("/api/graph/stats", params={"db_id": db_id}, headers=admin_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert "total_nodes" in data
    assert "total_edges" in data
    assert "entity_types" in data


async def test_get_labels_neo4j(test_client, admin_headers):
    """Test labels endpoint for Neo4j."""
    response = await test_client.get("/api/graph/labels", params={"db_id": "neo4j"}, headers=admin_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert "labels" in data
    assert isinstance(data["labels"], list)


async def test_deprecated_neo4j_endpoints(test_client, admin_headers):
    """Verify deprecated endpoints still work and return correct structure."""

    # /neo4j/nodes
    response = await test_client.get(
        "/api/graph/neo4j/nodes", params={"kgdb_name": "neo4j", "num": 5}, headers=admin_headers
    )
    assert response.status_code == 200
    payload = response.json()
    # Check compatibility structure
    assert payload["success"] is True
    assert "result" in payload
    assert payload["message"] == "success"
    assert "nodes" in payload["result"]

    # /neo4j/node
    # This might return empty if "NonExistentEntity" doesn't exist, but structure should be valid
    response = await test_client.get(
        "/api/graph/neo4j/node", params={"entity_name": "NonExistentEntity"}, headers=admin_headers
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "result" in payload
    assert payload["message"] == "success"
