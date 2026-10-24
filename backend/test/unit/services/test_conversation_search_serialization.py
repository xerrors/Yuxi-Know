"""搜索视图输出必须满足 chat_router 声明的 ThreadSearchResponse，避免命中结果在响应校验处 500。"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from server.routers.chat_router import ThreadSearchResponse
from yuxi.services import conversation_service as svc
from yuxi.storage.postgres.models_business import AgentRun, Base, Conversation, Message, Project
from yuxi.utils.datetime_utils import utc_now_naive

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


@pytest_asyncio.fixture()
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


async def _seed_thread(db, *, thread_id: str, with_run: bool) -> None:
    project_id = f"project-{thread_id}"
    db.add(
        Project(
            id=project_id,
            uid="user-1",
            selection_status="implicit",
            workdir_path=f"projects/workdir-{thread_id}",
            directory_mode="managed",
        )
    )
    conversation = Conversation(
        thread_id=thread_id,
        project_id=project_id,
        uid="user-1",
        agent_id="main",
        title=f"标题 {thread_id}",
        status="active",
        extra_metadata={},
        last_viewed_run_id=None,
    )
    db.add(conversation)
    await db.flush()
    db.add(
        Message(
            conversation_id=conversation.id,
            role="user",
            content="大陆部署方案正文",
            message_type="text",
            delivery_status="complete",
            created_at=utc_now_naive(),
        )
    )
    if with_run:
        db.add(
            AgentRun(
                id=f"run-{thread_id}",
                conversation_thread_id=thread_id,
                runtime_scope_id=thread_id,
                agent_slug="main",
                uid="user-1",
                status="completed",
                request_id=f"request-{thread_id}",
                run_type="chat",
                input_payload={},
            )
        )
    await db.commit()


async def test_search_threads_view_output_satisfies_response_model(session):
    await _seed_thread(session, thread_id="thread-search-body", with_run=True)

    result = await svc.search_threads_view(
        query="大陆",
        agent_id=None,
        db=session,
        current_uid="user-1",
        limit=20,
        offset=0,
    )

    validated = ThreadSearchResponse.model_validate(result)
    assert validated.items[0].id == "thread-search-body"
    assert validated.items[0].workdir_path == "projects/workdir-thread-search-body"
    assert validated.items[0].thread_status == "ready"
    assert validated.items[0].matched_count == 1
    assert validated.items[0].snippets[0].content == "大陆部署方案正文"


async def test_search_threads_view_title_only_hit_keeps_empty_snippets(session):
    await _seed_thread(session, thread_id="thread-search-title", with_run=False)

    result = await svc.search_threads_view(
        query="thread-search-title",
        agent_id=None,
        db=session,
        current_uid="user-1",
        limit=20,
        offset=0,
    )

    validated = ThreadSearchResponse.model_validate(result)
    assert [item.id for item in validated.items] == ["thread-search-title"]
    assert validated.items[0].matched_count == 0
    assert validated.items[0].snippets == []
    assert validated.items[0].thread_status == "done"
