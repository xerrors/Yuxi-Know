"""直接调用生产生命周期边界，回读事务、归属和 lease fencing。"""

import asyncio

import pytest
from sqlalchemy import select, text

from test.integration.services.agent_input_fixtures import SCOPE, send_input, start_input_run
from yuxi.modules.agents.models.inputs import AgentInput
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.modules.agents.repositories.sessions import SessionRepository
from yuxi.modules.agents.services.run_lifecycle import lock_run_lifecycle, settle_run

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]
pytest_plugins = ["test.integration.services.agent_input_fixtures"]


@pytest.mark.parametrize(
    ("thread_id", "turn_id", "reason"),
    [("foreign-thread", None, "同一 thread"), ("input-thread", "foreign-turn", "同一 Turn")],
)
async def test_output_boundary_rejects_foreign_causality(sessions, thread_id, turn_id, reason):
    """传入相邻 Thread 或 Turn 时拒绝写入，不能借当前 Run 补齐错误归属。"""
    run = await start_input_run(sessions)
    async with sessions() as db:
        with pytest.raises(ValueError, match=reason):
            await lock_run_lifecycle(db, run_id=run.id, thread_id=thread_id, turn_id=turn_id)
        await db.rollback()
    async with sessions() as db:
        persisted = await db.get(AgentRun, run.id)
        turn = await db.get(AgentTurn, run.turn_id)
        assert persisted.status == turn.status == "running"
        assert persisted.output_message_id is None
        assert not persisted.runtime_cleanup_pending
        assert turn.current_run_id == run.id and turn.result_run_id is None


async def test_settlement_never_commits_callers_transaction(sessions):
    """调用方回滚后，Run、Turn、队列暂停和 Input 投影均保留原值。"""
    run = await start_input_run(sessions)
    async with sessions() as db:
        pending = await db.get(AgentInput, "input-0")
        assert pending is not None
        source_id = pending.id
        await settle_run(db=db, run=run, worker_id="owner", status="failed", token_usage=None)
        # 独立事务仍读到提交前事实；生命周期入口只能 flush。
        async with sessions() as observer:
            assert (await observer.get(AgentRun, run.id)).status == "running"
            assert (await observer.get(AgentTurn, run.turn_id)).status == "running"
        await db.rollback()
    async with sessions() as db:
        persisted = await db.get(AgentRun, run.id)
        assert persisted.status == "running" and persisted.worker_id == "owner"
        assert not persisted.runtime_cleanup_pending
        assert (await db.get(AgentTurn, run.turn_id)).status == "running"
        assert (await db.get(AgentInput, source_id)).status == "consumed"
        session = await SessionRepository(db).get_session_by_thread_id("input-thread")
        assert session.uid == SCOPE.uid and not session.queue_paused


async def test_settlement_cannot_replace_current_lease_owner(sessions):
    """过期的执行方不能通过生产生命周期入口提交失败或改写 Turn。"""
    run = await start_input_run(sessions)
    async with sessions() as db:
        settlement = await settle_run(db=db, run=run, worker_id="old-owner", status="failed", token_usage=None)
        assert settlement.status == "running" and not settlement.changed
        await db.commit()
    async with sessions() as db:
        persisted = await db.get(AgentRun, run.id)
        assert persisted.status == "running" and persisted.worker_id == "owner"
        assert not persisted.runtime_cleanup_pending
        assert (await db.get(AgentTurn, run.turn_id)).status == "running"


async def test_failure_settlement_locks_input_before_run(sessions):
    """Input 被持有时结算尚未锁 Run，反向锁序会使独立 NOWAIT 读取失败。"""
    run = await start_input_run(sessions)
    receipt = await send_input(sessions, "steer awaiting failure")
    loop = asyncio.get_running_loop()
    settler_pid = loop.create_future()

    async def settle():
        """保留独立事务，供观察连接定位真实数据库锁等待。"""
        async with sessions() as db:
            settler_pid.set_result(await db.scalar(text("SELECT pg_backend_pid()")))
            result = await settle_run(db=db, run=run, worker_id="owner", status="failed", token_usage=None)
            await db.commit()
            return result

    async with sessions() as holder:
        holder_pid = await holder.scalar(text("SELECT pg_backend_pid()"))
        await holder.scalar(select(AgentInput).where(AgentInput.id == receipt["input_id"]).with_for_update())
        task = asyncio.create_task(settle())
        try:
            waiting_pid = await asyncio.wait_for(settler_pid, 5)
            async with sessions() as observer:
                async with asyncio.timeout(5):
                    while not await observer.scalar(
                        text("SELECT CAST(:holder AS integer) = ANY(pg_blocking_pids(CAST(:waiting AS integer)))"),
                        {"holder": holder_pid, "waiting": waiting_pid},
                    ):
                        await asyncio.sleep(0.01)
                current = await observer.scalar(select(AgentRun).where(AgentRun.id == run.id).with_for_update(nowait=True))
                assert current.status == "running"
                await observer.rollback()
        finally:
            await holder.rollback()
            result = await asyncio.wait_for(task, 5)
    assert result.status == "failed" and result.changed
    async with sessions() as db:
        assert (await db.get(AgentRun, run.id)).status == "failed"
        assert (await db.get(AgentTurn, run.turn_id)).status == "failed"
        assert (await db.get(AgentInput, receipt["input_id"])).status == "pending"
        assert (await SessionRepository(db).get_session_by_thread_id("input-thread")).queue_paused
