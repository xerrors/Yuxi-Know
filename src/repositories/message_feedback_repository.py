"""消息反馈数据访问层 - Repository"""

from typing import Any

from sqlalchemy import select

from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import MessageFeedback


class MessageFeedbackRepository:
    """消息反馈数据访问层"""

    async def get_by_id(self, id: int) -> MessageFeedback | None:
        """根据 ID 获取消息反馈"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(MessageFeedback).where(MessageFeedback.id == id))
            return result.scalar_one_or_none()

    async def list_by_message(self, message_id: int) -> list[MessageFeedback]:
        """获取消息的反馈列表"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(MessageFeedback).where(MessageFeedback.message_id == message_id))
            return list(result.scalars().all())

    async def create(self, data: dict[str, Any]) -> MessageFeedback:
        """创建消息反馈"""
        async with pg_manager.get_async_session_context() as session:
            feedback = MessageFeedback(**data)
            session.add(feedback)
        return feedback

    async def exists_by_message_and_user(self, message_id: int, user_id: str) -> bool:
        """检查用户是否已对消息反馈"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(MessageFeedback.id).where(
                    MessageFeedback.message_id == message_id, MessageFeedback.user_id == user_id
                )
            )
            return result.scalar_one_or_none() is not None
