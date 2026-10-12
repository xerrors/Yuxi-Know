"""线程历史里的图片投影：从持久 raw_message 投影官方 input content。"""

from __future__ import annotations

from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker
from test.support.sqlite import create_utc_sqlite_engine
from yuxi.modules.agents.repositories.public_items import PublicItemRepository
from yuxi.modules.agents.services.public_items import serialize_public_items
from yuxi.modules.agents.input_messages import build_chat_input_message
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.infrastructure.postgres.base import Base
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.agents.models.messages import Message
from yuxi.modules.workspace.models import Project

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

STARTED_AT = datetime(2026, 9, 25, 9, 0, 0)


@pytest_asyncio.fixture()
async def session():
    engine = create_utc_sqlite_engine()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add(
            Project(
                id="project-image-1",
                uid="user-1",
                selection_status="implicit",
                directory_mode="managed",
                workdir_path="projects/project-image-1",
            )
        )
        db.add(
            Session(
                id=1,
                thread_id="thread-images",
                project_id="project-image-1",
                uid="user-1",
                agent_id="main",
                status="active",
            )
        )
        db.add(
            AgentTurn(
                id="turn-images",
                thread_id="thread-images",
                uid="user-1",
                status="completed",
                current_run_id="run-images",
                result_run_id="run-images",
            )
        )
        db.add(
            AgentRun(
                id="run-images",
                thread_id="thread-images",
                runtime_scope_id="thread-images",
                agent_slug="main",
                uid="user-1",
                turn_id="turn-images",
                session_record_id=1,
                input_payload={},
                status="completed",
                created_at=STARTED_AT,
            )
        )
        await db.commit()
        yield db
    await engine.dispose()


async def _history(session) -> list[dict]:
    rows = await PublicItemRepository(session).list_items(thread_id="thread-images", uid="user-1", app_id=None)
    return [item for message, run, result_id in rows for item in serialize_public_items(message, run, result_id)]


async def test_多图历史行的投影按顺序给出全部图片(session):
    built = build_chat_input_message("三张图", ["A", "B", "C"])
    session.add(
        Message(
            id=1,
            session_record_id=1,
            role="user",
            content=built.content,
            turn_id="turn-images",
            run_id="run-images",
            message_type=built.message_type,
            image_content=built.image_content,
            extra_metadata={"raw_message": built.raw_message()},
            delivery_status="dispatched",
            created_at=STARTED_AT,
        )
    )
    await session.commit()

    user_message = (await _history(session))[0]

    assert [p["image_url"] for p in user_message["content"] if p["type"] == "input_image"] == [
        "data:image/jpeg;base64,A",
        "data:image/jpeg;base64,B",
        "data:image/jpeg;base64,C",
    ]


async def test_纯文本历史行不产生图片(session):
    """有 raw_message 但没有 image part 时不得凭空造出图片。"""
    built = build_chat_input_message("只有文字")
    session.add(
        Message(
            id=3,
            session_record_id=1,
            role="user",
            content=built.content,
            turn_id="turn-images",
            run_id="run-images",
            message_type=built.message_type,
            extra_metadata={"raw_message": built.raw_message()},
            delivery_status="dispatched",
            created_at=STARTED_AT,
        )
    )
    await session.commit()

    user_message = (await _history(session))[0]

    assert user_message["content"] == [{"type": "input_text", "text": "只有文字"}]
    assert user_message["yuxi"]["message_type"] == "text"


async def test_投影不外泄_raw_message_的原始形状(session):
    """DTO 给的是窄形状字符串数组，浏览器不必理解 LangChain 的 content parts。"""
    built = build_chat_input_message("两张图", ["A", "B"])
    session.add(
        Message(
            id=4,
            session_record_id=1,
            role="user",
            content=built.content,
            turn_id="turn-images",
            run_id="run-images",
            message_type=built.message_type,
            image_content=built.image_content,
            extra_metadata={"raw_message": built.raw_message()},
            delivery_status="dispatched",
            created_at=STARTED_AT,
        )
    )
    await session.commit()

    item = (await _history(session))[0]
    assert "raw_message" not in item["yuxi"]
    contents = [part["image_url"] for part in item["content"] if part["type"] == "input_image"]

    assert contents == ["data:image/jpeg;base64,A", "data:image/jpeg;base64,B"]
    assert all(isinstance(item, str) for item in contents)
