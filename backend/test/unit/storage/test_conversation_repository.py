from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.repositories.conversation_repository import (
    ConversationRepository,
    INVOCATION_CONVERSATION_SOURCES,
    MAX_CONVERSATION_TITLE_LENGTH,
)
from yuxi.storage.postgres.models_business import AgentRun, Base, Conversation, ConversationStats, Message, ToolCall
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = pytest.mark.unit


@pytest_asyncio.fixture()
async def conversation_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


def test_normalize_title_truncates_when_too_long():
    repo = ConversationRepository(None)  # type: ignore[arg-type]
    raw = "a" * (MAX_CONVERSATION_TITLE_LENGTH + 50)

    normalized = repo._normalize_title(raw)

    assert normalized is not None
    assert len(normalized) == MAX_CONVERSATION_TITLE_LENGTH
    assert normalized == "a" * MAX_CONVERSATION_TITLE_LENGTH


def test_normalize_title_trims_spaces():
    repo = ConversationRepository(None)  # type: ignore[arg-type]

    normalized = repo._normalize_title("   hello world   ")

    assert normalized == "hello world"


@pytest.mark.asyncio
async def test_list_agent_runs_for_trace_returns_latest_bounded_window_in_order(conversation_session):
    now = utc_now_naive()
    conversation = Conversation(
        thread_id="thread-run-trace-window",
        project_id="project-run-trace-window",
        uid="user-a",
        agent_id="agent-a",
        title="Run trace window",
        status="active",
        created_at=now,
        updated_at=now,
    )
    conversation_session.add(conversation)
    await conversation_session.flush()
    for index in range(3):
        created_at = now + timedelta(seconds=index)
        conversation_session.add(
            AgentRun(
                id=f"run-trace-{index}",
                conversation_thread_id=conversation.thread_id,
                runtime_scope_id=conversation.thread_id,
                agent_slug="main",
                uid=conversation.uid,
                status="completed",
                request_id=f"request-trace-{index}",
                conversation_id=conversation.id,
                input_payload={},
                created_at=created_at,
                started_at=created_at,
                finished_at=created_at,
            )
        )
    await conversation_session.commit()

    runs, truncated = await ConversationRepository(conversation_session).list_agent_runs_for_trace(
        conversation.id,
        limit=2,
    )

    assert [run.id for run in runs] == ["run-trace-1", "run-trace-2"]
    assert truncated is True


