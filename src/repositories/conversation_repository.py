"""对话数据访问层 - Repository"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import Conversation, ConversationStats, Message, ToolCall


class ConversationRepository:
    """对话数据访问层"""

    async def get_by_thread_id(self, thread_id: str) -> Conversation | None:
        """根据 thread_id 获取对话"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(Conversation).where(Conversation.thread_id == thread_id))
            return result.scalar_one_or_none()

    async def get_by_id(self, id: int) -> Conversation | None:
        """根据 ID 获取对话"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(Conversation).where(Conversation.id == id))
            return result.scalar_one_or_none()

    async def list_by_user(
        self, user_id: str, skip: int = 0, limit: int = 100, agent_id: str | None = None, status: str = "active"
    ) -> list[Conversation]:
        """获取用户的对话列表"""
        async with pg_manager.get_async_session_context() as session:
            query = select(Conversation).where(Conversation.user_id == str(user_id), Conversation.status == status)
            if agent_id:
                query = query.where(Conversation.agent_id == agent_id)
            query = query.order_by(Conversation.updated_at.desc()).offset(skip).limit(limit)
            result = await session.execute(query)
            return list(result.scalars().all())

    async def create(self, data: dict[str, Any]) -> Conversation:
        """创建对话"""
        async with pg_manager.get_async_session_context() as session:
            conversation = Conversation(**data)
            session.add(conversation)
            await session.flush()

            # 创建关联的 stats 记录
            stats = ConversationStats(conversation_id=conversation.id)
            session.add(stats)
        return conversation

    async def update(self, id: int, data: dict[str, Any]) -> Conversation | None:
        """更新对话"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(Conversation).where(Conversation.id == id))
            conversation = result.scalar_one_or_none()
            if conversation is None:
                return None
            for key, value in data.items():
                if key not in ("id", "thread_id", "user_id", "agent_id"):
                    setattr(conversation, key, value)
        return conversation

    async def update_status(self, id: int, status: str) -> bool:
        """更新对话状态"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(Conversation).where(Conversation.id == id))
            conversation = result.scalar_one_or_none()
            if conversation is None:
                return False
            conversation.status = status
        return True

    async def delete(self, id: int, soft_delete: bool = True) -> bool:
        """删除对话"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(Conversation).where(Conversation.id == id))
            conversation = result.scalar_one_or_none()
            if conversation is None:
                return False
            if soft_delete:
                conversation.status = "deleted"
            else:
                await session.delete(conversation)
        return True

    async def count_by_user(self, user_id: str) -> int:
        """统计用户对话数量"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(func.count(Conversation.id)).where(Conversation.user_id == str(user_id))
            )
            return result.scalar() or 0


class MessageRepository:
    """消息数据访问层"""

    async def get_by_id(self, id: int) -> Message | None:
        """根据 ID 获取消息"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(Message).where(Message.id == id))
            return result.scalar_one_or_none()

    async def list_by_conversation(self, conversation_id: int, limit: int | None = None, offset: int = 0) -> list[Message]:
        """获取对话的消息列表"""
        async with pg_manager.get_async_session_context() as session:
            query = (
                select(Message)
                .options(selectinload(Message.tool_calls), selectinload(Message.feedbacks))
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc())
            )
            query = query.offset(offset)
            if limit:
                query = query.limit(limit)
            result = await session.execute(query)
            return list(result.scalars().unique().all())

    async def create(self, data: dict[str, Any]) -> Message:
        """创建消息"""
        async with pg_manager.get_async_session_context() as session:
            message = Message(**data)
            session.add(message)
        return message

    async def count_by_conversation(self, conversation_id: int) -> int:
        """统计对话消息数量"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
            )
            return result.scalar() or 0


class ToolCallRepository:
    """工具调用数据访问层"""

    async def get_by_id(self, id: int) -> ToolCall | None:
        """根据 ID 获取工具调用"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(ToolCall).where(ToolCall.id == id))
            return result.scalar_one_or_none()

    async def get_by_langgraph_id(self, langgraph_tool_call_id: str) -> ToolCall | None:
        """根据 LangGraph tool_call_id 获取工具调用"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(ToolCall).where(ToolCall.langgraph_tool_call_id == langgraph_tool_call_id)
            )
            return result.scalar_one_or_none()

    async def list_by_message(self, message_id: int) -> list[ToolCall]:
        """获取消息的工具调用列表"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(ToolCall).where(ToolCall.message_id == message_id))
            return list(result.scalars().all())

    async def create(self, data: dict[str, Any]) -> ToolCall:
        """创建工具调用"""
        async with pg_manager.get_async_session_context() as session:
            tool_call = ToolCall(**data)
            session.add(tool_call)
        return tool_call

    async def update_output(
        self, langgraph_tool_call_id: str, tool_output: str, status: str = "success", error_message: str | None = None
    ) -> ToolCall | None:
        """更新工具调用输出"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(ToolCall).where(ToolCall.langgraph_tool_call_id == langgraph_tool_call_id)
            )
            tool_call = result.scalar_one_or_none()
            if tool_call is None:
                return None
            tool_call.tool_output = tool_output
            tool_call.status = status
            if error_message:
                tool_call.error_message = error_message
        return tool_call


class ConversationStatsRepository:
    """对话统计数据访问层"""

    async def get_by_conversation_id(self, conversation_id: int) -> ConversationStats | None:
        """根据对话 ID 获取统计信息"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(ConversationStats).where(ConversationStats.conversation_id == conversation_id)
            )
            return result.scalar_one_or_none()

    async def create(self, data: dict[str, Any]) -> ConversationStats:
        """创建统计信息"""
        async with pg_manager.get_async_session_context() as session:
            stats = ConversationStats(**data)
            session.add(stats)
        return stats

    async def update(
        self, conversation_id: int, data: dict[str, Any]
    ) -> ConversationStats | None:
        """更新统计信息"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(ConversationStats).where(ConversationStats.conversation_id == conversation_id)
            )
            stats = result.scalar_one_or_none()
            if stats is None:
                return None
            for key, value in data.items():
                if key != "conversation_id":
                    setattr(stats, key, value)
        return stats

    async def update_message_count(self, conversation_id: int, message_count: int) -> bool:
        """更新消息计数"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(ConversationStats).where(ConversationStats.conversation_id == conversation_id)
            )
            stats = result.scalar_one_or_none()
            if stats is None:
                return False
            stats.message_count = message_count
        return True
