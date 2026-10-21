"""从持久待办派生暂停；事务、Thread 锁与恢复意图归调用用例。"""

from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.agents.repositories.input import AgentInputRepository


async def pause_pending_queue(db: AsyncSession, agent_session: Session) -> None:
    """调用方持有 Thread 锁，仅在仍有待办时保留暂停。"""
    agent_session.queue_paused = await AgentInputRepository(db).has_pending_inputs(
        thread_id=agent_session.thread_id, uid=agent_session.uid, app_id=agent_session.app_id
    )
