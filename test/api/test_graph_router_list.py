"""
Integration tests for graph router list endpoint.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_admin_can_list_graphs(test_client, admin_headers):
    """Test that listing graphs returns 200 and a list of graphs."""
    response = await test_client.get("/api/graph/list", headers=admin_headers)
    assert response.status_code == 200, f"Failed to list graphs: {response.text}"
    data = response.json()

    # Check if response is wrapped
    if isinstance(data, dict) and "data" in data:
        graphs = data["data"]
    else:
        graphs = data

    assert isinstance(graphs, list)
    # Check structure of returned items if list is not empty
    if graphs:
        item = graphs[0]
        assert "id" in item
        assert "name" in item
        assert "type" in item
