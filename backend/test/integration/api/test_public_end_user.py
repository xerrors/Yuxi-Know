"""真实 HTTP 与 PostgreSQL 验证 Public API 终端用户身份边界。"""

from __future__ import annotations

import asyncio
import os
import uuid

import asyncpg
import pytest

from yuxi.modules.identity.security import AuthUtils

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_public_end_user_identity_is_unique_and_cannot_enter_product_api(test_client, admin_headers, api_key_factory):
    """并发同身份只建一行；不同 APP 隔离；特殊用户无产品凭据。"""
    me = await test_client.get("/api/auth/me", headers=admin_headers)
    assert me.status_code == 200, me.text
    owner_id = me.json()["id"]
    marker = uuid.uuid4().hex
    app_ids = [f"end-user-a-{marker}", f"end-user-b-{marker}"]
    external_id = f"visitor-{marker}"
    conn = await asyncpg.connect(os.environ["POSTGRES_URL"].replace("+asyncpg", ""))
    try:
        headers_by_app = []
        for app_id in app_ids:
            created = await api_key_factory(
                {
                    "request_id": str(uuid.uuid4()),
                    "name": "Public end user integration",
                    "access_level": "agents",
                    "app_id": app_id,
                }
            )
            headers_by_app.append({**created.headers, "X-End-User-Id": external_id})

        responses = await asyncio.gather(*(test_client.get("/api/v1/agents", headers=headers_by_app[0]) for _ in range(6)))
        assert all(response.status_code == 200 for response in responses), [response.text for response in responses]
        other_app = await test_client.get("/api/v1/agents", headers=headers_by_app[1])
        assert other_app.status_code == 200, other_app.text
        invalid = await test_client.get("/api/v1/agents", headers={**headers_by_app[0], "X-End-User-Id": ""})
        assert invalid.status_code == 422, invalid.text

        rows = await conn.fetch(
            """
            SELECT id, uid, username, role, user_kind, owner_user_id, app_id, end_user_id, department_id
            FROM users WHERE owner_user_id = $1 AND end_user_id = $2 ORDER BY app_id
            """,
            owner_id,
            external_id,
        )
        assert len(rows) == 2, rows
        assert {row["app_id"] for row in rows} == set(app_ids)
        assert len({row["uid"] for row in rows}) == 2
        assert all(row["role"] == "user" and row["user_kind"] == "end_user" for row in rows)
        assert all(row["department_id"] is None for row in rows)

        expected_uids = await conn.fetch("SELECT uid FROM users WHERE is_deleted = 0 AND user_kind = 'human' ORDER BY id")
        for endpoint in ("/api/auth/users", "/api/auth/users/access-options"):
            directory_uids = []
            for skip in range(0, len(expected_uids) + 2, 2):
                directory = await test_client.get(endpoint, headers=admin_headers, params={"skip": skip, "limit": 2})
                assert directory.status_code == 200, directory.text
                items = directory.json()
                directory_uids.extend(item["uid"] for item in items)
                if len(items) < 2:
                    break
            assert directory_uids == [row["uid"] for row in expected_uids]

        occupied_name = f"visitor_{marker[:12]}"
        await conn.execute("UPDATE users SET username = $1 WHERE id = $2", occupied_name, rows[0]["id"])
        duplicate = await test_client.post(
            "/api/auth/users",
            headers=admin_headers,
            json={"username": occupied_name, "password": "Duplicate-test-password-123", "role": "user"},
        )
        assert duplicate.status_code == 400, duplicate.text
        assert duplicate.json()["detail"] == "用户名已存在"

        hidden = await test_client.get("/api/auth/users/page", headers=admin_headers, params={"search": rows[0]["uid"]})
        assert hidden.status_code == 200, hidden.text
        assert hidden.json()["total"] == 0
        assert hidden.json()["items"] == []
        for kind in ("end_user", "all"):
            visible = await test_client.get(
                "/api/auth/users/page",
                headers=admin_headers,
                params={"search": rows[0]["uid"], "user_kind": kind, "limit": 1},
            )
            assert visible.status_code == 200, visible.text
            page = visible.json()
            assert page["total"] == 1
            assert [(item["id"], item["user_kind"], item["app_id"]) for item in page["items"]] == [
                (rows[0]["id"], "end_user", rows[0]["app_id"])
            ]
        invalid_kind = await test_client.get("/api/auth/users/page", headers=admin_headers, params={"user_kind": "unknown"})
        assert invalid_kind.status_code == 422, invalid_kind.text

        end_user = rows[0]
        login = await test_client.post("/api/auth/token", data={"username": end_user["uid"], "password": "not-a-password"})
        assert login.status_code == 401, login.text
        impersonate = await test_client.post(f"/api/auth/impersonate/{end_user['id']}", headers=admin_headers)
        assert impersonate.status_code == 404, impersonate.text
        product_token = AuthUtils.create_access_token({"sub": str(end_user["id"])})
        product = await test_client.get("/api/agent", headers={"Authorization": f"Bearer {product_token}"})
        assert product.status_code == 403, product.text
        new_key = await test_client.post(
            "/api/user/apikey/",
            headers=admin_headers,
            json={"request_id": str(uuid.uuid4()), "name": "Forbidden end user key", "user_id": end_user["id"]},
        )
        assert new_key.status_code == 404, new_key.text

        await conn.execute("UPDATE users SET is_deleted = 1, deleted_at = NOW() WHERE id = $1", end_user["id"])
        disabled = await test_client.get("/api/v1/agents", headers=headers_by_app[0])
        assert disabled.status_code == 403, disabled.text
        assert await conn.fetchval("SELECT is_deleted FROM users WHERE id = $1", end_user["id"]) == 1
        owner_catalog = await test_client.get("/api/v1/agents", headers={"Authorization": headers_by_app[0]["Authorization"]})
        assert owner_catalog.status_code == 200, owner_catalog.text
    finally:
        await conn.execute(
            "DELETE FROM users WHERE owner_user_id = $1 AND end_user_id = $2 AND app_id = ANY($3::varchar[])",
            owner_id,
            external_id,
            app_ids,
        )
        await conn.close()
