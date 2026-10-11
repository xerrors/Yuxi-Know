"""会话标题生成的真实持久化契约。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from test.integration.services.agent_input_fixtures import SCOPE
from yuxi.modules.agents.repositories.sessions import SessionRepository
from yuxi.modules.agents.services import threads

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]
pytest_plugins = ["test.integration.services.agent_input_fixtures"]


@pytest.mark.parametrize("outcome", ["generated", "timeout", "manual"])
async def test_auto_title_persists_once_and_preserves_manual_rename(sessions, monkeypatch, outcome):
    """回读真实数据库验证生成、失败回退及手动改名优先。"""
    from yuxi.modules.agents.services import titles

    text = "请帮我分析 PostgreSQL 的慢查询并给出索引优化建议"
    fallback = text[:30]
    async with sessions() as db:
        await SessionRepository(db).add_session(
            uid=SCOPE.uid,
            agent_id="main",
            project_id="input-project",
            thread_id="title-thread",
            config_snapshot={"model": "test:chat", "tool_approval_mode": "default"},
        )
        await db.commit()

    async def invoke(_messages):
        async with sessions() as db:
            persisted = await SessionRepository(db).get_session_by_thread_id("title-thread")
            assert persisted.title == fallback
            if outcome == "manual":
                await threads.update_thread(db=db, scope=SCOPE, thread_id="title-thread", title=fallback)
        if outcome == "timeout":
            raise TimeoutError
        return SimpleNamespace(text="PostgreSQL 慢查询优化")

    monkeypatch.setattr(titles, "system_options", SimpleNamespace(get=AsyncMock(return_value={"fast_model": "test:fast"})))
    monkeypatch.setattr(titles, "load_chat_model", lambda *args, **kwargs: SimpleNamespace(ainvoke=invoke))
    await titles.generate_session_title(thread_id="title-thread", uid=SCOPE.uid, app_id=None, content=text)

    async def unexpected(_messages):
        pytest.fail("同一会话重复生成标题")

    monkeypatch.setattr(titles, "load_chat_model", lambda *args, **kwargs: SimpleNamespace(ainvoke=unexpected))
    await titles.generate_session_title(thread_id="title-thread", uid=SCOPE.uid, app_id=None, content="第二条消息")
    async with sessions() as db:
        persisted = await SessionRepository(db).get_session_by_thread_id("title-thread")
        assert persisted.title == ("PostgreSQL 慢查询优化" if outcome == "generated" else fallback)
