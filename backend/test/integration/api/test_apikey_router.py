"""
Integration tests for API Key router endpoints.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from types import SimpleNamespace

from yuxi.modules.identity.repositories.oidc import OIDCRepository
from yuxi.modules.identity.models import OIDCIdentity
from yuxi.shared.errors import PermissionDeniedError
from yuxi.modules.identity.models import APIKey, User

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

API_KEYS_PATH = "/api/user/apikey/"
# 受登录保护的轻量端点，用于验证 Bearer 鉴权（API Key / JWT）是否生效，无需执行智能体
PROTECTED_PATH = "/api/agent"


def _create_payload(name: str) -> dict[str, str]:
    return {"request_id": str(uuid.uuid4()), "name": name}


async def test_list_api_keys_requires_auth(test_client):
    """List API keys should require authentication."""
    response = await test_client.get(API_KEYS_PATH)
    assert response.status_code == 401


async def test_list_api_keys_requires_admin(test_client, admin_headers):
    """List API keys should require admin privileges."""
    response = await test_client.get(API_KEYS_PATH, headers=admin_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert "api_keys" in data
    assert "total" in data


async def test_create_api_key(test_client, admin_headers):
    """Admin should be able to create a new API key."""
    payload = _create_payload("Test API Key")
    response = await test_client.post(API_KEYS_PATH, json=payload, headers=admin_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert "api_key" in data
    assert "secret" in data
    assert data["api_key"]["name"] == "Test API Key"
    assert data["api_key"]["key_prefix"].startswith("yxkey_")
    assert data["secret"].startswith(data["api_key"]["key_prefix"])

    replay = await test_client.post(API_KEYS_PATH, json=payload, headers=admin_headers)
    assert replay.status_code == 200, replay.text
    assert replay.json() == data

    conflict = await test_client.post(
        API_KEYS_PATH,
        json={**payload, "name": "Different intent"},
        headers=admin_headers,
    )
    assert conflict.status_code == 409, conflict.text


async def test_concurrent_create_replays_one_committed_api_key(test_client, admin_headers):
    """同一幂等请求并发到达时只提交一行，并向双方发布同一 secret。"""

    payload = _create_payload("Concurrent Replay")
    responses = await asyncio.gather(
        test_client.post(API_KEYS_PATH, json=payload, headers=admin_headers),
        test_client.post(API_KEYS_PATH, json=payload, headers=admin_headers),
    )

    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    created = responses[0].json()

    engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            row_count = await db.scalar(select(func.count(APIKey.id)).where(APIKey.request_id == payload["request_id"]))
        assert row_count == 1
    finally:
        await engine.dispose()
        await test_client.delete(f"{API_KEYS_PATH}{created['api_key']['id']}", headers=admin_headers)


async def test_get_api_key(test_client, admin_headers):
    """Admin should be able to get a single API key."""
    # First create a key
    create_response = await test_client.post(API_KEYS_PATH, json=_create_payload("Get Test"), headers=admin_headers)
    assert create_response.status_code == 200
    created = create_response.json()["api_key"]

    # Then retrieve it
    response = await test_client.get(f"{API_KEYS_PATH}{created['id']}", headers=admin_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["api_key"]["id"] == created["id"]
    assert data["api_key"]["name"] == "Get Test"


async def test_update_api_key(test_client, admin_headers):
    """Admin should be able to update an API key."""
    # Create a key
    create_response = await test_client.post(API_KEYS_PATH, json=_create_payload("Update Test"), headers=admin_headers)
    assert create_response.status_code == 200
    created = create_response.json()["api_key"]

    # Update it
    response = await test_client.put(
        f"{API_KEYS_PATH}{created['id']}",
        json={"name": "Updated Name", "is_enabled": False},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["api_key"]["name"] == "Updated Name"
    assert data["api_key"]["is_enabled"] is False


async def test_original_creation_intent_remains_replayable_after_mutable_fields_change(test_client, admin_headers):
    payload = _create_payload("Original Intent")
    create_response = await test_client.post(API_KEYS_PATH, json=payload, headers=admin_headers)
    assert create_response.status_code == 200, create_response.text
    created = create_response.json()

    update_response = await test_client.put(
        f"{API_KEYS_PATH}{created['api_key']['id']}",
        json={"name": "Renamed Later"},
        headers=admin_headers,
    )
    assert update_response.status_code == 200, update_response.text

    replay_response = await test_client.post(API_KEYS_PATH, json=payload, headers=admin_headers)
    assert replay_response.status_code == 200, replay_response.text
    assert replay_response.json()["secret"] == created["secret"]
    assert replay_response.json()["api_key"]["id"] == created["api_key"]["id"]
    assert replay_response.json()["api_key"]["name"] == "Renamed Later"

    await test_client.delete(f"{API_KEYS_PATH}{created['api_key']['id']}", headers=admin_headers)


async def test_delete_api_key(test_client, admin_headers):
    """Admin should be able to delete an API key."""
    # Create a key
    create_response = await test_client.post(API_KEYS_PATH, json=_create_payload("Delete Test"), headers=admin_headers)
    assert create_response.status_code == 200
    created = create_response.json()["api_key"]

    # Delete it
    response = await test_client.delete(f"{API_KEYS_PATH}{created['id']}", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()["success"] is True

    # Verify it's gone
    get_response = await test_client.get(f"{API_KEYS_PATH}{created['id']}", headers=admin_headers)
    assert get_response.status_code == 404


async def test_revoked_api_key_cannot_be_resurrected_by_replaying_creation_request(test_client, admin_headers):
    payload = _create_payload("Revocation Tombstone")
    create_response = await test_client.post(API_KEYS_PATH, json=payload, headers=admin_headers)
    assert create_response.status_code == 200, create_response.text
    secret = create_response.json()["secret"]
    api_key_id = create_response.json()["api_key"]["id"]

    delete_response = await test_client.delete(f"{API_KEYS_PATH}{api_key_id}", headers=admin_headers)
    assert delete_response.status_code == 200, delete_response.text

    replay_response = await test_client.post(API_KEYS_PATH, json=payload, headers=admin_headers)
    assert replay_response.status_code == 409, replay_response.text
    assert "secret" not in replay_response.text.lower()

    auth_response = await test_client.get(PROTECTED_PATH, headers={"Authorization": f"Bearer {secret}"})
    assert auth_response.status_code == 401, auth_response.text


async def test_user_delete_blocks_oidc_login_and_old_api_key(test_client, admin_headers):
    """删除用户阻断已绑定 OIDC 登录，已撤销 Key 不能重发或启用。"""

    suffix = uuid.uuid4().hex[:12]
    user_response = await test_client.post(
        "/api/auth/users",
        json={"username": f"revive_{suffix}", "password": "routerTest123!", "role": "user"},
        headers=admin_headers,
    )
    assert user_response.status_code == 200, user_response.text
    user_id = user_response.json()["id"]
    payload = {**_create_payload("Deleted User Tombstone"), "user_id": user_id}
    create_response = await test_client.post(API_KEYS_PATH, json=payload, headers=admin_headers)
    assert create_response.status_code == 200, create_response.text
    created = create_response.json()
    api_key_id = created["api_key"]["id"]
    secret = created["secret"]
    engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with factory() as db:
            db.add(OIDCIdentity(issuer="https://identity.example.test", subject=f"test:{suffix}", user_id=user_id))
            await db.commit()
        delete_response = await test_client.delete(f"/api/auth/users/{user_id}", headers=admin_headers)
        assert delete_response.status_code == 200, delete_response.text

        async with factory() as db:
            deleted_user = await db.get(User, user_id)
            persisted_key = await db.get(APIKey, api_key_id)
            assert deleted_user is not None and deleted_user.is_deleted == 1
            assert persisted_key is not None and persisted_key.is_enabled is False
            assert persisted_key.revoked_at is not None
            with pytest.raises(PermissionDeniedError):
                await OIDCRepository(db).resolve_user(
                    SimpleNamespace(issuer_url="https://identity.example.test"),
                    {"sub": f"test:{suffix}"},
                    {},
                )

        list_response = await test_client.get(API_KEYS_PATH, headers=admin_headers)
        assert list_response.status_code == 200, list_response.text
        assert api_key_id not in {item["id"] for item in list_response.json()["api_keys"]}

        replay_response = await test_client.post(API_KEYS_PATH, json=payload, headers=admin_headers)
        assert replay_response.status_code == 404, replay_response.text
        assert "secret" not in replay_response.json()

        enable_response = await test_client.put(
            f"{API_KEYS_PATH}{api_key_id}",
            json={"is_enabled": True},
            headers=admin_headers,
        )
        assert enable_response.status_code == 404, enable_response.text

        auth_response = await test_client.get(PROTECTED_PATH, headers={"Authorization": f"Bearer {secret}"})
        assert auth_response.status_code == 401, auth_response.text

        async with factory() as db:
            persisted_key = await db.get(APIKey, api_key_id)
            assert persisted_key is not None and persisted_key.revoked_at is not None
            assert persisted_key.is_enabled is False
    finally:
        async with factory() as db:
            await db.execute(delete(APIKey).where(APIKey.id == api_key_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()
        await engine.dispose()


async def test_api_key_auth_protected_endpoint(test_client, admin_headers):
    """Test that API Key can be used to authenticate to a protected endpoint via Bearer token."""
    # Create an API key
    create_response = await test_client.post(API_KEYS_PATH, json=_create_payload("Auth Test"), headers=admin_headers)
    assert create_response.status_code == 200
    api_key_secret = create_response.json()["secret"]
    created = create_response.json()["api_key"]

    try:
        response = await test_client.get(
            PROTECTED_PATH,
            headers={"Authorization": f"Bearer {api_key_secret}"},
        )
        assert response.status_code == 200, response.text
    finally:
        # Cleanup: delete the test API key
        await test_client.delete(f"{API_KEYS_PATH}{created['id']}", headers=admin_headers)


async def test_api_key_auth_requires_valid_key(test_client):
    """Test that invalid API Key is rejected."""
    # Call protected endpoint with invalid API Key
    response = await test_client.get(
        PROTECTED_PATH,
        headers={"Authorization": "Bearer yxkey_invalid_key_that_does_not_exist"},
    )
    assert response.status_code == 401, response.text


async def test_api_key_auth_requires_bearer_prefix(test_client, admin_headers):
    """Test that API Key must be prefixed with 'Bearer '."""
    # Create an API key
    admin_response = await test_client.post(API_KEYS_PATH, json=_create_payload("Prefix Test"), headers=admin_headers)
    assert admin_response.status_code == 200
    api_key_secret = admin_response.json()["secret"]
    created = admin_response.json()["api_key"]

    try:
        # Call without Bearer prefix should fail
        response = await test_client.get(
            PROTECTED_PATH,
            headers={"Authorization": api_key_secret},  # Missing "Bearer " prefix
        )
        assert response.status_code == 401, response.text
    finally:
        # Cleanup: delete the test API key
        await test_client.delete(f"{API_KEYS_PATH}{created['id']}", headers=admin_headers)


async def test_api_key_auto_binds_to_current_user(test_client, admin_headers):
    """Test that API Key created without user_id is auto-bound to creator."""
    # Create API key as admin
    create_response = await test_client.post(
        API_KEYS_PATH,
        json=_create_payload("Auto Bind Test"),
        headers=admin_headers,
    )
    assert create_response.status_code == 200
    created = create_response.json()["api_key"]

    try:
        # Verify user_id is set (auto-bound to admin)
        assert created["user_id"] is not None, "API Key should be auto-bound to creator"
    finally:
        # Cleanup: delete the test API key
        await test_client.delete(f"{API_KEYS_PATH}{created['id']}", headers=admin_headers)
