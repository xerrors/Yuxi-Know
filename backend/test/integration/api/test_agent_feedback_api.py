"""通过真实 HTTP 和 PostgreSQL 验证反馈协议与身份隔离。"""

import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from test.live_api_cleanup import delete_test_session_resources, make_test_session_title
from yuxi.modules.agents.models.feedback import AgentFeedbackRecord
from yuxi.modules.agents.models.messages import Message
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.modules.identity.models import User
from yuxi.modules.workspace.models import Project

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest_asyncio.fixture
async def feedback_agent(test_client, admin_headers):
    """创建本组用例独占的共享 Agent，避免依赖已有目录或内置默认数据。"""
    slug = f"pytest-feedback-{uuid.uuid4().hex}"
    response = await test_client.post(
        "/api/agent",
        headers=admin_headers,
        json={
            "slug": slug,
            "name": "Feedback HTTP test",
            "visibility": "shared",
            "config_json": {"context": {"tools": [], "skills": [], "knowledges": [], "mcps": []}},
            "share_config": {
                "version": 2,
                "read_scope": {"access_level": "global", "department_ids": [], "user_uids": []},
                "manage_scope": None,
            },
        },
    )
    assert response.status_code == 200, response.text
    try:
        yield slug
    finally:
        deleted = await test_client.delete(f"/api/agent/{slug}", headers=admin_headers)
        assert deleted.status_code == 200, deleted.text


