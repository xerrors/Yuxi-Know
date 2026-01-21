"""
Integration tests for dashboard router endpoints.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_dashboard_requires_authentication(test_client):
    response = await test_client.get("/api/dashboard/conversations")
    assert response.status_code == 401


async def test_standard_user_is_forbidden(test_client, standard_user):
    response = await test_client.get("/api/dashboard/conversations", headers=standard_user["headers"])
    assert response.status_code == 403


async def test_admin_can_fetch_conversations(test_client, admin_headers):
    response = await test_client.get("/api/dashboard/conversations", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)


async def test_admin_can_fetch_stats(test_client, admin_headers):
    """Test that all stats endpoints return 200 and don't crash on DB queries."""

    # Test call timeseries stats for all types
    types = ["models", "agents", "tokens", "tools"]
    for stats_type in types:
        response = await test_client.get(
            f"/api/dashboard/stats/calls/timeseries?type={stats_type}&time_range=14days", headers=admin_headers
        )
        assert response.status_code == 200, f"{stats_type} stats failed: {response.text}"
        data = response.json()
        assert "data" in data
        assert "categories" in data

    # Test user activity stats
    response = await test_client.get("/api/dashboard/stats/users", headers=admin_headers)
    assert response.status_code == 200, f"user stats failed: {response.text}"
    assert "total_users" in response.json()

    # Test tool call stats
    response = await test_client.get("/api/dashboard/stats/tools", headers=admin_headers)
    assert response.status_code == 200, f"tool stats failed: {response.text}"
    assert "total_calls" in response.json()


async def test_admin_can_fetch_feedbacks(test_client, admin_headers):
    """Test that feedback endpoint returns 200 and handles the User join correctly."""
    response = await test_client.get("/api/dashboard/feedbacks", headers=admin_headers)
    assert response.status_code == 200, f"feedbacks failed: {response.text}"
    assert isinstance(response.json(), list)
