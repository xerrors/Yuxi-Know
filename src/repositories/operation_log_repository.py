"""操作日志数据访问层 - Repository"""

from typing import Any

from sqlalchemy import select

from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import OperationLog


class OperationLogRepository:
    """操作日志数据访问层"""

    async def get_by_id(self, id: int) -> OperationLog | None:
        """根据 ID 获取操作日志"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(OperationLog).where(OperationLog.id == id))
            return result.scalar_one_or_none()

    async def list_by_user(
        self, user_id: int, skip: int = 0, limit: int = 100
    ) -> list[OperationLog]:
        """获取用户的操作日志列表"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(OperationLog)
                .where(OperationLog.user_id == user_id)
                .order_by(OperationLog.timestamp.desc())
                .offset(skip)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def create(self, data: dict[str, Any]) -> OperationLog:
        """创建操作日志"""
        async with pg_manager.get_async_session_context() as session:
            log = OperationLog(**data)
            session.add(log)
        return log

    async def count_by_user(self, user_id: int) -> int:
        """统计用户操作日志数量"""
        from sqlalchemy import func

        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(func.count(OperationLog.id)).where(OperationLog.user_id == user_id)
            )
            return result.scalar() or 0
