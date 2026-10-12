"""会话标题生成的真实持久化契约。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx

import pytest

from test.integration.services.agent_input_fixtures import SCOPE
from yuxi.modules.agents.repositories.sessions import SessionRepository
from yuxi.modules.agents.services import threads

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]
pytest_plugins = ["test.integration.services.agent_input_fixtures"]


@pytest.mark.parametrize(
    "outcome", ["generated", "timeout", "quota", "manual", "placeholder", "thinking", "dangling_think", "unclosed_think", "unrelated"]
)
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
        if outcome == "quota":
            request = httpx.Request("POST", "https://models.example/chat/completions")
            response = httpx.Response(429, request=request, json={"error": "PRIVATE_UPSTREAM_QUOTA"})
            raise httpx.HTTPStatusError("quota exhausted", request=request, response=response)
        return SimpleNamespace(
            text={
                "placeholder": "标题",
                "thinking": "<think>PRIVATE_REASONING</think>PostgreSQL 慢查询优化",
                "dangling_think": "PRIVATE_REASONING</think>PostgreSQL 慢查询优化",
                "unclosed_think": "<think>PRIVATE_REASONING",
                "unrelated": "浏览器UA",
            }.get(outcome, "PostgreSQL 慢查询优化")
        )

    monkeypatch.setattr(titles, "system_options", SimpleNamespace(get=AsyncMock(return_value={"fast_model": "test:fast"})))
    monkeypatch.setattr(titles, "load_chat_model", lambda *args, **kwargs: SimpleNamespace(ainvoke=invoke))
    await titles.generate_session_title(thread_id="title-thread", uid=SCOPE.uid, app_id=None, content=text)

    async def unexpected(_messages):
        pytest.fail("同一会话重复生成标题")

    monkeypatch.setattr(titles, "load_chat_model", lambda *args, **kwargs: SimpleNamespace(ainvoke=unexpected))
    await titles.generate_session_title(thread_id="title-thread", uid=SCOPE.uid, app_id=None, content="第二条消息")
    async with sessions() as db:
        persisted = await SessionRepository(db).get_session_by_thread_id("title-thread")
        assert persisted.title == ("PostgreSQL 慢查询优化" if outcome in {"generated", "thinking", "dangling_think"} else fallback)


@pytest.mark.parametrize("message", ["回复字母 A", "回复字母 B", "回复字母 C"])
async def test_short_letter_requests_keep_source_title_instead_of_unrelated_subject(sessions, monkeypatch, message):
    """模型给出浏览器主题时，短指令标题保持原用户消息。"""
    from yuxi.modules.agents.services import titles

    async with sessions() as db:
        await SessionRepository(db).add_session(uid=SCOPE.uid, agent_id="main", project_id="input-project", thread_id="letter-title")
        await db.commit()
    monkeypatch.setattr(titles, "system_options", SimpleNamespace(get=AsyncMock(return_value={"fast_model": "test:fast"})))
    model = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(text="浏览器UA")))
    monkeypatch.setattr(titles, "load_chat_model", lambda *args, **kwargs: model)
    await titles.generate_session_title(thread_id="letter-title", uid=SCOPE.uid, app_id=None, content=message)
    async with sessions() as db:
        session = await SessionRepository(db).get_session_by_thread_id("letter-title")
        assert session.title == message
