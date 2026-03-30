"""
Integration tests for authentication-related API routes.
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_login_with_invalid_credentials(test_client):
    response = await test_client.post("/api/auth/token", data={"username": "invalid", "password": "invalid"})
    assert response.status_code == 401
    assert "detail" in response.json()


async def test_admin_can_login_and_fetch_profile(test_client, admin_headers):
    profile_response = await test_client.get("/api/auth/me", headers=admin_headers)
    assert profile_response.status_code == 200
    data = profile_response.json()
    assert data["role"] in {"admin", "superadmin"}
    assert data["username"]
    assert data["user_id"]


async def test_admin_can_create_and_delete_user(test_client, admin_headers):
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "username": f"rtu_{suffix}",
        "password": "routerTest123!",
        "role": "user",
    }
    create_response = await test_client.post("/api/auth/users", json=payload, headers=admin_headers)
    assert create_response.status_code == 200, create_response.text

    created_user = create_response.json()
    assert created_user["username"] == payload["username"]
    assert created_user["role"] == payload["role"]

    delete_response = await test_client.delete(f"/api/auth/users/{created_user['id']}", headers=admin_headers)
    assert delete_response.status_code == 200, delete_response.text
    delete_payload = delete_response.json()
    assert delete_payload["success"] is True
    assert delete_payload["message"] == "用户已删除"


async def test_invalid_token_is_rejected(test_client):
    headers = {"Authorization": "Bearer not-a-real-token"}
    response = await test_client.get("/api/auth/me", headers=headers)
    assert response.status_code == 401
