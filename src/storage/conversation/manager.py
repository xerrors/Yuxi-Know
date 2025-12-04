"""
Conversation Storage Manager (Async)

Manages conversation data storage including messages, tool calls, and statistics.
All database operations are now asynchronous for improved performance.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.storage.db.models import Conversation, ConversationStats, Message, ToolCall
from src.utils import logger
from src.utils.datetime_utils import utc_now


class ConversationManager:
    """Async Manager for conversation storage operations"""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def create_conversation(
        self,
        user_id: str,
        agent_id: str,
        title: str | None = None,
        thread_id: str | None = None,
        metadata: dict | None = None,
    ) -> Conversation:
        """
        Create a new conversation

        Args:
            user_id: User ID
            agent_id: Agent ID
            title: Conversation title
            thread_id: Optional thread ID (will generate UUID if not provided)
            metadata: Optional additional metadata

        Returns:
            Created Conversation object
        """
        if not thread_id:
            thread_id = str(uuid.uuid4())

        metadata = (metadata or {}).copy()
        metadata.setdefault("attachments", [])

        conversation = Conversation(
            thread_id=thread_id,
            user_id=str(user_id),
            agent_id=agent_id,
            title=title or "New Conversation",
            status="active",
            extra_metadata=metadata,
        )

        self.db.add(conversation)
        # Flush to assign primary key without committing
        await self.db.flush()

        # Create associated stats record and commit once
        stats = ConversationStats(conversation_id=conversation.id)
        self.db.add(stats)
        await self.db.commit()
        await self.db.refresh(conversation)

        logger.info(f"Created conversation: {conversation.thread_id} for user {user_id}")
        return conversation

    async def get_conversation_by_thread_id(self, thread_id: str) -> Conversation | None:
        """
        Get conversation by thread ID

        Args:
            thread_id: Thread ID

        Returns:
            Conversation object or None if not found
        """
        result = await self.db.execute(select(Conversation).filter(Conversation.thread_id == thread_id))
        return result.scalar_one_or_none()

    async def _get_conversation_by_id(self, conversation_id: int) -> Conversation | None:
        result = await self.db.execute(select(Conversation).filter(Conversation.id == conversation_id))
        return result.scalar_one_or_none()

    def _ensure_metadata(self, conversation: Conversation) -> dict:
        """
        Return a shallow copy of conversation metadata with a standalone attachments list.

        We copy here because SQLAlchemy's JSON type does not automatically detect in-place
        mutations. By assigning a fresh dict/list back we ensure the ORM marks the row dirty.
        """
        metadata = dict(conversation.extra_metadata or {})
        metadata["attachments"] = list(metadata.get("attachments", []))
        return metadata

    async def _save_metadata(self, conversation: Conversation, metadata: dict) -> None:
        conversation.extra_metadata = metadata
        conversation.updated_at = utc_now()
        await self.db.commit()
        await self.db.refresh(conversation)

    async def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        message_type: str = "text",
        extra_metadata: dict | None = None,
        image_content: str | None = None,
    ) -> Message:
        """
        Add a message to a conversation

        Args:
            conversation_id: Conversation ID
            role: Message role (user/assistant/system/tool)
            content: Message content
            message_type: Message type (text/tool_call/tool_result/multimodal_image)
            extra_metadata: Additional metadata (complete message dump)
            image_content: Base64 encoded image content for multimodal messages

        Returns:
            Created Message object
        """
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            message_type=message_type,
            extra_metadata=extra_metadata or {},
            image_content=image_content,
        )

        self.db.add(message)
        # Mark the parent conversation as active for sorting/analytics
        conversation = await self._get_conversation_by_id(conversation_id)
        if conversation:
            conversation.updated_at = utc_now()

        await self.db.commit()
        await self.db.refresh(message)

        # Update conversation stats
        await self._update_message_count(conversation_id)

        logger.debug(f"Added {role} message to conversation {conversation_id}")
        return message

    async def add_message_by_thread_id(
        self,
        thread_id: str,
        role: str,
        content: str,
        message_type: str = "text",
        extra_metadata: dict | None = None,
        image_content: str | None = None,
    ) -> Message | None:
        """
        Add a message to a conversation by thread ID

        Args:
            thread_id: Thread ID
            role: Message role (user/assistant/system/tool)
            content: Message content
            message_type: Message type (text/tool_call/tool_result/multimodal_image)
            extra_metadata: Additional metadata (complete message dump)
            image_content: Base64 encoded image content for multimodal messages

        Returns:
            Created Message object or None if conversation not found
        """
        conversation = await self.get_conversation_by_thread_id(thread_id)
        if not conversation:
            logger.warning(f"Conversation not found for thread_id: {thread_id}")
            return None

        return await self.add_message(
            conversation_id=conversation.id,
            role=role,
            content=content,
            message_type=message_type,
            extra_metadata=extra_metadata,
            image_content=image_content,
        )

    async def add_tool_call(
        self,
        message_id: int,
        tool_name: str,
        tool_input: dict | None = None,
        tool_output: str | None = None,
        status: str = "pending",
        error_message: str | None = None,
        langgraph_tool_call_id: str | None = None,
    ) -> ToolCall:
        """
        Add a tool call record

        Args:
            message_id: Message ID
            tool_name: Tool name
            tool_input: Tool input parameters
            tool_output: Tool execution result
            status: Status (pending/success/error)
            error_message: Error message if failed
            langgraph_tool_call_id: LangGraph tool_call_id for precise matching

        Returns:
            Created ToolCall object
        """
        tool_call = ToolCall(
            message_id=message_id,
            tool_name=tool_name,
            tool_input=tool_input or {},
            tool_output=tool_output,
            status=status,
            error_message=error_message,
            langgraph_tool_call_id=langgraph_tool_call_id,
        )

        self.db.add(tool_call)
        await self.db.commit()
        await self.db.refresh(tool_call)

        logger.debug(f"Added tool call {tool_name} to message {message_id}")
        return tool_call

    async def get_messages(self, conversation_id: int, limit: int | None = None, offset: int = 0) -> list[Message]:
        """
        Get messages for a conversation

        Args:
            conversation_id: Conversation ID
            limit: Maximum number of messages to return
            offset: Number of messages to skip

        Returns:
            List of Message objects
        """
        query = (
            select(Message)
            .options(selectinload(Message.tool_calls))
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )

        if limit:
            query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        return result.scalars().unique().all()

    async def get_messages_by_thread_id(
        self, thread_id: str, limit: int | None = None, offset: int = 0
    ) -> list[Message]:
        """
        Get messages for a conversation by thread ID

        Args:
            thread_id: Thread ID
            limit: Maximum number of messages to return
            offset: Number of messages to skip

        Returns:
            List of Message objects
        """
        conversation = await self.get_conversation_by_thread_id(thread_id)
        if not conversation:
            logger.warning(f"Conversation not found for thread_id: {thread_id}")
            return []

        return await self.get_messages(conversation.id, limit, offset)

    async def list_conversations(
        self, user_id: str | None = None, agent_id: str | None = None, status: str = "active"
    ) -> list[Conversation]:
        """
        List conversations for a user or all users

        Args:
            user_id: User ID (optional, if None or empty string, returns all users' conversations)
            agent_id: Optional agent ID filter
            status: Conversation status filter

        Returns:
            List of Conversation objects
        """
        query = select(Conversation).filter(Conversation.status == status)

        # Only filter by user_id if it's provided and not empty
        if user_id:
            query = query.filter(Conversation.user_id == str(user_id))

        if agent_id:
            query = query.filter(Conversation.agent_id == agent_id)

        query = query.order_by(Conversation.updated_at.desc())
        result = await self.db.execute(query)
        return result.scalars().all()

    async def update_conversation(
        self,
        thread_id: str,
        title: str | None = None,
        status: str | None = None,
        metadata: dict | None = None,
    ) -> Conversation | None:
        """
        Update conversation information

        Args:
            thread_id: Thread ID
            title: New title
            status: New status
            metadata: Additional metadata to merge

        Returns:
            Updated Conversation object or None if not found
        """
        conversation = await self.get_conversation_by_thread_id(thread_id)
        if not conversation:
            return None

        if title is not None:
            conversation.title = title
        if status is not None:
            conversation.status = status

        # Handle metadata updates
        if metadata is not None:
            current_metadata = conversation.extra_metadata or {}
            current_metadata.update(metadata)
            conversation.extra_metadata = current_metadata

        conversation.updated_at = utc_now()
        await self.db.commit()
        await self.db.refresh(conversation)

        logger.info(f"Updated conversation {thread_id}")
        return conversation

    async def delete_conversation(self, thread_id: str, soft_delete: bool = True) -> bool:
        """
        Delete a conversation

        Args:
            thread_id: Thread ID
            soft_delete: If True, mark as deleted; if False, permanently delete

        Returns:
            True if successful, False otherwise
        """
        conversation = await self.get_conversation_by_thread_id(thread_id)
        if not conversation:
            return False

        if soft_delete:
            conversation.status = "deleted"
            await self.db.commit()
            logger.info(f"Soft deleted conversation {thread_id}")
        else:
            self.db.delete(conversation)
            await self.db.commit()
            logger.info(f"Permanently deleted conversation {thread_id}")

        return True

    async def get_stats(self, conversation_id: int) -> ConversationStats | None:
        """
        Get conversation statistics

        Args:
            conversation_id: Conversation ID

        Returns:
            ConversationStats object or None if not found
        """
        result = await self.db.execute(
            select(ConversationStats).filter(ConversationStats.conversation_id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def update_stats(
        self,
        conversation_id: int,
        tokens_used: int | None = None,
        model_used: str | None = None,
        user_feedback: dict | None = None,
    ) -> ConversationStats | None:
        """
        Update conversation statistics

        Args:
            conversation_id: Conversation ID
            tokens_used: Number of tokens to add
            model_used: Model name
            user_feedback: User feedback data

        Returns:
            Updated ConversationStats object or None if not found
        """
        stats = await self.get_stats(conversation_id)
        if not stats:
            return None

        if tokens_used is not None:
            stats.total_tokens += tokens_used
        if model_used is not None:
            stats.model_used = model_used
        if user_feedback is not None:
            stats.user_feedback = user_feedback

        stats.updated_at = utc_now()
        await self.db.commit()
        await self.db.refresh(stats)

        return stats

    async def get_tool_call_by_langgraph_id(self, langgraph_tool_call_id: str) -> ToolCall | None:
        """
        Get tool call by LangGraph tool_call_id

        Args:
            langgraph_tool_call_id: LangGraph tool_call_id

        Returns:
            ToolCall object or None if not found
        """
        result = await self.db.execute(
            select(ToolCall).filter(ToolCall.langgraph_tool_call_id == langgraph_tool_call_id)
        )
        return result.scalar_one_or_none()

    async def update_tool_call_output(
        self,
        langgraph_tool_call_id: str,
        tool_output: str,
        status: str = "success",
        error_message: str | None = None,
    ) -> ToolCall | None:
        """
        Update tool call output by LangGraph tool_call_id

        Args:
            langgraph_tool_call_id: LangGraph tool_call_id
            tool_output: Tool execution result
            status: Status (success/error)
            error_message: Error message if failed

        Returns:
            Updated ToolCall object or None if not found
        """
        tool_call = await self.get_tool_call_by_langgraph_id(langgraph_tool_call_id)
        if not tool_call:
            logger.warning(f"Tool call not found for langgraph_tool_call_id: {langgraph_tool_call_id}")
            return None

        tool_call.tool_output = tool_output
        tool_call.status = status
        if error_message:
            tool_call.error_message = error_message

        await self.db.commit()
        await self.db.refresh(tool_call)

        logger.debug(f"Updated tool call {langgraph_tool_call_id} with output")
        return tool_call

    async def _update_message_count(self, conversation_id: int) -> None:
        """
        Update message count in conversation stats

        Args:
            conversation_id: Conversation ID
        """
        from sqlalchemy import func

        stats = await self.get_stats(conversation_id)
        if stats:
            result = await self.db.execute(select(func.count()).filter(Message.conversation_id == conversation_id))
            message_count = result.scalar()
            stats.message_count = message_count
            await self.db.commit()

    # -------------------------------------------------------------------------
    # Attachment helpers
    # -------------------------------------------------------------------------

    async def get_attachments(self, conversation_id: int) -> list[dict]:
        conversation = await self._get_conversation_by_id(conversation_id)
        if not conversation:
            return []
        metadata = self._ensure_metadata(conversation)
        return list(metadata.get("attachments", []))

    async def get_attachments_by_thread_id(self, thread_id: str) -> list[dict]:
        conversation = await self.get_conversation_by_thread_id(thread_id)
        if not conversation:
            return []
        return await self.get_attachments(conversation.id)

    async def add_attachment(self, conversation_id: int, attachment_info: dict) -> dict | None:
        conversation = await self._get_conversation_by_id(conversation_id)
        if not conversation:
            return None

        metadata = self._ensure_metadata(conversation)
        attachments = metadata.get("attachments", [])
        attachments = [item for item in attachments if item.get("file_id") != attachment_info.get("file_id")]
        attachments.append(attachment_info)
        metadata["attachments"] = attachments
        await self._save_metadata(conversation, metadata)
        return attachment_info

    async def update_attachment_status(
        self, conversation_id: int, file_id: str, status: str, update_fields: dict | None = None
    ) -> dict | None:
        conversation = await self._get_conversation_by_id(conversation_id)
        if not conversation:
            return None

        metadata = self._ensure_metadata(conversation)
        attachments = metadata.get("attachments", [])
        target = None
        for item in attachments:
            if item.get("file_id") == file_id:
                item["status"] = status
                if update_fields:
                    item.update(update_fields)
                target = item
                break

        if target is not None:
            metadata["attachments"] = attachments
            await self._save_metadata(conversation, metadata)
        return target

    async def remove_attachment(self, conversation_id: int, file_id: str) -> bool:
        conversation = await self._get_conversation_by_id(conversation_id)
        if not conversation:
            return False

        metadata = self._ensure_metadata(conversation)
        attachments = metadata.get("attachments", [])
        new_attachments = [item for item in attachments if item.get("file_id") != file_id]

        if len(new_attachments) == len(attachments):
            return False

        metadata["attachments"] = new_attachments
        await self._save_metadata(conversation, metadata)
        return True
