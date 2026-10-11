from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import HTTPException
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import async_sessionmaker

from test.support.sqlite import create_utc_sqlite_engine

from yuxi.api.routers.dashboard import (
    dashboard,
    get_all_sessions,
    get_session_detail,
    get_tool_call_stats,
    get_user_activity_stats,
)
from yuxi.api.dependencies.auth import get_superadmin_user
from yuxi.modules.agents.models.definitions import Agent
from yuxi.infrastructure.postgres.base import Base
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.identity.models import Department, User
from yuxi.modules.agents.models.messages import Message, ToolCall
from yuxi.shared.datetime import utc_now

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


@pytest_asyncio.fixture()
async def dashboard_session():
    engine = create_utc_sqlite_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        dept_a = Department(name="Dept A")
        dept_b = Department(name="Dept B")
        superadmin = User(
            username="Super Admin",
            uid="superadmin",
            password_hash="$argon2id$placeholder",
            role="superadmin",
            department=dept_a,
        )
        admin_a = User(
            username="Admin A",
            uid="admin_a",
            password_hash="$argon2id$placeholder",
            role="admin",
            department=dept_a,
        )
        user_a = User(
            username="User A",
            uid="user_a",
            password_hash="$argon2id$placeholder",
            role="user",
            department=dept_a,
        )
        admin_b = User(
            username="Admin B",
            uid="admin_b",
            password_hash="$argon2id$placeholder",
            role="admin",
            department=dept_b,
        )
        user_b = User(
            username="User B",
            uid="user_b",
            password_hash="$argon2id$placeholder",
            role="user",
            department=dept_b,
        )
        agent = Agent(
            visibility="shared",
            slug="agent-shared",
            backend_id="shared-backend",
            name="Shared Agent",
            share_config={},
        )
        now = utc_now()
        session_a = Session(
            thread_id="thread-a",
            project_id="project-thread-a",
            uid="user_a",
            agent_id="agent-shared",
            title="Dept A agent_session",
            status="active",
            created_at=now,
            updated_at=now,
        )
        session_b = Session(
            thread_id="thread-b",
            project_id="project-thread-b",
            uid="user_b",
            agent_id="agent-shared",
            title="Dept B agent_session",
            status="active",
            created_at=now,
            updated_at=now,
        )
        message_a = Message(agent_session=session_a, role="assistant", content="A", created_at=now)
        message_b = Message(agent_session=session_b, role="assistant", content="B", created_at=now)
        tool_call_a = ToolCall(message=message_a, tool_name="dept_a_tool", status="success", created_at=now)
        tool_call_b = ToolCall(message=message_b, tool_name="dept_b_tool", status="success", created_at=now)
        db.add_all(
            [
                dept_a,
                dept_b,
                superadmin,
                admin_a,
                user_a,
                admin_b,
                user_b,
                agent,
                session_a,
                session_b,
                message_a,
                message_b,
                tool_call_a,
                tool_call_b,
            ]
        )
        await db.commit()
        for item in [
            dept_a,
            dept_b,
            superadmin,
            admin_a,
            user_a,
            admin_b,
            user_b,
            session_a,
            session_b,
        ]:
            await db.refresh(item)
        yield {"db": db, "superadmin": superadmin, "admin_a": admin_a}
    await engine.dispose()


async def test_dashboard_routes_require_superadmin_dependency():
    dashboard_routes = [route for route in dashboard.routes if isinstance(route, APIRoute)]

    assert dashboard_routes
    for route in dashboard_routes:
        dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
        assert get_superadmin_user in dependency_calls


async def test_dashboard_dependency_rejects_department_admin(dashboard_session):
    with pytest.raises(HTTPException) as exc:
        await get_superadmin_user(dashboard_session["admin_a"])

    assert exc.value.status_code == 403


async def test_session_list_superadmin_sees_all_departments(dashboard_session):
    response = await get_all_sessions(db=dashboard_session["db"], current_user=dashboard_session["superadmin"])

    assert response["total"] == 2
    assert {item["thread_id"] for item in response["items"]} == {"thread-a", "thread-b"}


async def test_session_detail_superadmin_can_view_other_department(dashboard_session):
    response = await get_session_detail(
        "thread-b",
        db=dashboard_session["db"],
        current_user=dashboard_session["superadmin"],
    )

    assert response["thread_id"] == "thread-b"


async def test_user_activity_stats_superadmin_include_all_departments(dashboard_session):
    stats = await get_user_activity_stats(db=dashboard_session["db"], current_user=dashboard_session["superadmin"])

    assert stats.total_users == 5
    assert stats.active_users_24h == 2
    assert stats.active_users_30d == 2


async def test_tool_stats_superadmin_include_all_departments(dashboard_session):
    stats = await get_tool_call_stats(db=dashboard_session["db"], current_user=dashboard_session["superadmin"])

    assert stats.total_calls == 2
    assert stats.successful_calls == 2
    assert {tool["tool_name"] for tool in stats.most_used_tools} == {"dept_a_tool", "dept_b_tool"}
