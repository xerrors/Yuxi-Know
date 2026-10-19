import uuid
from collections.abc import AsyncGenerator

import anyio
import httpx
import pytest

import asyncpg
import pytest_asyncio

from test.live_api_cleanup import cleanup_test_chat_resources, list_test_session_resources
from test.support.postgres import postgres_dsn
from test.support.public_api import delete_agent

SHARED = {"version": 2, "read_scope": {"access_level": "global"}, "manage_scope": None}


@pytest_asyncio.fixture
async def actors(test_client, admin_headers):
    """创建两个部门的管理员和普通用户，并清理本测试资源。"""
    suffix = uuid.uuid4().hex[:8]
    password = f"Test-{uuid.uuid4().hex}"
    users, departments, agents, keys = [], [], [], []
    db = await asyncpg.connect(postgres_dsn())
    identities = {}
    try:
        for index in range(2):
            uid = f"padmin{index}{suffix}"
            response = await test_client.post(
                "/api/departments",
                headers=admin_headers,
                json={
                    "name": f"Permission {index} {suffix}",
                    "admin_uid": uid,
                    "admin_password": password,
                },
            )
            assert response.status_code == 201, response.text
            department_id = response.json()["id"]
            departments.append(department_id)
            token = await test_client.post("/api/auth/token", data={"username": uid, "password": password})
            assert token.status_code == 200, token.text
            headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
            me = (await test_client.get("/api/auth/me", headers=headers)).json()
            users.append(me["id"])
            identities[f"admin{index}"] = {**me, "headers": headers}
            response = await test_client.post(
                "/api/auth/users",
                headers=headers,
                json={
                    "username": f"puser{index}{suffix}",
                    "password": password,
                },
            )
            assert response.status_code == 200, response.text
            user = response.json()
            users.append(user["id"])
            token = await test_client.post("/api/auth/token", data={"username": user["uid"], "password": password})
            assert token.status_code == 200, token.text
            identities[f"user{index}"] = {
                **user,
                "headers": {"Authorization": f"Bearer {token.json()['access_token']}"},
            }
        yield {
            "client": test_client,
            "root": admin_headers,
            "identities": identities,
            "db": db,
            "agents": agents,
            "keys": keys,
            "password": password,
        }
    finally:
        for slug in agents:
            await delete_agent(test_client, admin_headers, slug)
        for key in keys:
            await test_client.delete(f"/api/user/apikey/{key}", headers=admin_headers)
        for user_id in users:
            response = await test_client.delete(f"/api/auth/users/{user_id}", headers=admin_headers)
            assert response.status_code in {200, 404}, response.text
        for department_id in departments:
            await test_client.delete(f"/api/departments/{department_id}", headers=admin_headers)
        await db.close()


async def create_agent(actors, owner, **payload):
    """创建定义并登记清理目标。"""
    response = await actors["client"].post("/api/agent", headers=owner["headers"], json={"name": "Permission bot", **payload})
    assert response.status_code == 200, response.text
    agent = response.json()["agent"]
    actors["agents"].append(agent["slug"])
    return agent


@pytest_asyncio.fixture(scope="function")
async def standard_user(test_client: httpx.AsyncClient, admin_headers: dict[str, str]) -> AsyncGenerator[dict, None]:
    """创建普通用户，清理本例会话后再删除身份。"""
    username = f"pytest_user_{uuid.uuid4().hex[:8]}"
    password = f"Pw!{uuid.uuid4().hex[:8]}"

    # 用户隔离重构后所有登录用户必须绑定部门，创建时显式指定一个已存在部门
    dept_response = await test_client.get("/api/departments", headers=admin_headers)
    if dept_response.status_code != 200 or not dept_response.json():
        pytest.fail(f"No department available to bind standard user: {dept_response.text}")
    department_id = dept_response.json()[0]["id"]

    response = await test_client.post(
        "/api/auth/users",
        json={"username": username, "password": password, "role": "user", "department_id": department_id},
        headers=admin_headers,
    )
    if response.status_code != 200:
        pytest.fail(f"Failed to create standard user (status={response.status_code}): {response.text}")

    user_payload = response.json()
    login_response = await test_client.post(
        "/api/auth/token",
        data={"username": user_payload["uid"], "password": password},
    )
    if login_response.status_code != 200:
        pytest.fail(f"Failed to authenticate as standard user (status={login_response.status_code}): {login_response.text}")

    access_token = login_response.json().get("access_token")
    if not access_token:
        pytest.fail("Standard user login succeeded but no access token was returned.")

    try:
        yield {
            "user": user_payload,
            "password": password,
            "headers": {"Authorization": f"Bearer {access_token}"},
        }
    finally:
        auth_check = await test_client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_token}"})
        if auth_check.status_code == 200:
            await cleanup_test_chat_resources(
                test_client,
                {"Authorization": f"Bearer {access_token}"},
                owner_uid=str(user_payload["uid"]),
            )
        elif auth_check.status_code in {401, 403, 423}:
            # 锁定或删除用户的令牌已失效，确认无持久对话后再由管理员清理用户。
            remaining = await list_test_session_resources(str(user_payload["uid"]))
            if remaining:
                raise RuntimeError("Cannot clean test sessions with a revoked standard-user token")
        else:
            raise RuntimeError(f"Cannot verify standard-user cleanup access: {auth_check.status_code}")
        cleanup_error = None
        for _ in range(3):
            response = await test_client.delete(f"/api/auth/users/{user_payload['id']}", headers=admin_headers)
            if response.status_code in (200, 404):
                cleanup_error = None
                break
            cleanup_error = response
            await anyio.sleep(0.3)
        if cleanup_error is not None:
            assert cleanup_error.status_code == 200, f"Failed to cleanup test user {user_payload['uid']}: {cleanup_error.text}"
