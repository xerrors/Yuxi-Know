"""标题检索在真实 PostgreSQL 中遵守作用域和字面匹配。"""

import pytest

from test.integration.services.agent_input_fixtures import SCOPE
from yuxi.modules.agents.repositories.sessions import SessionRepository

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]
pytest_plugins = ["test.integration.services.agent_input_fixtures"]


async def test_title_only_search_preserves_app_agent_and_literal_pattern(sessions):
    """空会话的标题分支保持 APP、Agent、归档隔离，通配字符按字面匹配。"""
    query = r"Needle%_\path"
    async with sessions() as db:
        repo = SessionRepository(db)
        for thread_id, agent, app, status, title in [
            ("web-main", "main", None, "active", query),
            ("app-main", "main", "app-one", "active", query),
            ("other-app", "main", "app-two", "active", query),
            ("web-other-agent", "other", None, "active", query),
            ("archived-title", "main", None, "archived", query),
            ("wildcard-decoy", "main", None, "active", "NeedleXXZpath"),
        ]:
            row = await repo.add_session(
                uid=SCOPE.uid,
                agent_id=agent,
                app_id=app,
                project_id="input-project",
                thread_id=thread_id,
                title=title,
            )
            row.status = status
        await db.commit()

    async with sessions() as db:
        for app, agent, expected in [
            (None, "main", "web-main"),
            ("app-one", "main", "app-main"),
            ("app-two", "main", "other-app"),
            (None, "other", "web-other-agent"),
        ]:
            rows, has_more = await SessionRepository(db).search_sessions(
                uid=SCOPE.uid,
                query=query,
                app_id=app,
                agent_id=agent,
            )
            assert has_more is False
            assert [row["agent_session"].thread_id for row in rows] == [expected]
            assert rows[0]["matched_count"] == 0
            assert rows[0]["message_id"] is None
            assert rows[0]["snippets"] == []
