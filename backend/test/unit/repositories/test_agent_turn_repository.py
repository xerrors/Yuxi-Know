"""Turn 用量查询的持久归属边界。"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from test.support.sqlite import create_utc_sqlite_engine
from yuxi.modules.agents.repositories.turn import AgentTurnRepository
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.infrastructure.postgres.base import Base
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.agents.models.messages import Message

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


@pytest_asyncio.fixture()
async def session():
    """建立包含 Turn、Run 与 Message 约束的 SQLite 单测库。"""
    engine = create_utc_sqlite_engine()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


async def test_usage_includes_bound_final_output_across_runs_but_excludes_unbound_text(session):
    """最终 Model 行发布为 text 后仍计费，旁路 text 不能伪装为输出。"""
    agent_session = Session(thread_id="usage-thread", project_id="usage-project", uid="user-1", agent_id="main", status="active")
    session.add(agent_session)
    await session.flush()
    turn = AgentTurn(id="usage-turn", thread_id="usage-thread", uid="user-1", status="completed")
    first = AgentRun(
        id="usage-first",
        thread_id="usage-thread",
        runtime_scope_id="usage-thread",
        agent_slug="main",
        uid="user-1",
        status="yielded",
        turn_id=turn.id,
        session_record_id=agent_session.id,
        run_type="chat",
        input_payload={},
    )
    resumed = AgentRun(
        id="usage-resume",
        thread_id="usage-thread",
        runtime_scope_id="usage-thread",
        agent_slug="main",
        uid="user-1",
        status="completed",
        turn_id=turn.id,
        session_record_id=agent_session.id,
        run_type="resume",
        resume_from_run_id=first.id,
        input_payload={},
    )
    session.add_all([turn, first, resumed])
    await session.flush()

    first_audit = Message(
        session_record_id=agent_session.id,
        run_id=first.id,
        turn_id=turn.id,
        role="assistant",
        content="tool call",
        message_type="model_audit",
        operation_id="model-first",
        execution_status="completed",
        usage={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
    )
    abandoned_same_operation = Message(
        session_record_id=agent_session.id,
        run_id=first.id,
        turn_id=turn.id,
        role="assistant",
        content="",
        message_type="model_audit",
        operation_id="model-final",
        execution_status="abandoned",
    )
    unbound_text = Message(
        session_record_id=agent_session.id,
        run_id=resumed.id,
        turn_id=turn.id,
        role="assistant",
        content="unbound",
        message_type="text",
        operation_id="model-unbound",
        execution_status="completed",
        usage={"input_tokens": 900, "output_tokens": 900, "total_tokens": 1800},
    )
    wrong_run_output = Message(
        session_record_id=agent_session.id,
        run_id=resumed.id,
        turn_id=turn.id,
        role="assistant",
        content="wrong owner",
        message_type="text",
        operation_id="model-wrong-owner",
        execution_status="completed",
        usage={"input_tokens": 900, "output_tokens": 900, "total_tokens": 1800},
    )
    final_output = Message(
        session_record_id=agent_session.id,
        run_id=resumed.id,
        turn_id=turn.id,
        role="assistant",
        content="final",
        message_type="text",
        operation_id="model-final",
        execution_status="completed",
        usage={"input_tokens": 8, "output_tokens": 4, "total_tokens": 12},
    )
    session.add_all([first_audit, abandoned_same_operation, unbound_text, wrong_run_output, final_output])
    await session.flush()
    first.output_message_id = wrong_run_output.id
    resumed.output_message_id = final_output.id
    turn.current_run_id = resumed.id
    turn.result_run_id = resumed.id
    await session.flush()

    audits = await AgentTurnRepository(session).list_model_usage_audits(turn.id)

    assert [(message.run_id, message.operation_id) for message in audits] == [
        (first.id, "model-first"),
        (first.id, "model-final"),
        (resumed.id, "model-final"),
    ]
    assert audits[-1].id == final_output.id
    assert sum((message.usage or {}).get("total_tokens", 0) for message in audits) == 22


async def test_usage_includes_child_run_final_model_output_but_not_child_unbound_text(session):
    """父子 Turn 分别计量，子结果不得进入父 Turn 的输出与用量。"""
    parent_session = Session(thread_id="parent-thread", project_id="usage-project", uid="user-1", agent_id="main", status="active")
    child_session = Session(
        thread_id="child-thread",
        project_id="usage-project",
        uid="user-1",
        agent_id="main",
        status="active",
        tree_root_thread_id="parent-thread",
        parent_thread_id="parent-thread",
        cooperation_name="child",
        cooperation_path="/root/child",
    )
    session.add_all([parent_session, child_session])
    await session.flush()
    turn = AgentTurn(id="parent-turn", thread_id="parent-thread", uid="user-1", status="completed")
    parent_run = AgentRun(
        id="parent-run",
        thread_id="parent-thread",
        runtime_scope_id="parent-thread",
        agent_slug="main",
        uid="user-1",
        status="completed",
        turn_id=turn.id,
        session_record_id=parent_session.id,
        run_type="chat",
        input_payload={},
    )
    session.add_all([turn, parent_run])
    await session.flush()
    child_turn = AgentTurn(id="child-turn", thread_id="child-thread", uid="user-1", status="completed")
    session.add(child_turn)
    await session.flush()
    child_run = AgentRun(
        id="child-run",
        thread_id="child-thread",
        runtime_scope_id="parent-thread",
        agent_slug="main",
        uid="user-1",
        status="completed",
        turn_id=child_turn.id,
        session_record_id=child_session.id,
        created_by_run_id=parent_run.id,
        run_type="chat",
        input_payload={},
    )
    session.add(child_run)
    await session.flush()
    parent_audit = Message(
        session_record_id=parent_session.id,
        run_id=parent_run.id,
        turn_id=turn.id,
        role="assistant",
        content="delegate",
        message_type="model_audit",
        operation_id="parent-model",
        execution_status="completed",
        usage={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
    )
    child_unbound = Message(
        session_record_id=child_session.id,
        run_id=child_run.id,
        turn_id=child_turn.id,
        role="assistant",
        content="unbound",
        message_type="text",
        operation_id="child-unbound",
        execution_status="completed",
        usage={"input_tokens": 900, "output_tokens": 900, "total_tokens": 1800},
    )
    child_final = Message(
        session_record_id=child_session.id,
        run_id=child_run.id,
        turn_id=child_turn.id,
        role="assistant",
        content="child result",
        message_type="text",
        operation_id="child-model",
        execution_status="completed",
        usage={"input_tokens": 4, "output_tokens": 3, "total_tokens": 7},
    )
    session.add_all([parent_audit, child_unbound, child_final])
    await session.flush()
    child_run.output_message_id = child_final.id
    child_turn.current_run_id = child_run.id
    child_turn.result_run_id = child_run.id
    turn.current_run_id = parent_run.id
    turn.result_run_id = parent_run.id
    await session.flush()

    audits = await AgentTurnRepository(session).list_model_usage_audits(turn.id)

    assert [message.operation_id for message in audits] == ["parent-model"]
    child_audits = await AgentTurnRepository(session).list_model_usage_audits(child_turn.id)
    assert [message.operation_id for message in child_audits] == ["child-model"]
    assert sum(message.usage["total_tokens"] for message in child_audits) == 7
