"""
Integration tests for dashboard router endpoints.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from yuxi.modules.agents.models.messages import Message
from yuxi.modules.agents.models.sessions import Session
from yuxi.shared.datetime import utc_now

from test.live_api_cleanup import make_test_session_title

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _set_session_statuses(member_thread_id: str, deleted_thread_id: str) -> None:
    """使用绑定当前测试事件循环的一次性引擎写入状态事实。"""
    engine = create_async_engine(os.environ["POSTGRES_URL"])
    try:
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with session_factory() as db:
            await db.execute(update(Session).where(Session.thread_id == member_thread_id).values(status="active"))
            await db.execute(update(Session).where(Session.thread_id == deleted_thread_id).values(status="deleted"))
            await db.commit()
    finally:
        await engine.dispose()


async def test_dashboard_http_reads_tool_messages_and_counts_only_started_executions(test_client, admin_headers):
    """真实 HTTP 从工具 Message 读取结果，并区分失败、中断和审批拒绝。"""
    from sqlalchemy import select

    default_agent = await test_client.get("/api/agent/default", headers=admin_headers)
    assert default_agent.status_code == 200, default_agent.text
    agent = default_agent.json()["agent"]
    marker = f"dashboard-tools-{uuid.uuid4().hex[:10]}"
    created = await test_client.post(
        "/api/v1/agents/sessions",
        headers={**admin_headers, "Idempotency-Key": marker},
        json={"agent_id": agent["slug"], "title": make_test_session_title(marker)},
    )
    assert created.status_code == 201, created.text
    thread_id = created.json()["id"]
    before = await test_client.get("/api/dashboard/stats/tools", headers=admin_headers)
    assert before.status_code == 200, before.text
    baseline = before.json()
    before_series = await test_client.get("/api/dashboard/stats/calls/timeseries?type=tools&time_range=14days", headers=admin_headers)
    assert before_series.status_code == 200, before_series.text

    engine = create_async_engine(os.environ["POSTGRES_URL"])
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            session = await db.scalar(select(Session).where(Session.thread_id == thread_id))
            model = Message(session_record_id=session.id, role="assistant", content="tool source")
            db.add(model)
            await db.flush()
            now = utc_now()
            for status, started, source in [
                ("completed", now, None),
                ("failed", now, None),
                ("interrupted", now, None),
                ("failed", None, "approval_rejection"),
            ]:
                db.add(
                    Message(
                        session_record_id=session.id,
                        role="tool",
                        message_type="tool_audit",
                        execution_status=status,
                        started_at=started,
                        content="persisted tool output",
                        operation_id=f"{marker}-{source or status}",
                        extra_metadata={
                            "tool_name": source or status,
                            "input": {"query": "persisted input"},
                            "output": "persisted tool output",
                            "source_model_message_id": model.id,
                            "source": source,
                        },
                    )
                )
            await db.commit()

        detail = await test_client.get(f"/api/dashboard/sessions/{thread_id}", headers=admin_headers)
        stats = await test_client.get("/api/dashboard/stats/tools", headers=admin_headers)
        series = await test_client.get("/api/dashboard/stats/calls/timeseries?type=tools&time_range=14days", headers=admin_headers)
        assert detail.status_code == stats.status_code == series.status_code == 200
        message = next(item for item in detail.json()["messages"] if item["id"] == model.id)
        assert "tool_calls" not in message
        tools = message["tool_executions"]
        assert [tool["execution_status"] for tool in tools] == ["completed", "failed", "interrupted", "failed"]
        assert all(tool["tool_output"] == "persisted tool output" for tool in tools)
        assert all(tool["tool_input"] == {"query": "persisted input"} for tool in tools)
        assert tools[-1]["source"] == "approval_rejection" and tools[-1]["started_at"] is None
        assert stats.json()["total_calls"] == baseline["total_calls"] + 3
        assert stats.json()["successful_calls"] == baseline["successful_calls"] + 1
        assert stats.json()["failed_calls"] == baseline["failed_calls"] + 1
        assert series.json()["total_count"] == before_series.json()["total_count"] + 3
    finally:
        await engine.dispose()


async def test_dashboard_requires_authentication(test_client):
    response = await test_client.get("/api/dashboard/sessions")
    assert response.status_code == 401


async def test_standard_user_is_forbidden(test_client, standard_user):
    response = await test_client.get("/api/dashboard/sessions", headers=standard_user["headers"])
    assert response.status_code == 403


async def test_admin_can_fetch_sessions(test_client, admin_headers):
    response = await test_client.get("/api/dashboard/sessions", headers=admin_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == {"items", "total", "limit", "offset"}
    assert isinstance(data["items"], list)
    assert data["total"] >= len(data["items"])


async def test_admin_can_fetch_session_filter_options(test_client, admin_headers):
    response = await test_client.get("/api/dashboard/sessions/options", headers=admin_headers)

    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == {"users", "agents"}
    assert all("is_deleted" in item for item in data["users"])
    assert all("is_deleted" in item for item in data["agents"])


async def test_dashboard_rejects_invalid_query_ranges(test_client, admin_headers):
    responses = [
        await test_client.get("/api/dashboard/stats/threads?time_range=365days", headers=admin_headers),
        await test_client.get("/api/dashboard/sessions?limit=0", headers=admin_headers),
        await test_client.get("/api/dashboard/sessions?offset=-1", headers=admin_headers),
    ]

    assert [response.status_code for response in responses] == [422, 422, 422]


async def test_agent_stats_http_omits_removed_top_performers_contract(test_client, admin_headers):
    """智能体统计 HTTP 契约只发布对话与工具使用概览。"""
    response = await test_client.get("/api/dashboard/stats/agents", headers=admin_headers)

    assert response.status_code == 200, response.text
    assert set(response.json()) == {
        "total_agents",
        "agent_session_counts",
        "agent_tool_usage",
        "agent_names",
    }


async def test_admin_can_fetch_stats(test_client, admin_headers):
    """Test that the timeseries stats endpoint returns consistent values."""
    response = await test_client.get(
        "/api/dashboard/stats/calls/timeseries?type=models&time_range=14days",
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_count"] >= 0
    assert len(data["data"]) == 14
    assert isinstance(data["categories"], list)


async def test_knowledge_stats_matches_runtime_capability(test_client, admin_headers):
    response = await test_client.get("/api/dashboard/stats/knowledge", headers=admin_headers)

    assert response.status_code == 200, response.text
    assert set(response.json()) == {
        "total_knowledge_bases",
        "total_files",
        "total_nodes",
        "total_storage_size",
        "knowledge_bases_by_type",
        "file_type_distribution",
    }


async def test_admin_can_fetch_thread_analytics(test_client, admin_headers):
    """Test that thread analytics endpoint returns complete statistics schema."""
    response = await test_client.get(
        "/api/dashboard/stats/threads?time_range=30days",
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "summary" in data
    assert "daily_trends" in data
    assert "depth_distribution" in data
    assert "agent_distribution" in data
    assert "top_users" in data
    assert "status_distribution" in data
    assert len(data["daily_trends"]) == 30
    assert data["summary"]["total_threads"] >= 0


async def test_dashboard_http_counts_all_sessions_and_excludes_deleted(test_client, admin_headers):
    default_agent = await test_client.get("/api/agent/default", headers=admin_headers)
    assert default_agent.status_code == 200, default_agent.text
    agent = default_agent.json()["agent"]
    agent_id = str(agent.get("slug") or agent["agent_id"])
    marker = f"dashboard-scope-{uuid.uuid4().hex[:10]}"

    async def analytics():
        response = await test_client.get(
            "/api/dashboard/stats/threads", params={"time_range": "30days", "agent_id": agent_id}, headers=admin_headers
        )
        assert response.status_code == 200, response.text
        return response.json()

    baseline = await analytics()
    thread_ids = []
    for status in ("active", "member", "deleted"):
        response = await test_client.post(
            "/api/v1/agents/sessions",
            headers={**admin_headers, "Idempotency-Key": f"{marker}-{status}"},
            json={
                "agent_id": agent_id,
                "title": make_test_session_title(f"{marker}-{status}"),
            },
        )
        assert response.status_code == 201, response.text
        thread_ids.append(str(response.json()["id"]))

    await _set_session_statuses(thread_ids[1], thread_ids[2])

    all_sessions = await analytics()
    assert all_sessions["summary"]["total_threads"] == baseline["summary"]["total_threads"] + 2

    default_audit = await test_client.get(
        "/api/dashboard/sessions",
        params={"search": marker, "limit": 10},
        headers=admin_headers,
    )
    deleted_audit = await test_client.get(
        "/api/dashboard/sessions",
        params={"search": marker, "status": "deleted", "limit": 10},
        headers=admin_headers,
    )
    assert default_audit.status_code == 200, default_audit.text
    assert deleted_audit.status_code == 200, deleted_audit.text
    assert {item["thread_id"] for item in default_audit.json()["items"]} == set(thread_ids[:2])
    assert {item["thread_id"] for item in deleted_audit.json()["items"]} == {thread_ids[2]}


async def test_dashboard_http_reads_run_token_totals(test_client, admin_headers):
    """真实 HTTP 返回 PostgreSQL 同会话 Run 用量和缺失标记。"""
    from sqlalchemy import select
    from yuxi.modules.agents.models.runs import AgentRun
    from yuxi.modules.agents.models.turns import AgentTurn

    default_agent = await test_client.get("/api/agent/default", headers=admin_headers)
    assert default_agent.status_code == 200
    agent = default_agent.json()["agent"]
    agent_id = str(agent.get("slug") or agent["agent_id"])
    marker = f"dashboard-usage-{uuid.uuid4().hex[:10]}"
    response = await test_client.post(
        "/api/v1/agents/sessions",
        headers={**admin_headers, "Idempotency-Key": marker},
        json={
            "agent_id": agent_id,
            "title": make_test_session_title(marker),
        },
    )
    assert response.status_code == 201
    thread_id = str(response.json()["id"])
    engine = create_async_engine(os.environ["POSTGRES_URL"])
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            agent_session = (await db.execute(select(Session).where(Session.thread_id == thread_id))).scalar_one()
            for index, usage in enumerate(
                [
                    {"total": {"total_tokens": 120}, "complete": True, "usage_reported_call_count": 1},
                    {"total": {"total_tokens": 80}, "complete": True, "usage_reported_call_count": 1},
                ]
            ):
                run_id = f"{marker}-{index}"
                db.add(
                    AgentTurn(
                        id=f"turn-{run_id}",
                        thread_id=thread_id,
                        uid=agent_session.uid,
                        status="completed",
                        current_run_id=run_id,
                        result_run_id=run_id,
                    )
                )
                await db.flush()
                db.add(
                    AgentRun(
                        id=run_id,
                        session_record_id=agent_session.id,
                        thread_id=thread_id,
                        runtime_scope_id=thread_id,
                        turn_id=f"turn-{run_id}",
                        run_type="chat",
                        input_payload={},
                        uid=agent_session.uid,
                        agent_slug=agent_id,
                        status="completed",
                        token_usage=usage,
                    )
                )
            await db.commit()
            for expected, complete in [(200, True), (120, False), (None, False)]:
                listing = await test_client.get("/api/dashboard/sessions", headers=admin_headers, params={"search": marker})
                detail = await test_client.get(f"/api/dashboard/sessions/{thread_id}", headers=admin_headers)
                assert listing.status_code == detail.status_code == 200
                item = listing.json()["items"][0]
                assert item["status"] == "active"
                assert item["total_tokens"] == detail.json()["total_tokens"] == expected
                assert item["token_usage_complete"] is complete
                assert detail.json()["token_usage_complete"] is complete
                run_id = f"{marker}-{1 if expected == 200 else 0}"
                await db.execute(update(AgentRun).where(AgentRun.id == run_id).values(token_usage={"available": False}))
                await db.commit()
    finally:
        await engine.dispose()
