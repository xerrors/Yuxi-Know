"""Public Thread 历史按 Input、Turn 和 Run 明确归属。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from test.support.sqlite import create_utc_sqlite_engine
from yuxi.infrastructure.postgres.base import Base
from yuxi.modules.agents.models.inputs import AgentInput
from yuxi.modules.agents.models.messages import Message
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.modules.agents.repositories.input import AgentInputRepository
from yuxi.modules.agents.repositories.public_items import PublicItemRepository
from yuxi.modules.agents.input_messages import build_chat_input_message, serialize_input_message
from yuxi.modules.agents.services.public_items import serialize_public_items
from yuxi.modules.agents.scope import ActorScope
from yuxi.modules.agents.services.threads import get_queue_snapshot
from yuxi.modules.agents.services.thread_access import require_thread
from yuxi.modules.workspace.models import Project
from yuxi.shared.errors import DomainError, ResourceNotFoundError

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]
SCOPE = ActorScope(uid="user-1", app_id=None)
STARTED_AT = datetime(2026, 9, 29, 9, 0, 0)


@pytest_asyncio.fixture()
async def session():
    """为真实 ORM 查询建立独立内存数据库。"""
    engine = create_utc_sqlite_engine()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add(
            Project(
                id="project-thread-1",
                uid="user-1",
                selection_status="implicit",
                directory_mode="managed",
                workdir_path="projects/project-thread-1",
            )
        )
        db.add(
            Session(
                id=1,
                thread_id="thread-1",
                project_id="project-thread-1",
                uid="user-1",
                agent_id="main",
                status="active",
            )
        )
        await db.commit()
        yield db
    await engine.dispose()


def _turn_run(*, turn_id: str, run_id: str, created_at: datetime) -> tuple[AgentTurn, AgentRun]:
    """建立一轮已完成的顶层执行。"""
    turn = AgentTurn(
        id=turn_id,
        thread_id="thread-1",
        uid="user-1",
        status="completed",
        current_run_id=run_id,
        result_run_id=run_id,
    )
    run = AgentRun(
        id=run_id,
        turn_id=turn_id,
        thread_id="thread-1",
        runtime_scope_id="thread-1",
        agent_slug="main",
        uid="user-1",
        session_record_id=1,
        run_type="chat",
        input_payload={},
        status="completed",
        created_at=created_at,
    )
    return turn, run


async def test_history_only_shows_consumed_input_and_its_own_reply(session):
    """队列正文不进入正式历史，消费后仅与自身 Turn/Run 关联。"""
    turn_a, run_a = _turn_run(turn_id="turn-a", run_id="run-a", created_at=STARTED_AT)
    session.add_all([turn_a, run_a])
    session.add(
        AgentInput(
            id="input-b",
            messages=[serialize_input_message(build_chat_input_message("B"))],
            received_seq=2,
            thread_id="thread-1",
            uid="user-1",
            agent_slug="main",
            kind="follow_up",
            status="pending",
            input_payload={},
            source="chat",
            channel="web",
            origin_metadata={},
        )
    )
    session.add_all(
        [
            Message(
                id=1,
                session_record_id=1,
                role="user",
                content="A",
                turn_id="turn-a",
                run_id="run-a",
                delivery_status="dispatched",
                created_at=STARTED_AT,
            ),
            Message(
                id=2,
                session_record_id=1,
                role="assistant",
                content="A reply",
                turn_id="turn-a",
                run_id="run-a",
                delivery_status="complete",
                created_at=STARTED_AT + timedelta(seconds=1),
            ),
        ]
    )
    await _register_visible(session)
    await session.commit()

    pending = await _read_items(session)
    assert [item["content"][0]["text"] for item in pending] == ["A", "A reply"]
    assert len((await get_queue_snapshot(db=session, scope=SCOPE, thread_id="thread-1"))["inputs"]) == 1

    turn_b, run_b = _turn_run(turn_id="turn-b", run_id="run-b", created_at=STARTED_AT + timedelta(seconds=3))
    session.add_all([turn_b, run_b])
    await session.flush()
    input_b = await session.get(AgentInput, "input-b")
    await AgentInputRepository(session).consume(inputs=[input_b], turn_id="turn-b", run_id="run-b")
    session.add(
        Message(
            id=4,
            session_record_id=1,
            role="assistant",
            content="B reply",
            turn_id="turn-b",
            run_id="run-b",
            delivery_status="complete",
            created_at=STARTED_AT + timedelta(seconds=4),
        )
    )
    await _register_visible(session)
    await session.commit()

    completed = await _read_items(session)
    assert [item["content"][0]["text"] for item in completed] == ["A", "A reply", "B", "B reply"]
    assert [(item["turn_id"], item["yuxi"]["run_id"]) for item in completed] == [
        ("turn-a", "run-a"),
        ("turn-a", "run-a"),
        ("turn-b", "run-b"),
        ("turn-b", "run-b"),
    ]
    assert len((await get_queue_snapshot(db=session, scope=SCOPE, thread_id="thread-1"))["inputs"]) == 0


async def test_history_exposes_tool_result_without_internal_model_metadata(session):
    """历史消息不泄露模型运行内部 metadata。"""
    turn, run = _turn_run(turn_id="turn-a", run_id="run-a", created_at=STARTED_AT)
    session.add_all([turn, run])
    answer = Message(
        session_record_id=1,
        role="assistant",
        content="answer",
        turn_id="turn-a",
        run_id="run-a",
        message_type="text",
        operation_id="model-a",
        delivery_status="complete",
        extra_metadata={
            "model_run_id": "private-model-run",
            "start_metadata": {"provider": "private"},
            "finish_metadata": {"model_name": "private"},
            "langfuse_trace_id": "trace-safe",
        },
    )
    session.add(answer)
    await session.flush()
    session.add(
        Message(
            session_record_id=answer.session_record_id,
            turn_id=answer.turn_id,
            run_id=answer.run_id,
            role="tool",
            message_type="tool_audit",
            operation_id="call-a",
            content="safe result",
            execution_status="completed",
            started_at=answer.created_at,
            extra_metadata={"source_model_message_id": answer.id, "tool_name": "search", "input": {"q": "Yuxi"}},
        )
    )
    await _register_visible(session)
    await session.commit()

    history = await _read_items(session)
    assert [item["type"] for item in history] == ["message", "function_call", "function_call_output"]
    assert history[1]["call_id"] == history[2]["call_id"] == "call-a"
    assert history[2]["output"] == "safe result"
    assert "private-model-run" not in str(history)


async def test_history_rejects_other_app_scope(session):
    """相同用户的另一 APP 也不能读取 Thread 历史。"""
    agent_session = await session.get(Session, 1)
    agent_session.app_id = "other-app"
    await session.commit()
    with pytest.raises(DomainError) as failure:
        await _read_items(session)
    assert isinstance(failure.value, ResourceNotFoundError)


async def _register_visible(db):
    """历史 oracle 显式登记已经发送过的 item，不由待测 serializer 生成。"""
    from sqlalchemy import select

    messages = (await db.scalars(select(Message).where(Message.role == "assistant"))).all()
    for message in messages:
        public = {
            "message": {
                "id": f"visible-{message.id}",
                "type": "message",
                "role": "assistant",
                "turn_id": message.turn_id,
                "content": [{"type": "output_text", "text": message.content}],
                "status": "completed",
                "phase": "commentary",
                "yuxi": {"run_id": message.run_id, "output_index": 0},
            }
        }
        if message.operation_id:
            public["call"] = {
                "id": "call-item",
                "type": "function_call",
                "turn_id": message.turn_id,
                "call_id": "call-a",
                "name": "search",
                "arguments": {"q": "Yuxi"},
                "status": "completed",
                "yuxi": {"run_id": message.run_id, "output_index": 1},
            }
            public["result"] = {
                "id": "result-item",
                "type": "function_call_output",
                "turn_id": message.turn_id,
                "call_id": "call-a",
                "output": "safe result",
                "error": None,
                "status": "completed",
                "yuxi": {"run_id": message.run_id, "output_index": 2},
            }
        message.extra_metadata = {**(message.extra_metadata or {}), "public_items": public}


async def _read_items(db):
    """直接验证公开 serializer 对持久消息的投影，分页由真实 PG 测试覆盖。"""
    await require_thread(db=db, scope=SCOPE, thread_id="thread-1")
    rows = await PublicItemRepository(db).list_items(thread_id="thread-1", uid=SCOPE.uid, app_id=SCOPE.app_id)
    return [item for message, run, result_id in rows for item in serialize_public_items(message, run, result_id)]
