"""通过真实 HTTP 验证协作会话身份恢复和用户隔离。"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio

from yuxi.bootstrap.models import load_models
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.workspace.models import Project
from yuxi.shared.datetime import utc_now

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_sandboxes():
    """本测试只使用 HTTP 与 PostgreSQL 协作状态，不创建沙盒，跳过全局沙盒清理。"""
    yield


@pytest_asyncio.fixture
async def cooperation_user(test_client, admin_headers):
    """在测试管理员所属部门建立用户，不要求跨部门管理权限。"""
    admin = await test_client.get("/api/auth/me", headers=admin_headers)
    assert admin.status_code == 200, admin.text
    username, password = f"pytest_coop_{uuid.uuid4().hex[:8]}", f"Pw!{uuid.uuid4().hex}"
    response = await test_client.post(
        "/api/auth/users",
        headers=admin_headers,
        json={
            "username": username,
            "password": password,
            "role": "user",
            "department_id": admin.json()["department_id"],
        },
    )
    assert response.status_code == 200, response.text
    user = response.json()
    try:
        login = await test_client.post("/api/auth/token", data={"username": user["uid"], "password": password})
        assert login.status_code == 200
        yield {"user": user, "headers": {"Authorization": f"Bearer {login.json()['access_token']}"}}
    finally:
        deleted = await test_client.delete(f"/api/auth/users/{user['id']}", headers=admin_headers)
        assert deleted.status_code in (200, 404), deleted.text


async def test_state_recovers_children_without_checkpoint_and_rejects_other_user(test_client, cooperation_user, admin_headers):
    """创建已提交而父 checkpoint 从未写入的子 Run，页面仍能发现并读到终态。"""
    uid = cooperation_user["user"]["uid"]
    project_id = str(uuid.uuid4())
    parent_thread, child_thread = (f"pytest-cooperation-state-{uuid.uuid4()}" for _ in range(2))
    parent_id, child_id = (str(uuid.uuid4()) for _ in range(2))
    turn_id, child_turn_id = str(uuid.uuid4()), str(uuid.uuid4())
    load_models()
    engine = create_async_engine(os.environ["POSTGRES_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as db:
            db.add(
                Project(
                    id=project_id,
                    uid=uid,
                    selection_status="implicit",
                    workdir_path=f"projects/{project_id}",
                    directory_mode="managed",
                )
            )
            await db.flush()
            parent = Session(thread_id=parent_thread, uid=uid, project_id=project_id, agent_id="state-probe", status="active")
            child = Session(
                thread_id=child_thread,
                uid=uid,
                project_id=project_id,
                agent_id="state-probe",
                status="active",
                tree_root_thread_id=parent_thread,
                parent_thread_id=parent_thread,
                cooperation_name="worker",
                cooperation_path="/root/worker",
            )
            db.add(parent)
            await db.flush()
            db.add(child)
            await db.flush()
            db.add(
                AgentTurn(
                    id=turn_id,
                    thread_id=parent_thread,
                    uid=uid,
                    status="completed",
                    current_run_id=parent_id,
                    result_run_id=parent_id,
                )
            )
            await db.flush()
            db.add(
                AgentRun(
                    id=parent_id,
                    uid=uid,
                    agent_slug="state-probe",
                    run_type="chat",
                    session_record_id=parent.id,
                    thread_id=parent_thread,
                    runtime_scope_id=parent_thread,
                    turn_id=turn_id,
                    status="completed",
                    finished_at=utc_now(),
                    input_payload={},
                )
            )
            await db.flush()
            db.add(
                AgentTurn(
                    id=child_turn_id,
                    thread_id=child_thread,
                    uid=uid,
                    status="completed",
                    current_run_id=child_id,
                    result_run_id=child_id,
                )
            )
            await db.flush()
            db.add(
                AgentRun(
                    id=child_id,
                    uid=uid,
                    agent_slug="state-probe",
                    run_type="chat",
                    session_record_id=child.id,
                    thread_id=child_thread,
                    runtime_scope_id=parent_thread,
                    turn_id=child_turn_id,
                    status="completed",
                    finished_at=utc_now(),
                    created_by_run_id=parent_id,
                    input_payload={"runtime": {"tool_call_id": "start-probe"}},
                )
            )
            await db.commit()

        response = await test_client.get(f"/api/v1/agents/sessions/{parent_thread}/state", headers=cooperation_user["headers"])
        assert response.status_code == 200, response.text
        runs = response.json()["agent_state"]["cooperation"]["sessions"]
        assert len(runs) == 2, response.json()
        member = next(item for item in runs if item["session_id"] == child_thread)
        assert member["current_run_id"] == child_id and member["turn_status"] == "completed"
        summary_url = f"/api/v1/agents/sessions/{parent_thread}/cooperation"
        summary = await test_client.get(summary_url, headers=cooperation_user["headers"])
        assert summary.status_code == 200, summary.text
        snapshot = summary.json()
        assert "agent_state" not in snapshot and "next_cursor" not in snapshot
        assert {row["session_id"] for row in snapshot["sessions"]} == {parent_thread, child_thread}
        assert all("output" not in row for row in snapshot["sessions"])
        child_run_url = f"/api/v1/agents/sessions/{child_thread}/runs/{child_id}"
        run_response = await test_client.get(child_run_url, headers=cooperation_user["headers"])
        assert run_response.status_code == 200, run_response.text
        assert run_response.json()["status"] == "completed"
        async with sessions() as db:
            persisted = await db.get(AgentRun, child_id)
            assert persisted is not None and persisted.turn_id == child_turn_id
            assert persisted.created_by_run_id == parent_id
        for url in (f"/api/v1/agents/sessions/{parent_thread}/state", child_run_url, summary_url):
            denied = await test_client.get(url, headers=admin_headers)
            assert denied.status_code == 404, denied.text
            assert child_id not in denied.text
    finally:
        async with sessions() as db:
            await db.execute(
                update(AgentTurn).where(AgentTurn.id.in_([turn_id, child_turn_id])).values(current_run_id=None, result_run_id=None)
            )
            await db.execute(delete(AgentRun).where(AgentRun.id == child_id))
            await db.execute(delete(AgentRun).where(AgentRun.id == parent_id))
            await db.execute(delete(AgentTurn).where(AgentTurn.id.in_([turn_id, child_turn_id])))
            await db.execute(delete(Session).where(Session.thread_id == child_thread))
            await db.execute(delete(Session).where(Session.thread_id == parent_thread))
            await db.execute(delete(Project).where(Project.id == project_id))
            await db.commit()
        await engine.dispose()
