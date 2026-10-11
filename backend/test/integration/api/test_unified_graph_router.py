from __future__ import annotations

import uuid

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _create_dify_database(test_client, admin_headers) -> str:
    response = await test_client.post(
        "/api/knowledge/knowledge-bases",
        json={
            "name": f"pytest_graph_dify_{uuid.uuid4().hex[:8]}",
            "description": "Graph router Dify negative test",
            "kb_type": "dify",
            "additional_params": {
                "dify_api_url": "https://api.dify.ai/v1",
                "dify_token": "test-token",
                "dify_dataset_id": f"dataset-{uuid.uuid4().hex[:8]}",
            },
        },
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["kb_id"]


async def _delete_database(test_client, admin_headers, kb_id: str) -> None:
    await test_client.delete(f"/api/knowledge/knowledge-bases/{kb_id}", headers=admin_headers)


async def test_graph_routes_require_auth(test_client):
    response = await test_client.get("/api/graph/list")
    assert response.status_code == 401


async def test_standard_user_cannot_access_graph_endpoints(test_client, standard_user):
    response = await test_client.get("/api/graph/list", headers=standard_user["headers"])
    assert response.status_code == 403


async def test_get_graphs_list_only_returns_milvus(test_client, admin_headers, knowledge_base_resource):
    response = await test_client.get("/api/graph/list", headers=admin_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert isinstance(payload["data"], list)
    assert payload["data"]
    assert all(graph["type"] == "milvus" for graph in payload["data"])
    assert any(graph["id"] == knowledge_base_resource["kb_id"] for graph in payload["data"])


@pytest.mark.parametrize("path", ["/api/graph/subgraph", "/api/graph/stats", "/api/graph/labels"])
async def test_graph_endpoints_reject_non_milvus_types(test_client, admin_headers, path):
    kb_id = await _create_dify_database(test_client, admin_headers)
    try:
        response = await test_client.get(path, params={"kb_id": kb_id}, headers=admin_headers)
    finally:
        await _delete_database(test_client, admin_headers, kb_id)

    assert response.status_code == 404
    assert "only supports Milvus" in response.text


@pytest.mark.parametrize(
    ("path", "params", "expected_keys"),
    [
        ("/api/graph/subgraph", {"node_label": "*", "max_nodes": 10}, ("nodes", "edges")),
        ("/api/graph/stats", {}, ("total_nodes", "total_edges", "entity_types")),
        ("/api/graph/labels", {}, ("labels",)),
    ],
)
async def test_milvus_graph_endpoints(test_client, admin_headers, knowledge_base_resource, path, params, expected_keys):
    response = await test_client.get(
        path,
        params={"kb_id": knowledge_base_resource["kb_id"], **params},
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    for key in expected_keys:
        assert key in payload["data"]
