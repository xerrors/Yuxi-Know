import uuid

import asyncpg
import pytest_asyncio

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
