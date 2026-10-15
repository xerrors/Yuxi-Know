"""AgentRun 集成测试共享的数据工厂。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, update

from yuxi.modules.agents.models.cooperation import CooperationEvent, CooperationRuntime
from yuxi.modules.agents.models.definitions import Agent
from yuxi.modules.agents.models.inputs import AgentInput, AgentInputReceipt
from yuxi.modules.agents.repositories.input import AgentInputRepository
from yuxi.modules.agents.repositories.input_receipt import AgentInputReceiptRepository
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.agents.models.messages import Message
from yuxi.modules.workspace.models import Project
from yuxi.modules.identity.models import User
from yuxi.shared.datetime import utc_now
from yuxi.modules.agents.input_messages import build_chat_input_message, serialize_input_message


async def create_agent_run(
    session_factory,
    *,
    prefix: str,
    message_content: str,
    input_payload: dict[str, Any],
    status: str = "pending",
    worker_id: str | None = None,
    lease_expires_at: datetime | None = None,
) -> tuple[str, str, int]:
    """创建供 AgentRun 集成测试使用的最小持久化链路。"""
    run_id = str(uuid.uuid4())
    input_id = f"{prefix}-{uuid.uuid4()}"
    turn_id = f"{prefix}-{uuid.uuid4()}"
    thread_id = f"pytest-{prefix}-{uuid.uuid4()}"
    uid = f"pytest-user-{uuid.uuid4()}"
    project_id = str(uuid.uuid4())

    async with session_factory() as db:
        db.add(User(username=uid, uid=uid, password_hash="test"))
        await db.flush()
        db.add(
            Project(
                id=project_id,
                uid=uid,
                selection_status="implicit",
                workdir_path=f"projects/{project_id}",
                directory_mode="managed",
            )
        )
        await db.flush()
        agent_session = Session(
            thread_id=thread_id,
            uid=uid,
            project_id=project_id,
            agent_id="main",
            status="active",
        )
        db.add(agent_session)
        await db.flush()
        input_repo = AgentInputRepository(db)
        input_item = await input_repo.create(
            input_id=input_id,
            thread_id=thread_id,
            uid=uid,
            app_id=None,
            agent_slug="main",
            kind="follow_up",
            messages=[serialize_input_message(build_chat_input_message(message_content))],
            input_payload=dict(input_payload),
        )
        await AgentInputReceiptRepository(db).create(
            receipt_id=str(uuid.uuid4()),
            idempotency_key=str(uuid.uuid4()),
            uid=uid,
            app_id=None,
            thread_id=thread_id,
            event_type="message",
            intent_hash="test-intent",
            input_id=input_id,
        )
        turn = AgentTurn(id=turn_id, thread_id=thread_id, uid=uid, app_id=None, status="running")
        db.add(turn)
        await db.flush()
        db.add(
            AgentRun(
                id=run_id,
                thread_id=thread_id,
                runtime_scope_id=thread_id,
                agent_slug="main",
                uid=uid,
                turn_id=turn_id,
                session_record_id=agent_session.id,
                input_payload=dict(input_payload),
                status=status,
                run_type="chat",
                worker_id=worker_id,
                heartbeat_at=utc_now() if worker_id else None,
                lease_expires_at=lease_expires_at,
            )
        )
        await db.flush()
        turn.current_run_id = run_id
        [message] = await input_repo.consume(
            inputs=[input_item],
            turn_id=turn_id,
            run_id=run_id,
        )
        (await db.get(AgentRun, run_id)).input_message_id = message.id
        await db.commit()
        return run_id, thread_id, message.id


async def cleanup_agent_run_threads(session_factory, thread_ids: list[str]) -> None:
    """按外键顺序清理本测试创建的持久事实。"""
    async with session_factory() as db:
        rows = (await db.execute(select(Session.project_id, Session.uid).where(Session.thread_id.in_(thread_ids)))).all()
        session_record_ids = list((await db.scalars(select(Session.id).where(Session.thread_id.in_(thread_ids)))).all())
        input_ids = list((await db.scalars(select(AgentInput.id).where(AgentInput.thread_id.in_(thread_ids)))).all())
        await db.execute(delete(CooperationEvent).where(CooperationEvent.tree_root_thread_id.in_(thread_ids)))
        await db.execute(delete(CooperationRuntime).where(CooperationRuntime.tree_root_thread_id.in_(thread_ids)))
        await db.execute(update(Session).where(Session.thread_id.in_(thread_ids)).values(created_by_run_id=None))
        await db.execute(delete(AgentInputReceipt).where(AgentInputReceipt.thread_id.in_(thread_ids)))
        if input_ids:
            await db.execute(delete(AgentInput).where(AgentInput.id.in_(input_ids)))
        if session_record_ids:
            await db.execute(delete(Message).where(Message.session_record_id.in_(session_record_ids)))
        await db.execute(delete(AgentRun).where(AgentRun.thread_id.in_(thread_ids)))
        await db.execute(delete(AgentTurn).where(AgentTurn.thread_id.in_(thread_ids)))

        await db.execute(delete(Session).where(Session.thread_id.in_(thread_ids)))
        await db.execute(delete(Project).where(Project.id.in_([row.project_id for row in rows])))
        await db.execute(delete(Agent).where(Agent.created_by.in_([row.uid for row in rows])))
        await db.execute(delete(User).where(User.uid.in_([row.uid for row in rows])))
        await db.commit()


async def settle_locked_run(db, run, **options):
    """测试入口取得真实 Thread/Turn 锁，断言仍由调用方独立 PG 回读。"""
    from yuxi.modules.agents.repositories.turn import AgentTurnRepository
    from yuxi.modules.agents.repositories.sessions import SessionRepository
    from yuxi.modules.agents.services.runs import lock_ready_steer, settle_checkpoint

    agent_session = await SessionRepository(db).lock_session_by_thread_id(run.thread_id)
    turn = await AgentTurnRepository(db).get_for_scope(
        turn_id=run.turn_id,
        thread_id=run.thread_id,
        uid=run.uid,
        app_id=run.app_id,
        for_update=True,
    )
    pending = await lock_ready_steer(db, agent_session=agent_session, turn=turn) if options["status"] == "completed" else None
    return await settle_checkpoint(db=db, run=run, agent_session=agent_session, turn=turn, pending_steer=pending, **options)