@pytest.mark.asyncio
async def test_lock_conversation_refreshes_cached_lifecycle_state(tmp_path):
    """加锁读取必须刷新同一 Session 中已缓存的生命周期状态。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'conversation-lock.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with factory() as reader, factory() as writer:
            conversation = Conversation(
                thread_id="thread-refresh-lock",
                project_id="project-refresh-lock",
                uid="user-a",
                agent_id="agent-a",
                title="Refresh lock",
                status="active",
            )
            reader.add(conversation)
            await reader.commit()

            repository = ConversationRepository(reader)
            cached = await repository.get_conversation_by_id(conversation.id)
            assert cached is conversation
            assert cached.status == "active"

            await writer.execute(
                update(Conversation).where(Conversation.id == conversation.id).values(status="deleted")
            )
            await writer.commit()

            locked = await repository.lock_conversation_by_thread_id(conversation.thread_id)

            assert locked is conversation
            assert locked.status == "deleted"
    finally:
        await engine.dispose()


def _seed_invocation_excluding_conversations() -> tuple[Conversation, Conversation, Conversation, datetime]:
    now = utc_now_naive()
    normal = Conversation(
        thread_id="thread-normal",
        project_id="project-thread-normal",
        uid="user-a",
        agent_id="agent-a",
        title="Normal",
        status="active",
        created_at=now,
        updated_at=now,
        extra_metadata={},
    )
    agent_call = Conversation(
        thread_id="thread-call",
        project_id="project-thread-call",
        uid="user-a",
        agent_id="agent-a",
        title="Agent Call Run",
        status="active",
        is_pinned=True,
        created_at=now,
        updated_at=now + timedelta(minutes=2),
        extra_metadata={"source": "agent_call"},
    )
    agent_eval = Conversation(
        thread_id="thread-eval",
        project_id="project-thread-eval",
        uid="user-a",
        agent_id="agent-a",
        title="Agent Evaluation Run",
        status="active",
        created_at=now,
        updated_at=now + timedelta(minutes=1),
        extra_metadata={"source": "agent_evaluation"},
    )
    return normal, agent_call, agent_eval, now


@pytest.mark.asyncio
async def test_model_audit_messages_are_hidden_from_history_and_message_count(conversation_session):
    now = utc_now_naive()
    conversation = Conversation(
        thread_id="thread-model-audit",
        project_id="project-model-audit",
        uid="user-a",
        agent_id="agent-a",
        title="Model Audit",
        status="active",
        created_at=now,
        updated_at=now,
    )
    conversation_session.add(conversation)
    await conversation_session.flush()
    stats = ConversationStats(conversation_id=conversation.id, message_count=0)
    visible_message = Message(
        conversation_id=conversation.id,
        role="user",
        content="visible",
        message_type="text",
    )
    audit_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content="hidden intermediate",
        message_type="model_audit",
        operation_id="model-1",
        execution_status="completed",
    )
    tool_audit = Message(
        conversation_id=conversation.id,
        role="tool",
        content="hidden tool output",
        message_type="tool_audit",
        operation_id="tool-1",
        started_at=now,
        sequence=2,
        execution_status="completed",
    )
    conversation_session.add_all([stats, visible_message, audit_message, tool_audit])
    await conversation_session.commit()

    repo = ConversationRepository(conversation_session)
    messages = await repo.get_messages(conversation.id)
    await repo._update_message_count(conversation.id)

    assert [message.content for message in messages] == ["visible"]
    assert stats.message_count == 1

    previous_updated_at = conversation.updated_at
    await repo.publish_assistant_output(audit_message)
    published_messages = await repo.get_messages(conversation.id)

    assert [message.content for message in published_messages] == ["visible", "hidden intermediate"]
    assert audit_message.message_type == "text"
    assert stats.message_count == 2
    assert conversation.updated_at > previous_updated_at


@pytest.mark.asyncio
async def test_only_state_proven_terminal_model_audit_keeps_tool_call_visible(conversation_session):
    now = utc_now_naive()
    conversation = Conversation(
        thread_id="thread-tool-audit",
        project_id="project-tool-audit",
        uid="user-a",
        agent_id="agent-a",
        title="Tool Audit",
        status="active",
        created_at=now,
        updated_at=now,
    )
    conversation_session.add(conversation)
    await conversation_session.flush()
    runs = [
        AgentRun(
            id="run-active",
            conversation_thread_id=conversation.thread_id,
            runtime_scope_id=conversation.thread_id,
            agent_slug="main",
            uid=conversation.uid,
            status="running",
            request_id="request-active",
            conversation_id=conversation.id,
            input_payload={},
        ),
        AgentRun(
            id="run-unproven",
            conversation_thread_id=conversation.thread_id,
            runtime_scope_id=conversation.thread_id,
            agent_slug="main",
            uid=conversation.uid,
            status="completed",
            request_id="request-unproven",
            conversation_id=conversation.id,
            input_payload={},
        ),
        AgentRun(
            id="run-proven",
            conversation_thread_id=conversation.thread_id,
            runtime_scope_id=conversation.thread_id,
            agent_slug="main",
            uid=conversation.uid,
            status="interrupted",
            request_id="request-proven",
            conversation_id=conversation.id,
            input_payload={},
        ),
    ]
    conversation_session.add_all(runs)
    await conversation_session.flush()
    audit_messages = [
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content="active",
            message_type="model_audit",
            extra_metadata={"state_reconciled": True},
            run_id="run-active",
            operation_id="model-active",
            execution_status="completed",
        ),
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content="unproven",
            message_type="model_audit",
            run_id="run-unproven",
            operation_id="model-unproven",
            execution_status="completed",
        ),
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content="proven",
            message_type="model_audit",
            extra_metadata={"state_reconciled": True},
            run_id="run-proven",
            operation_id="model-proven",
            execution_status="completed",
        ),
    ]
    conversation_session.add_all(audit_messages)
    await conversation_session.flush()
    conversation_session.add_all(
        [
            ToolCall(
                message_id=message.id,
                langgraph_tool_call_id=f"tool-{message.operation_id}",
                tool_name="search",
                status="success",
            )
            for message in audit_messages
        ]
    )
    await conversation_session.commit()

    messages = await ConversationRepository(conversation_session).get_messages(conversation.id)

    assert [message.content for message in messages] == ["proven"]
    assert messages[0].tool_calls[0].langgraph_tool_call_id == "tool-model-proven"


@pytest.mark.asyncio
async def test_list_conversations_excludes_invocation_sources(conversation_session):
    normal, agent_call, agent_eval, _ = _seed_invocation_excluding_conversations()
    conversation_session.add_all([normal, agent_call, agent_eval])
    await conversation_session.commit()

    repo = ConversationRepository(conversation_session)
    items = await repo.list_conversations(
        uid="user-a",
        limit=20,
        offset=0,
        exclude_sources=INVOCATION_CONVERSATION_SOURCES,
    )

    assert [item.thread_id for item in items] == ["thread-normal"]


@pytest.mark.asyncio
async def test_list_conversations_paginates_only_non_pinned_items(conversation_session):
    now = utc_now_naive()
    pinned = Conversation(
        thread_id="thread-pinned",
        project_id="project-pinned",
        uid="user-a",
        agent_id="agent-a",
        title="Pinned",
        status="active",
        is_pinned=True,
        created_at=now,
        updated_at=now + timedelta(minutes=10),
    )
    regular = [
        Conversation(
            thread_id=f"thread-{index}",
            project_id=f"project-{index}",
            uid="user-a",
            agent_id="agent-a",
            title=f"Thread {index}",
            status="active",
            created_at=now,
            updated_at=now + timedelta(minutes=index),
        )
        for index in range(4)
    ]
    conversation_session.add_all([pinned, *regular])
    await conversation_session.commit()

    repository = ConversationRepository(conversation_session)
    first_page = await repository.list_conversations(uid="user-a", limit=2, offset=0)
    second_page = await repository.list_conversations(uid="user-a", limit=2, offset=2)

    assert [item.thread_id for item in first_page] == ["thread-pinned", "thread-3", "thread-2"]
    assert [item.thread_id for item in second_page] == ["thread-pinned", "thread-1", "thread-0"]


@pytest.mark.asyncio
async def test_search_conversations_filters_user_status_and_tool_messages(conversation_session):
    now = utc_now_naive()
    active = Conversation(
        thread_id="thread-active",
        project_id="project-thread-active",
        uid="user-a",
        agent_id="agent-a",
        title="Active Thread",
        status="active",
        created_at=now,
        updated_at=now,
    )
    deleted = Conversation(
        thread_id="thread-deleted",
        project_id="project-thread-deleted",
        uid="user-a",
        agent_id="agent-a",
        title="Deleted Thread",
        status="deleted",
        created_at=now,
        updated_at=now,
    )
    other_user = Conversation(
        thread_id="thread-other-user",
        project_id="project-thread-other-user",
        uid="user-b",
        agent_id="agent-a",
        title="Other User Thread",
        status="active",
        created_at=now,
        updated_at=now,
    )
    tool_only = Conversation(
        thread_id="thread-tool-only",
        project_id="project-thread-tool-only",
        uid="user-a",
        agent_id="agent-a",
        title="Tool Only Thread",
        status="active",
        created_at=now,
        updated_at=now,
    )
    conversation_session.add_all([active, deleted, other_user, tool_only])
    await conversation_session.flush()
    conversation_session.add_all(
        [
            Message(
                conversation=active,
                role="assistant",
                content="大陆部署方案需要保留",
                message_type="text",
                created_at=now,
            ),
            Message(
                conversation=deleted,
                role="assistant",
                content="大陆 deleted should not show",
                message_type="text",
                created_at=now,
            ),
            Message(
                conversation=other_user,
                role="assistant",
                content="大陆 other user should not show",
                message_type="text",
                created_at=now,
            ),
            Message(
                conversation=tool_only,
                role="tool",
                content="大陆 tool output should not show",
                message_type="tool_result",
                created_at=now,
            ),
        ]
    )
    await conversation_session.commit()

    repo = ConversationRepository(conversation_session)
    items, has_more = await repo.search_conversations(
        uid="user-a",
        query="大陆",
        limit=20,
        offset=0,
    )

    assert has_more is False
    assert [item["conversation"].thread_id for item in items] == ["thread-active"]
    assert items[0]["matched_count"] == 1
    assert items[0]["message_id"] is not None
    assert "大陆部署方案" in items[0]["snippets"][0]["content"]


@pytest.mark.asyncio
async def test_search_conversations_excludes_invocation_sources(conversation_session):
    normal, agent_call, agent_eval, now = _seed_invocation_excluding_conversations()
    conversation_session.add_all([normal, agent_call, agent_eval])
    await conversation_session.flush()
    conversation_session.add_all(
        [
            Message(conversation=normal, role="user", content="导航隐藏检查", message_type="text", created_at=now),
            Message(
                conversation=agent_call,
                role="user",
                content="导航隐藏检查 call",
                message_type="text",
                created_at=now,
            ),
            Message(
                conversation=agent_eval,
                role="user",
                content="导航隐藏检查 eval",
                message_type="text",
                created_at=now,
            ),
        ]
    )
    await conversation_session.commit()

    repo = ConversationRepository(conversation_session)
    items, has_more = await repo.search_conversations(
        uid="user-a",
        query="导航隐藏检查",
        limit=20,
        offset=0,
        exclude_sources=INVOCATION_CONVERSATION_SOURCES,
    )

    assert has_more is False
    assert [item["conversation"].thread_id for item in items] == ["thread-normal"]


@pytest.mark.asyncio
async def test_search_conversations_filters_agent_and_paginates(conversation_session):
    now = utc_now_naive()
    old = now - timedelta(days=1)
    first = Conversation(
        thread_id="thread-first",
        project_id="project-thread-first",
        uid="user-a",
        agent_id="agent-a",
        title="First",
        status="active",
        created_at=old,
        updated_at=old,
    )
    second = Conversation(
        thread_id="thread-second",
        project_id="project-thread-second",
        uid="user-a",
        agent_id="agent-a",
        title="Second",
        status="active",
        created_at=now,
        updated_at=now,
    )
    other_agent = Conversation(
        thread_id="thread-other-agent",
        project_id="project-thread-other-agent",
        uid="user-a",
        agent_id="agent-b",
        title="Other Agent",
        status="active",
        created_at=now,
        updated_at=now,
    )
    conversation_session.add_all([first, second, other_agent])
    await conversation_session.flush()
    conversation_session.add_all(
        [
            Message(
                conversation=first,
                role="user",
                content="大陆关键词 old",
                message_type="text",
                created_at=old,
            ),
            Message(
                conversation=second,
                role="assistant",
                content="大陆关键词 latest",
                message_type="text",
                created_at=now,
            ),
            Message(
                conversation=other_agent,
                role="assistant",
                content="大陆关键词 other agent",
                message_type="text",
                created_at=now,
            ),
        ]
    )
    await conversation_session.commit()

    repo = ConversationRepository(conversation_session)
    first_page, has_more = await repo.search_conversations(
        uid="user-a",
        agent_id="agent-a",
        query="大陆",
        limit=1,
        offset=0,
    )
    second_page, second_has_more = await repo.search_conversations(
        uid="user-a",
        agent_id="agent-a",
        query="大陆",
        limit=1,
        offset=1,
    )

    assert has_more is True
    assert [item["conversation"].thread_id for item in first_page] == ["thread-second"]
    assert second_has_more is False
    assert [item["conversation"].thread_id for item in second_page] == ["thread-first"]


@pytest.mark.asyncio
async def test_search_conversations_matches_title_without_message_hit(conversation_session):
    now = utc_now_naive()
    old = now - timedelta(days=1)
    title_only = Conversation(
        thread_id="thread-title-only",
        project_id="project-thread-title-only",
        uid="user-a",
        agent_id="agent-a",
        title="大陆标题命中",
        status="active",
        created_at=now,
        updated_at=now,
    )
    body_match = Conversation(
        thread_id="thread-body-match",
        project_id="project-thread-body-match",
        uid="user-a",
        agent_id="agent-a",
        title="正文命中",
        status="active",
        created_at=old,
        updated_at=old,
    )
    conversation_session.add_all([title_only, body_match])
    await conversation_session.flush()
    await conversation_session.commit()
    conversation_session.add(
        Message(
            conversation=body_match,
            role="user",
            content="大陆正文命中",
            message_type="text",
            created_at=old,
        )
    )
    await conversation_session.commit()

    repo = ConversationRepository(conversation_session)
    items, has_more = await repo.search_conversations(uid="user-a", query="大陆", limit=20, offset=0)

    assert has_more is False
    assert [item["conversation"].thread_id for item in items] == ["thread-title-only", "thread-body-match"]

    title_item = items[0]
    assert title_item["matched_count"] == 0
    assert title_item["latest_match_at"] is None
    assert title_item["message_id"] is None
    assert title_item["snippets"] == []

    body_item = items[1]
    assert body_item["matched_count"] == 1
    assert "大陆正文命中" in body_item["snippets"][0]["content"]


@pytest.mark.asyncio
async def test_search_conversations_title_match_stays_within_user_and_agent_scope(conversation_session):
    now = utc_now_naive()
    mine = Conversation(
        thread_id="thread-mine",
        project_id="project-thread-mine",
        uid="user-a",
        agent_id="agent-a",
        title="大陆我的标题",
        status="active",
        created_at=now,
        updated_at=now,
    )
    other_user = Conversation(
        thread_id="thread-other-user-title",
        project_id="project-thread-other-user-title",
        uid="user-b",
        agent_id="agent-a",
        title="大陆别人的标题",
        status="active",
        created_at=now,
        updated_at=now,
    )
    deleted = Conversation(
        thread_id="thread-deleted-title",
        project_id="project-thread-deleted-title",
        uid="user-a",
        agent_id="agent-a",
        title="大陆已删除标题",
        status="deleted",
        created_at=now,
        updated_at=now,
    )
    other_agent = Conversation(
        thread_id="thread-other-agent-title",
        project_id="project-thread-other-agent-title",
        uid="user-a",
        agent_id="agent-b",
        title="大陆其他智能体标题",
        status="active",
        created_at=now,
        updated_at=now,
    )
    conversation_session.add_all([mine, other_user, deleted, other_agent])
    await conversation_session.commit()

    repo = ConversationRepository(conversation_session)
    items, has_more = await repo.search_conversations(
        uid="user-a",
        agent_id="agent-a",
        query="大陆",
        limit=20,
        offset=0,
    )

    assert has_more is False
    assert [item["conversation"].thread_id for item in items] == ["thread-mine"]


async def test_search_conversations_treats_like_wildcards_as_literals(conversation_session):
    """查询中的 %/_ 按字面匹配，不得作为 ilike 通配符扩大命中面（负向：去掉转义后 pattern 会命中含 50x 的正文）。"""
    now = utc_now_naive()
    literal = Conversation(
        thread_id="thread-literal-percent",
        project_id="project-thread-literal-percent",
        uid="user-a",
        agent_id="agent-a",
        title="进度报告",
        status="active",
        created_at=now,
        updated_at=now,
    )
    wildcard_bait = Conversation(
        thread_id="thread-wildcard-bait",
        project_id="project-thread-wildcard-bait",
        uid="user-a",
        agent_id="agent-a",
        title="另一份报告",
        status="active",
        created_at=now,
        updated_at=now,
    )
    conversation_session.add_all([literal, wildcard_bait])
    await conversation_session.flush()
    for conversation, content in ((literal, "完成率 50% 目标"), (wildcard_bait, "完成率 50x 目标")):
        conversation_session.add(
            Message(
                conversation=conversation,
                role="user",
                content=content,
                message_type="text",
                created_at=now,
            )
        )
    await conversation_session.commit()

    repo = ConversationRepository(conversation_session)
    items, _ = await repo.search_conversations(uid="user-a", query="50%", limit=20, offset=0)
    assert [item["conversation"].thread_id for item in items] == ["thread-literal-percent"]

    items, _ = await repo.search_conversations(uid="user-a", query="完成率_ 目标", limit=20, offset=0)
    assert items == []
