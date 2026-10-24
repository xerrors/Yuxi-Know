"""通过真实 HTTP 验证协作会话身份恢复和用户隔离。"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio

from yuxi.infrastructure.postgres.models import load_models
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.modules.agents.input_messages import build_chat_input_message, serialize_input_message
from yuxi.modules.agents.models.cooperation import CooperationEvent, CooperationRuntime
from yuxi.modules.agents.models.inputs import AgentInput, AgentInputReceipt
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


async def test_cooperation_observation_and_root_archive_preserve_scope_and_live_members(test_client, cooperation_user, admin_headers):
    """协作观察按用户隔离，归档不能隐藏仍在等待的成员入口。"""
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
            parent = Session(
                thread_id=parent_thread,
                uid=uid,
                project_id=project_id,
                agent_id="state-probe",
                status="active",
                config_snapshot={"model": "test:state", "tool_approval_mode": "default"},
            )
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

        async with sessions() as db:
            member_turn = await db.get(AgentTurn, child_turn_id)
            member_turn.status = "waiting"
            member_turn.waitpoint = {"kind": "answer", "run_id": child_id}
            (await db.get(AgentRun, child_id)).status = "interrupted"
            await db.commit()
        archive_url = f"/api/v1/agents/sessions/{parent_thread}/archive"
        refused = await test_client.post(archive_url, headers=cooperation_user["headers"])
        assert refused.status_code == 409, refused.text
        async with sessions() as db:
            assert (await db.scalar(select(Session).where(Session.thread_id == parent_thread))).status == "active"
            assert (await db.get(AgentTurn, turn_id)).status == "completed"
            member_turn = await db.get(AgentTurn, child_turn_id)
            assert member_turn.status == "waiting"
            member_turn.status = "completed"
            member_turn.waitpoint = None
            (await db.get(AgentRun, child_id)).status = "completed"
            await db.commit()
        archived = await test_client.post(archive_url, headers=cooperation_user["headers"])
        assert archived.status_code == 200, archived.text
        assert archived.json()["yuxi"]["archived"] is True
        async with sessions() as db:
            assert (await db.scalar(select(Session).where(Session.thread_id == parent_thread))).status == "archived"
            assert (await db.scalar(select(Session).where(Session.thread_id == child_thread))).status == "active"
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


@pytest.mark.parametrize("event_type", ["yuxi.session.tree.continue", "agent.session.input.message"])
async def test_tree_resume_rejects_unconfirmed_cleanup_without_mutating_queue(test_client, cooperation_user, event_type):
    """两种 HTTP 恢复入口均拒绝尚未清理的失败 Run，并保留原队列与停止意图。"""
    uid = cooperation_user["user"]["uid"]
    project_id, turn_id, run_id, input_id = (str(uuid.uuid4()) for _ in range(4))
    thread_id = f"pytest-coop-resume-{uuid.uuid4().hex}"
    load_models()
    engine = create_async_engine(os.environ["POSTGRES_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    snapshot = {"model": "test:state", "tool_approval_mode": "default"}
    try:
        async with sessions() as db:
            db.add(
                Project(
                    id=project_id, uid=uid, selection_status="implicit", workdir_path=f"projects/{project_id}", directory_mode="managed"
                )
            )
            await db.flush()
            member = Session(
                thread_id=thread_id,
                uid=uid,
                project_id=project_id,
                agent_id="state-probe",
                status="active",
                queue_paused=True,
                config_snapshot=snapshot,
            )
            db.add(member)
            await db.flush()
            db.add(AgentTurn(id=turn_id, thread_id=thread_id, uid=uid, status="failed", current_run_id=run_id, result_run_id=run_id))
            await db.flush()
            db.add(
                AgentRun(
                    id=run_id,
                    uid=uid,
                    agent_slug="state-probe",
                    run_type="chat",
                    session_record_id=member.id,
                    thread_id=thread_id,
                    runtime_scope_id=thread_id,
                    turn_id=turn_id,
                    status="failed",
                    finished_at=utc_now(),
                    runtime_cleanup_pending=True,
                    input_payload={"context_snapshot": snapshot},
                )
            )
            db.add(CooperationRuntime(tree_root_thread_id=thread_id, stopped=True))
            db.add(
                AgentInput(
                    id=input_id,
                    thread_id=thread_id,
                    uid=uid,
                    agent_slug="state-probe",
                    kind="follow_up",
                    status="pending",
                    messages=[serialize_input_message(build_chat_input_message("ORIGINAL_PENDING_WORK"))],
                    input_payload={"context_snapshot": snapshot},
                )
            )
            await db.commit()

        event = {"type": event_type}
        if event_type == "agent.session.input.message":
            event["input"] = [{"role": "user", "content": [{"type": "input_text", "text": "RESUME_AFTER_STOP"}]}]
        response = await test_client.post(
            f"/api/v1/agents/sessions/{thread_id}/events",
            headers={**cooperation_user["headers"], "Idempotency-Key": f"resume-{uuid.uuid4().hex}"},
            json={"events": [event]},
        )
        assert response.status_code == 409, response.text
        async with sessions() as db:
            assert (await db.get(CooperationRuntime, thread_id)).stopped is True
            assert (await db.scalar(select(Session).where(Session.thread_id == thread_id))).queue_paused is True
            run = await db.get(AgentRun, run_id)
            assert run.status == "failed" and run.runtime_cleanup_pending
            items = list((await db.scalars(select(AgentInput).where(AgentInput.thread_id == thread_id))).all())
            assert len(items) == 1 and items[0].id == input_id
            assert items[0].status == "pending" and items[0].turn_id is None and items[0].consumed_run_id is None
            assert list((await db.scalars(select(AgentTurn.id).where(AgentTurn.thread_id == thread_id))).all()) == [turn_id]
            assert list((await db.scalars(select(AgentRun.id).where(AgentRun.thread_id == thread_id))).all()) == [run_id]
            assert not await db.scalar(select(AgentInputReceipt.id).where(AgentInputReceipt.thread_id == thread_id))
    finally:
        async with sessions() as db:
            await db.execute(delete(AgentInputReceipt).where(AgentInputReceipt.thread_id == thread_id))
            await db.execute(delete(AgentInput).where(AgentInput.thread_id == thread_id))
            await db.execute(update(AgentTurn).where(AgentTurn.thread_id == thread_id).values(current_run_id=None, result_run_id=None))
            await db.execute(delete(CooperationEvent).where(CooperationEvent.tree_root_thread_id == thread_id))
            await db.execute(delete(AgentRun).where(AgentRun.thread_id == thread_id))
            await db.execute(delete(AgentTurn).where(AgentTurn.thread_id == thread_id))
            await db.execute(delete(CooperationRuntime).where(CooperationRuntime.tree_root_thread_id == thread_id))
            await db.execute(delete(Session).where(Session.thread_id == thread_id))
            await db.execute(delete(Project).where(Project.id == project_id))
            await db.commit()
        await engine.dispose()
