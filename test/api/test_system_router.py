"""
Integration tests for system router endpoints.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_health_endpoint_is_public(test_client):
    response = await test_client.get("/api/system/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_info_endpoint_is_public(test_client):
    response = await test_client.get("/api/system/info")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "data" in payload


async def test_config_endpoints_require_admin(test_client, standard_user):
    assert (await test_client.get("/api/system/config")).status_code == 401
    assert (await test_client.get("/api/system/config", headers=standard_user["headers"])).status_code == 403


async def test_admin_can_fetch_config_and_reload_info(test_client, admin_headers):
    config_response = await test_client.get("/api/system/config", headers=admin_headers)
    assert config_response.status_code == 200, config_response.text
    assert isinstance(config_response.json(), dict)

    reload_response = await test_client.post("/api/system/info/reload", headers=admin_headers)
    assert reload_response.status_code == 200, reload_response.text
    reload_payload = reload_response.json()
    assert reload_payload["success"] is True
    assert "data" in reload_payload
