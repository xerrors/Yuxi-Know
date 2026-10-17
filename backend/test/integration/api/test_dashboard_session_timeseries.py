"""会话趋势的真实 PostgreSQL 时间桶与 HTTP 协议验证。"""

import os
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.modules.agents.models.definitions import Agent
from yuxi.modules.agents.models.messages import Message
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.identity.models import User
from yuxi.modules.system.repositories.dashboard import DashboardRepository
from yuxi.modules.workspace.models import Project

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


@pytest.mark.parametrize(
    "time_range,step,expected_last",
    [
        ("14hours", timedelta(hours=1), "2001-01-01 00:00"),
        ("14days", timedelta(days=1), "2001-01-01"),
        ("14weeks", timedelta(weeks=1), "2020-01"),
    ],
)
async def test_session_buckets_use_calendar_boundaries_and_distinct_messages(time_range, step, expected_last):
    """回滚隔离的真实记录证明跨年、首桶边界、去重与审计/删除排除。"""
    engine = create_async_engine(os.environ["POSTGRES_URL"])
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            now = datetime(2020 if time_range == "14weeks" else 2001, 1, 1, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
            first = now.replace(minute=0) - 13 * step
            if time_range == "14weeks":
                first -= timedelta(days=first.weekday())
            repo = DashboardRepository(db)
            before = await repo.get_call_timeseries(metric_type="sessions", time_range=time_range, now=now)
            marker = uuid.uuid4().hex
            user = User(uid=f"ds-{marker}", username=f"ds-{marker}", role="user", password_hash="test-placeholder")
            deleted_user = User(uid=f"dd-{marker}", username=f"dd-{marker}", role="user", password_hash="test-placeholder", is_deleted=1)
            agent = Agent(slug=f"ds-{marker}", name="测试统计智能体", backend_id=f"ds-{marker}", visibility="shared", share_config={})
            db.add_all([user, deleted_user, agent])
            await db.flush()
            projects = {}
            for owner in (user, deleted_user):
                project = Project(
                    id=uuid.uuid4().hex, uid=owner.uid, selection_status="implicit", workdir_path="test/stats", directory_mode="managed"
                )
                db.add(project)
                projects[owner.uid] = project
            await db.flush()
            sessions = []
            for index, (created, status, owner) in enumerate(
                [
                    (first, "active", user),
                    (first - timedelta(microseconds=1), "active", user),
                    (now, "deleted", user),
                    (now, "active", deleted_user),
                    (now + timedelta(seconds=1), "active", user),
                ]
            ):
                session = Session(
                    thread_id=f"ds-{marker}-{index}",
                    uid=owner.uid,
                    project_id=projects[owner.uid].id,
                    agent_id=agent.slug,
                    status=status,
                    created_at=created,
                )
                db.add(session)
                sessions.append(session)
            await db.flush()
            for index, created, audit in [
                (0, first, False),
                (0, first + timedelta(seconds=1), False),
                (0, first + step, False),
                (0, first - timedelta(microseconds=1), False),
                (1, first, True),
                (2, first, False),
                (3, first, False),
                (1, now + timedelta(seconds=1), False),
            ]:
                db.add(
                    Message(
                        session_record_id=sessions[index].id,
                        role="assistant",
                        content="" if audit else "test",
                        created_at=created,
                        message_type="tool_audit" if audit else None,
                    )
                )
            await db.flush()
            after = await repo.get_call_timeseries(metric_type="sessions", time_range=time_range, now=now)
            assert len(after["data"]) == 14
            assert after["data"][-1]["date"] == expected_last
            assert len({row["date"] for row in after["data"]}) == 14
            assert after["categories"] == ["new_threads", "active_threads"]
            deltas = [
                {key: current["data"][key] - original["data"][key] for key in after["categories"]}
                for current, original in zip(after["data"], before["data"], strict=True)
            ]
            assert (
                deltas
                == [{"new_threads": 1, "active_threads": 1}, {"new_threads": 0, "active_threads": 1}]
                + [{"new_threads": 0, "active_threads": 0}] * 12
            )
            assert after["total_count"] - before["total_count"] == 1
            assert all(row["total"] == row["data"]["new_threads"] for row in after["data"])
            await db.rollback()
    finally:
        await engine.dispose()


async def test_session_timeseries_http_ranges_and_authorization(test_client, admin_headers, standard_user):
    """真实 HTTP 接受三个范围且仍只允许超级管理员读取。"""
    path = "/api/dashboard/stats/calls/timeseries?type=sessions"
    for time_range in ("14hours", "14days", "14weeks"):
        response = await test_client.get(f"{path}&time_range={time_range}", headers=admin_headers)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["categories"] == ["new_threads", "active_threads"]
        assert len(payload["data"]) == 14
        assert payload["total_count"] == sum(row["data"]["new_threads"] for row in payload["data"])
        assert all(set(row["data"]) == {"new_threads", "active_threads"} for row in payload["data"])
    assert (await test_client.get(path)).status_code == 401
    assert (await test_client.get(path, headers=standard_user["headers"])).status_code == 403
    assert (await test_client.get(f"{path}&time_range=30days", headers=admin_headers)).status_code == 422


async def test_agent_distribution_http_ranges_and_authorization(test_client, admin_headers, standard_user):
    """独立范围接口返回同口径摘要且权限和范围校验生效。"""
    path = "/api/dashboard/stats/agents/sessions"
    counts = []
    for time_range in ("all", "3months", "30days", "7days"):
        response = await test_client.get(f"{path}?time_range={time_range}", headers=admin_headers)
        assert response.status_code == 200, response.text
        payload = response.json()
        rows = payload["agent_distribution"]
        count = sum(row["thread_count"] for row in rows)
        messages = sum(row["message_count"] for row in rows)
        assert payload["agent_count"] == len(rows)
        assert payload["total_threads"] == count
        assert payload["avg_messages_per_thread"] == (round(messages / count, 1) if count else 0)
        counts.append(count)
    assert counts == sorted(counts, reverse=True)
    assert (await test_client.get(path)).status_code == 401
    assert (await test_client.get(path, headers=standard_user["headers"])).status_code == 403
    assert (await test_client.get(f"{path}?time_range=invalid", headers=admin_headers)).status_code == 422


@pytest.mark.parametrize(
    "time_range,expected_threads,expected_messages", [("all", 8, 11), ("3months", 6, 10), ("30days", 4, 7), ("7days", 2, 4)]
)
async def test_agent_distribution_postgres_created_ranges(time_range, expected_threads, expected_messages):
    """回滚隔离的真实 PostgreSQL 记录证明范围边界、加权均值与排除条件。"""
    engine = create_async_engine(os.environ["POSTGRES_URL"])
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            now = datetime(2020, 5, 31, 12, tzinfo=ZoneInfo("Asia/Shanghai"))
            repo = DashboardRepository(db)
            baseline = await repo.get_agent_session_distribution(time_range=time_range, now=now)
            marker = uuid.uuid4().hex
            user = User(uid=f"dist-{marker}", username=f"dist-{marker}", role="user", password_hash="test-placeholder")
            deleted = User(uid=f"dist-d-{marker}", username=f"dist-d-{marker}", role="user", password_hash="test-placeholder", is_deleted=1)
            agents = [
                Agent(slug=f"dist-{marker}-{i}", name=f"统计测试{i}", backend_id=f"dist-{marker}-{i}", visibility="shared", share_config={})
                for i in range(2)
            ]
            db.add_all([user, deleted, *agents])
            await db.flush()
            projects = {
                owner.uid: Project(
                    id=uuid.uuid4().hex,
                    uid=owner.uid,
                    selection_status="implicit",
                    workdir_path="test/distribution",
                    directory_mode="managed",
                )
                for owner in (user, deleted)
            }
            db.add_all(list(projects.values()))
            await db.flush()
            fixtures = [
                (datetime(2019, 1, 1), 1),
                (datetime(2020, 2, 28, 23, 59, 59, 999999), 0),
                (datetime(2020, 2, 29), 2),
                (datetime(2020, 5, 1, 23, 59, 59, 999999), 1),
                (datetime(2020, 5, 2), 3),
                (datetime(2020, 5, 24, 23, 59, 59, 999999), 0),
                (datetime(2020, 5, 25), 4),
                (datetime(2020, 5, 31), 0),
            ]
            sessions = []
            for index, (created, messages) in enumerate(fixtures):
                session = Session(
                    thread_id=f"dist-{marker}-{index}",
                    uid=user.uid,
                    project_id=projects[user.uid].id,
                    agent_id=agents[1 if index == 7 else 0].slug,
                    status="active",
                    created_at=created.replace(tzinfo=ZoneInfo("Asia/Shanghai")),
                )
                db.add(session)
                await db.flush()
                sessions.append(session)
                db.add_all(
                    [Message(session_record_id=session.id, role="assistant", content="sample", created_at=now) for _ in range(messages)]
                )
            for message_type in ("model_audit", "tool_audit"):
                db.add(Message(session_record_id=sessions[6].id, role="assistant", content="", created_at=now, message_type=message_type))
            db.add(Message(session_record_id=sessions[6].id, role="assistant", content="future", created_at=now + timedelta(seconds=1)))
            for index, (created, status, owner) in enumerate(
                [(now + timedelta(seconds=1), "active", user), (now, "deleted", user), (now, "active", deleted)]
            ):
                db.add(
                    Session(
                        thread_id=f"dist-x-{marker}-{index}",
                        uid=owner.uid,
                        project_id=projects[owner.uid].id,
                        agent_id=agents[0].slug,
                        status=status,
                        created_at=created,
                    )
                )
            await db.flush()

            result = await repo.get_agent_session_distribution(time_range=time_range, now=now)
            fixture_rows = [row for row in result["agent_distribution"] if row["agent_id"] in {agent.slug for agent in agents}]
            assert sum(row["thread_count"] for row in fixture_rows) == expected_threads
            assert sum(row["message_count"] for row in fixture_rows) == expected_messages
            assert result["total_threads"] == baseline["total_threads"] + expected_threads
            assert result["agent_count"] == baseline["agent_count"] + 2
            total_messages = sum(row["message_count"] for row in baseline["agent_distribution"]) + expected_messages
            assert result["avg_messages_per_thread"] == round(total_messages / result["total_threads"], 1)
            empty_agent = next(row for row in fixture_rows if row["agent_id"] == agents[1].slug)
            assert empty_agent["thread_count"] == 1 and empty_agent["avg_messages"] == 0
            await db.rollback()
    finally:
        await engine.dispose()
