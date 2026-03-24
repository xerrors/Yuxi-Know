"""
Integration tests for settings router endpoints.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_reranker_list_requires_admin(test_client, standard_user):
    public_response = await test_client.get("/api/settings/rerankers")
    assert public_response.status_code == 401

    forbidden_response = await test_client.get("/api/settings/rerankers", headers=standard_user["headers"])
    assert forbidden_response.status_code == 403


async def test_admin_can_list_rerankers(test_client, admin_headers):
    response = await test_client.get("/api/settings/rerankers", headers=admin_headers)
    assert response.status_code == 200, response.text
    payload = response.json()

    assert "rerankers" in payload
    assert isinstance(payload["rerankers"], dict)
