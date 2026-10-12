"""Thread 用户、APP 与持久状态的共同授权边界。"""

from sqlalchemy.ext.asyncio import AsyncSession
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.agents.repositories.sessions import SessionRepository
from yuxi.modules.agents.scope import ActorScope
from yuxi.shared.errors import ResourceNotFoundError


async def require_thread(*, db: AsyncSession, scope: ActorScope, thread_id: str, lock: bool = False) -> Session:
    """按用户与 APP 完整作用域读取 Thread，可选择取得调度锁。"""
    repo = SessionRepository(db)
    agent_session = await repo.lock_session_by_thread_id(thread_id) if lock else await repo.get_session_by_thread_id(thread_id)
    if (
        agent_session is None
        or agent_session.uid != scope.uid
        or agent_session.app_id != scope.app_id
        or agent_session.status not in {"active", "archived"}
    ):
        raise ResourceNotFoundError("Thread 不存在")
    return agent_session
