"""API 集成测试共享的会话与密钥清理辅助。"""

from __future__ import annotations

import uuid

import asyncpg

from test.live_api_cleanup import delete_test_session_resources, make_test_session_title, validate_test_runs_terminal
from test.support.postgres import postgres_dsn


async def create_department(test_client, headers: dict[str, str], payload: dict) -> dict:
    """按调用方给定的身份字段创建部门。"""
    response = await test_client.post("/api/departments", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def create_api_user(test_client, headers: dict[str, str], payload: dict) -> dict:
    """按调用方给定的账号字段创建用户。"""
    response = await test_client.post("/api/auth/users", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def delete_user_by_id(test_client, headers: dict[str, str], user_id: int) -> None:
    """删除已知用户，允许资源已被业务流程级联删除。"""
    response = await test_client.delete(f"/api/auth/users/{user_id}", headers=headers)
    assert response.status_code in {200, 404}, response.text


async def delete_department_by_id(test_client, headers: dict[str, str], department_id: int) -> None:
    """删除已知测试部门，允许资源已被业务流程级联删除。"""
    response = await test_client.delete(f"/api/departments/{department_id}", headers=headers)
    assert response.status_code in {200, 404}, response.text


async def create_default_agent_thread(test_client, headers: dict[str, str], *, title_prefix: str) -> str:
    """通过默认 Agent 创建隔离的 Public Thread。"""
    agent_response = await test_client.get("/api/agent/default", headers=headers)
    assert agent_response.status_code == 200, agent_response.text
    agent = agent_response.json().get("agent") or {}
    agent_id = agent.get("slug") or agent.get("agent_id") or agent.get("id")
    assert isinstance(agent_id, str) and agent_id, "default agent response must include its slug or id"
    response = await test_client.post(
        "/api/v1/agents/sessions",
        json={"agent_id": agent_id, "title": make_test_session_title(title_prefix)},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 201, response.text
    thread_id = response.json()["id"]
    assert thread_id
    return str(thread_id)


async def get_thread_workdir_path(thread_id: str) -> str:
    """从 PostgreSQL 读取 Thread 实际绑定的 Workdir。"""
    conn = await asyncpg.connect(postgres_dsn())
    try:
        workdir_path = await conn.fetchval(
            "SELECT p.workdir_path FROM sessions c JOIN projects p ON p.id = c.project_id WHERE c.thread_id = $1",
            thread_id,
        )
    finally:
        await conn.close()
    assert workdir_path
    return str(workdir_path)


async def delete_created_threads(*thread_ids: str | None) -> None:
    """只清理已验证为隐式 Project 的测试 Thread。"""
    targets = {thread_id for thread_id in thread_ids if thread_id}
    if not targets:
        return
    await validate_test_runs_terminal(targets)
    conn = await asyncpg.connect(postgres_dsn())
    try:
        rows = await conn.fetch(
            "SELECT c.thread_id, c.uid, c.project_id, p.workdir_path, "
            "p.directory_mode, p.selection_status, u.user_kind, u.end_user_id "
            "FROM sessions c JOIN projects p ON p.id = c.project_id AND p.uid = c.uid "
            "JOIN users u ON u.uid = c.uid "
            "WHERE c.thread_id = ANY($1::text[])",
            sorted(targets),
        )
    finally:
        await conn.close()
    if {row["thread_id"] for row in rows} != targets:
        raise RuntimeError("Test Thread cleanup cannot verify all created resources")
    if any(row["directory_mode"] != "managed" or row["selection_status"] != "implicit" for row in rows):
        raise RuntimeError("Test Thread cleanup refuses a non-implicit Project")
    workdirs = {(row["uid"], row["workdir_path"]): {row["project_id"]} for row in rows}
    await delete_test_session_resources(workdirs, targets, {row["project_id"] for row in rows})
    public_uids = {row["uid"] for row in rows if row["user_kind"] == "end_user" and row["end_user_id"] == "__default__"}
    if public_uids:
        conn = await asyncpg.connect(postgres_dsn())
        try:
            await conn.execute(
                "DELETE FROM users WHERE uid = ANY($1::text[]) AND user_kind = 'end_user' "
                "AND end_user_id = '__default__' "
                "AND NOT EXISTS (SELECT 1 FROM sessions WHERE sessions.uid = users.uid) "
                "AND NOT EXISTS (SELECT 1 FROM projects WHERE projects.uid = users.uid)",
                sorted(public_uids),
            )
        finally:
            await conn.close()
