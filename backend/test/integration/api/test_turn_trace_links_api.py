"""以独占资源验证 Turn 观测入口的真实 HTTP 权限与持久关联。"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, update

from test.integration.api.test_agent_feedback_api import create_feedback_session
from test.integration.api.test_agent_feedback_api import feedback_agent as feedback_agent
from test.live_api_cleanup import delete_test_session_resources
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.modules.identity.models import User
from yuxi.modules.workspace.models import Project

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


@pytest_asyncio.fixture
async def trace_targets(test_client, postgres_sessions, feedback_agent, standard_user):
    """只登记并清理本用例创建的会话、项目与独占 Workdir。"""
    workdirs, projects, threads = {}, set(), set()

    async def create(headers):
        """创建可回读最终结果的独立会话。"""
        target = await create_feedback_session(test_client, headers, postgres_sessions, feedback_agent)
        threads.add(target["thread_id"])
        async with postgres_sessions() as db:
            thread = await db.scalar(select(Session).where(Session.thread_id == target["thread_id"]))
            project = await db.get(Project, thread.project_id)
            projects.add(project.id)
            workdirs.setdefault((thread.uid, project.workdir_path), set()).add(project.id)
        return target

    try:
        yield create
    finally:
        if threads:
            await delete_test_session_resources(workdirs, threads, projects)


async def test_feedback_trace_is_platform_jwt_only_and_preserves_personal_thread_access(
    test_client, admin_headers, standard_user, postgres_sessions, trace_targets, api_key_factory
):
    """跨用户只开放反馈观测，普通用户、admin、Key 和删除目标均被拒绝。"""
    target = await trace_targets(standard_user["headers"])
    base = f"/api/agent/threads/{target['thread_id']}/turns/{target['turn_id']}"
    saved = await test_client.put(f"{base}/feedback", headers=standard_user["headers"], json={"run_id": target["run_id"], "rating": "like"})
    assert saved.status_code == 200, saved.text
    path = f"/api/system/agent-feedback/{saved.json()['id']}/langfuse"
    for role in ("user", "admin"):
        async with postgres_sessions() as db:
            await db.execute(update(User).where(User.uid == standard_user["user"]["uid"]).values(role=role))
            await db.commit()
        for endpoint in (path, f"{base}/langfuse"):
            denied = await test_client.get(endpoint, headers=standard_user["headers"])
            assert denied.status_code == 403, denied.text
    for level in ("agents", "full"):
        issued = await api_key_factory(
            {
                "request_id": str(uuid.uuid4()),
                "name": "Turn trace boundary",
                "access_level": level,
                "app_id": f"pytest-trace-{uuid.uuid4().hex}",
            }
        )
        for endpoint in (path, f"{base}/langfuse"):
            assert (await test_client.get(endpoint, headers=issued.headers)).status_code == 403
    assert (await test_client.get(path)).status_code == 401
    allowed = await test_client.get(path, headers=admin_headers)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json() == {"turn_id": target["turn_id"], "langfuse_trace_id": None, "langfuse_url": None}
    assert (await test_client.get(f"{base}/langfuse", headers=admin_headers)).status_code == 404
    async with postgres_sessions() as db:
        await db.execute(update(Session).where(Session.thread_id == target["thread_id"]).values(status="archived"))
        await db.commit()
    assert (await test_client.get(path, headers=admin_headers)).json()["turn_id"] == target["turn_id"]
    async with postgres_sessions() as db:
        await db.execute(update(Session).where(Session.thread_id == target["thread_id"]).values(status="deleted"))
        await db.commit()
    assert (await test_client.get(path, headers=admin_headers)).status_code == 404


async def test_turn_trace_navigation_uses_exact_turn_and_audits_keep_run_binding(
    test_client, standard_user, postgres_sessions, trace_targets, feedback_agent
):
    """同轮恢复段共享 Trace，邻轮 Trace 不补缺失值，审计返回真实 Turn。"""
    sessions = postgres_sessions
    async with sessions() as db:
        await db.execute(update(User).where(User.uid == standard_user["user"]["uid"]).values(role="superadmin"))
        await db.commit()
    admin_headers = standard_user["headers"]
    target = await trace_targets(admin_headers)
    base = f"/api/agent/threads/{target['thread_id']}/turns/{target['turn_id']}"
    saved = await test_client.put(f"{base}/feedback", json={"run_id": target["run_id"], "rating": "like"}, headers=admin_headers)
    assert saved.status_code == 200, saved.text
    feedback_path = f"/api/system/agent-feedback/{saved.json()['id']}/langfuse"
    trace_id = uuid.uuid4().hex
    try:
        async with sessions() as db:
            # 反馈所在的最终 Run 没有 Trace，读取同一 Turn 较早执行段的持久关联。
            await db.execute(update(AgentRun).where(AgentRun.id == target["previous_id"]).values(langfuse_trace_id=trace_id))
            await db.commit()
        for endpoint in (f"{base}/langfuse", feedback_path):
            response = await test_client.get(endpoint, headers=admin_headers)
            assert response.status_code == 200, response.text
            assert response.json()["turn_id"] == target["turn_id"]
            assert response.json()["langfuse_trace_id"] == trace_id
            assert set(response.json()) == {"turn_id", "langfuse_trace_id", "langfuse_url"}

        audits = await test_client.get(f"/api/v1/agents/sessions/{target['thread_id']}/audits", headers=admin_headers)
        assert audits.status_code == 200, audits.text
        assert {run["turn_id"] for run in audits.json()["runs"]} == {target["turn_id"]}
        assert len(audits.json()["runs"]) == 2
        assert [(turn["turn_id"], turn["status"]) for turn in audits.json()["turns"]] == [(target["turn_id"], "completed")]

        async with sessions() as db:
            thread = await db.scalar(select(Session).where(Session.thread_id == target["thread_id"]))
            neighbour = AgentTurn(id=str(uuid.uuid4()), thread_id=thread.thread_id, uid=thread.uid, status="completed")
            db.add(neighbour)
            await db.flush()
            db.add(
                AgentRun(
                    id=str(uuid.uuid4()),
                    turn_id=neighbour.id,
                    thread_id=thread.thread_id,
                    uid=thread.uid,
                    runtime_scope_id=thread.tree_root_thread_id,
                    session_record_id=thread.id,
                    agent_slug=feedback_agent,
                    status="completed",
                    langfuse_trace_id=uuid.uuid4().hex,
                )
            )
            await db.execute(update(AgentRun).where(AgentRun.id == target["previous_id"]).values(langfuse_trace_id=None))
            await db.commit()
            assert await db.scalar(select(AgentRun.langfuse_trace_id).where(AgentRun.turn_id == neighbour.id)) is not None
        for endpoint in (f"{base}/langfuse", feedback_path):
            response = await test_client.get(endpoint, headers=admin_headers)
            assert response.json() == {"turn_id": target["turn_id"], "langfuse_trace_id": None, "langfuse_url": None}
        assert (await test_client.get(f"{base}/langfuse")).status_code == 401
        assert (await test_client.get(f"/api/system/agent-feedback/{uuid.uuid4()}/langfuse", headers=admin_headers)).status_code == 404
    finally:
        await test_client.post(f"/api/v1/agents/sessions/{target['thread_id']}/archive", headers=admin_headers)