@pytest.mark.parametrize("access_level", ["agents", "full"])
async def test_web_feedback_rejects_api_keys_and_app_sessions(test_client, standard_user, feedback_target, feedback_agent, access_level):
    """Web 反馈拒绝两类 Key；产品 JWT 不能读写 APP 终端用户会话。"""
    engine = create_async_engine(os.environ["POSTGRES_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    headers = standard_user["headers"]
    app_id = f"pytest-feedback-app-{uuid.uuid4().hex}"
    key = await test_client.post(
        "/api/user/apikey/",
        headers=headers,
        json={"request_id": str(uuid.uuid4()), "name": "Feedback Web boundary", "access_level": access_level, "app_id": app_id},
    )
    assert key.status_code == 200, key.text
    public_headers = {"Authorization": f"Bearer {key.json()['secret']}", "X-End-User-Id": "feedback-visitor"}
    target, workdirs, projects = None, {}, set()
    web_target, _ = feedback_target
    try:
        target = await create_feedback_session(test_client, public_headers, sessions, feedback_agent)
        async with sessions() as db:
            thread = await db.scalar(select(Session).where(Session.thread_id == target["thread_id"]))
            project = await db.get(Project, thread.project_id)
            workdirs = {(thread.uid, project.workdir_path): {project.id}}
            projects = {project.id}
        base = f"/api/agent/threads/{target['thread_id']}"
        path = f"{base}/turns/{target['turn_id']}/feedback"
        body = {"run_id": target["run_id"], "rating": "like"}
        for selected in (target, web_target):
            key_base = f"/api/agent/threads/{selected['thread_id']}"
            key_path = f"{key_base}/turns/{selected['turn_id']}/feedback"
            assert (
                await test_client.put(key_path, headers=public_headers, json={"run_id": selected["run_id"], "rating": "like"})
            ).status_code == 403
            assert (await test_client.get(f"{key_base}/feedback", headers=public_headers)).status_code == 403
            assert (await test_client.delete(key_path, headers=public_headers, params={"run_id": selected["run_id"]})).status_code == 403
        assert (await test_client.put(path, headers=headers, json=body)).status_code == 404
        assert (await test_client.get(f"{base}/feedback", headers=headers)).status_code == 404
        async with sessions() as db:
            count = await db.scalar(
                select(func.count())
                .select_from(AgentFeedbackRecord)
                .where(AgentFeedbackRecord.run_id.in_([target["run_id"], web_target["run_id"]]))
            )
            assert count == 0
    finally:
        if target:
            await delete_test_session_resources(workdirs, {target["thread_id"]}, projects)
        await test_client.delete(f"/api/user/apikey/{key.json()['api_key']['id']}", headers=headers)
        async with sessions() as db:
            await db.execute(delete(User).where(User.user_kind == "end_user", User.app_id == app_id))
            await db.commit()
        await engine.dispose()


async def create_feedback_session(client, headers, sessions, agent_id):
    """经 HTTP 创建属于测试身份的会话，再建立可独立回读的最终输出。"""
    response = await client.post(
        "/api/v1/agents/sessions",
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"agent_id": agent_id, "title": make_test_session_title("feedback")},
    )
    assert response.status_code == 201, response.text
    thread_id = response.json()["id"]
    turn_id, run_id, previous_id = (str(uuid.uuid4()) for _ in range(3))
    async with sessions() as db:
        thread = await db.scalar(select(Session).where(Session.thread_id == thread_id))
        turn = AgentTurn(id=turn_id, thread_id=thread_id, uid=thread.uid, app_id=thread.app_id, status="completed")
        db.add(turn)
        await db.flush()
        for target, status in ((previous_id, "yielded"), (run_id, "completed")):
            db.add(
                AgentRun(
                    id=target,
                    thread_id=thread_id,
                    runtime_scope_id=thread.tree_root_thread_id,
                    turn_id=turn_id,
                    session_record_id=thread.id,
                    uid=thread.uid,
                    app_id=thread.app_id,
                    agent_slug=agent_id,
                    status=status,
                )
            )
        await db.flush()
        output = Message(session_record_id=thread.id, role="assistant", content="用于反馈验收的最终回答", run_id=run_id, turn_id=turn_id)
        db.add(output)
        await db.flush()
        run = await db.get(AgentRun, run_id)
        run.output_message_id = output.id
        turn.current_run_id = turn.result_run_id = run_id
        await db.commit()
    return {"thread_id": thread_id, "turn_id": turn_id, "run_id": run_id, "previous_id": previous_id}


@pytest_asyncio.fixture
async def feedback_target(test_client, standard_user, feedback_agent):
    """准备普通用户的独立测试目标，结束归档交给现有测试清理。"""
    engine = create_async_engine(os.environ["POSTGRES_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    target = await create_feedback_session(test_client, standard_user["headers"], sessions, feedback_agent)
    try:
        yield target, sessions
    finally:
        await test_client.post(f"/api/v1/agents/sessions/{target['thread_id']}/archive", headers=standard_user["headers"])
        await engine.dispose()


async def test_user_feedback_roundtrip_and_admin_cannot_impersonate(test_client, admin_headers, standard_user, feedback_target):
    """赞踩说明、并发去重和撤销通过数据库终值与真实回读确认。"""
    target, sessions = feedback_target
    base = f"/api/agent/threads/{target['thread_id']}"
    path = f"{base}/turns/{target['turn_id']}/feedback"
    body = {"run_id": target["run_id"], "rating": "like", "reason": "有帮助"}
    headers = standard_user["headers"]
    first, second = await asyncio.gather(*(test_client.put(path, json=body, headers=headers) for _ in range(2)))
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    denied = await test_client.put(path, json=body, headers=admin_headers)
    assert denied.status_code == 404
    assert (await test_client.get(f"{base}/feedback", headers=admin_headers)).status_code == 404
    update_response = await test_client.put(path, json={**body, "rating": "dislike", "reason": "  流程需要调整  "}, headers=headers)
    assert update_response.status_code == 200, update_response.text
    async with sessions() as db:
        rows = (await db.scalars(select(AgentFeedbackRecord).where(AgentFeedbackRecord.run_id == target["run_id"]))).all()
        assert len(rows) == 1 and (rows[0].rating, rows[0].reason) == ("dislike", "流程需要调整")
    page = await test_client.get(f"{base}/feedback", params={"source": "user", "run_ids": target["run_id"]}, headers=headers)
    assert page.status_code == 200 and page.json()["items"][0]["id"] == first.json()["id"]
    changed = await test_client.put(path, json={**body, "reason": None}, headers=headers)
    assert changed.status_code == 200 and changed.json()["reason"] is None
    for _ in range(2):
        assert (await test_client.delete(path, params={"run_id": target["run_id"]}, headers=headers)).status_code == 204
    assert (await test_client.get(f"{base}/feedback", headers=headers)).json()["items"] == []
    async with sessions() as db:
        assert (
            await db.scalar(select(func.count()).select_from(AgentFeedbackRecord).where(AgentFeedbackRecord.run_id == target["run_id"]))
            == 0
        )


async def test_http_feedback_rejects_nonfinal_and_invalid_inputs(test_client, standard_user, feedback_target):
    """猜中历史 Run、未知目标和非法正文均不能创建评价。"""
    target, _ = feedback_target
    path = f"/api/agent/threads/{target['thread_id']}/turns/{target['turn_id']}/feedback"
    headers = standard_user["headers"]
    for run_id, rating, reason, expected in (
        (target["previous_id"], "like", None, 409),
        (str(uuid.uuid4()), "like", None, 404),
        (target["run_id"], "unknown", None, 422),
        (target["run_id"], "like", "x" * 2001, 422),
    ):
        response = await test_client.put(path, json={"run_id": run_id, "rating": rating, "reason": reason}, headers=headers)
        assert response.status_code == expected, response.text
    assert (await test_client.put(path, json={"run_id": target["run_id"], "rating": "like"})).status_code == 401
    params = [("run_ids", str(uuid.uuid4())) for _ in range(101)]
    assert (await test_client.get(f"/api/agent/threads/{target['thread_id']}/feedback", params=params, headers=headers)).status_code == 422


async def test_platform_list_rejects_regular_admin_and_full_api_key(test_client, admin_headers, standard_user, feedback_target):
    """用户和普通 admin 均不可集中读，superadmin 的 full Key 也不例外。"""
    target, sessions = feedback_target
    path = f"/api/agent/threads/{target['thread_id']}/turns/{target['turn_id']}/feedback"
    saved = await test_client.put(path, json={"run_id": target["run_id"], "rating": "like"}, headers=standard_user["headers"])
    assert saved.status_code == 200, saved.text
    assert (await test_client.get("/api/system/agent-feedback", headers=standard_user["headers"])).status_code == 403
    async with sessions() as db:
        await db.execute(update(User).where(User.uid == standard_user["user"]["uid"]).values(role="admin"))
        await db.commit()
    assert (await test_client.get("/api/system/agent-feedback", headers=standard_user["headers"])).status_code == 403
    key = await test_client.post(
        "/api/user/apikey/",
        headers=admin_headers,
        json={
            "request_id": str(uuid.uuid4()),
            "name": "Feedback isolation",
            "access_level": "full",
            "app_id": f"pytest-feedback-{uuid.uuid4().hex}",
        },
    )
    assert key.status_code == 200, key.text
    try:
        denied = await test_client.get("/api/system/agent-feedback", headers={"Authorization": f"Bearer {key.json()['secret']}"})
        assert denied.status_code == 403, denied.text
        allowed = await test_client.get("/api/system/agent-feedback", headers=admin_headers)
        assert allowed.status_code == 200, allowed.text
        record = next(item for item in allowed.json()["items"] if item["id"] == saved.json()["id"])
        assert "manifest" not in record and "uid" not in record
        async with sessions() as db:
            await db.execute(update(Session).where(Session.thread_id == target["thread_id"]).values(status="deleted"))
            await db.commit()
        deleted = await test_client.get("/api/system/agent-feedback", headers=admin_headers)
        assert saved.json()["id"] not in {item["id"] for item in deleted.json()["items"]}
        assert (
            await test_client.get(f"/api/agent/threads/{target['thread_id']}/feedback", headers=standard_user["headers"])
        ).status_code == 404
    finally:
        await test_client.delete(f"/api/user/apikey/{key.json()['api_key']['id']}", headers=admin_headers)


async def test_public_feedback_routes_are_absent(test_client, standard_user, feedback_target):
    """使用有效身份与目标访问撤下的 Public 地址，所有方法都返回 404。"""
    target, _ = feedback_target
    base = f"/api/v1/agents/sessions/{target['thread_id']}"
    path = f"{base}/turns/{target['turn_id']}/feedback"
    headers = standard_user["headers"]
    assert (await test_client.get(f"{base}/feedback", headers=headers)).status_code == 404
    assert (await test_client.put(path, headers=headers, json={"run_id": target["run_id"], "rating": "like"})).status_code == 404
    assert (await test_client.delete(path, headers=headers, params={"run_id": target["run_id"]})).status_code == 404
