"""
对话域持久化 Repository（Async）
"""

import uuid as uuid_lib

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from yuxi.storage.postgres.models_business import Conversation, ConversationStats, Message, ToolCall
from yuxi.utils import logger
from yuxi.utils.datetime_utils import utc_now_naive

MAX_CONVERSATION_TITLE_LENGTH = 255
MESSAGE_SEARCH_SNIPPET_RADIUS = 72
MESSAGE_SEARCH_SNIPPET_MAX_LENGTH = 180
MESSAGE_SEARCH_SNIPPETS_PER_THREAD = 2
MESSAGE_SEARCH_ROLES = ("user", "assistant")
MESSAGE_SEARCH_EXCLUDED_TYPES = ("tool_call", "tool_result")
INVOCATION_CONVERSATION_SOURCES = ("agent_call", "agent_evaluation")


class ConversationRepository:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    def _normalize_title(self, title: str | None) -> str | None:
        if title is None:
            return None
        normalized = str(title).strip()
        if not normalized:
            return ""
        if len(normalized) > MAX_CONVERSATION_TITLE_LENGTH:
            logger.warning(
                f"Conversation title too long ({len(normalized)}), truncate to {MAX_CONVERSATION_TITLE_LENGTH}"
            )
            return normalized[:MAX_CONVERSATION_TITLE_LENGTH]
        return normalized

    def _escape_like_query(self, query: str) -> str:
        return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def _message_search_conditions(self, query: str):
        pattern = f"%{self._escape_like_query(query)}%"
        return [
            Message.role.in_(MESSAGE_SEARCH_ROLES),
            or_(Message.message_type.is_(None), Message.message_type.notin_(MESSAGE_SEARCH_EXCLUDED_TYPES)),
            Message.content.ilike(pattern, escape="\\"),
        ]

    def _exclude_source_conditions(self, sources: tuple[str, ...]):
        if not sources:
            return []
        source = Conversation.extra_metadata["source"].as_string()
        return [
            or_(
                Conversation.extra_metadata.is_(None),
                source.is_(None),
                source.notin_(sources),
            )
        ]

    def _build_message_search_snippet(self, content: str, query: str) -> str:
        normalized = " ".join(str(content or "").split())
        if not normalized:
            return ""

        match_index = normalized.lower().find(query.lower())
        if match_index < 0:
            return normalized[:MESSAGE_SEARCH_SNIPPET_MAX_LENGTH]

        start = max(0, match_index - MESSAGE_SEARCH_SNIPPET_RADIUS)
        end = min(len(normalized), match_index + len(query) + MESSAGE_SEARCH_SNIPPET_RADIUS)
        snippet = normalized[start:end].strip()
        if start > 0:
            snippet = f"...{snippet}"
        if end < len(normalized):
            snippet = f"{snippet}..."
        return snippet[:MESSAGE_SEARCH_SNIPPET_MAX_LENGTH]

    async def add_conversation(
        self,
        *,
        uid: str,
        agent_id: str,
        title: str | None = None,
        thread_id: str | None = None,
        metadata: dict | None = None,
    ) -> Conversation:
        """创建对话和统计记录但只 flush，供外层事务继续绑定关系。"""
        if not thread_id:
            thread_id = str(uuid_lib.uuid4())

        metadata = (metadata or {}).copy()
        metadata.setdefault("attachments", [])

        normalized_title = self._normalize_title(title)

        conversation = Conversation(
            thread_id=thread_id,
            uid=str(uid),
            agent_id=agent_id,
            title=normalized_title or "New Conversation",
            status="active",
            extra_metadata=metadata,
        )

        self.db.add(conversation)
        await self.db.flush()

        stats = ConversationStats(conversation_id=conversation.id)
        self.db.add(stats)
        await self.db.flush()

        logger.info(f"Created conversation: {conversation.thread_id} for user {uid}")
        return conversation

    async def create_conversation(
        self,
        uid: str,
        agent_id: str,
        title: str | None = None,
        thread_id: str | None = None,
        metadata: dict | None = None,
    ) -> Conversation:
        """创建并提交一个完整对话，适用于不需要外层事务编排的入口。"""
        conversation = await self.add_conversation(
            uid=uid,
            agent_id=agent_id,
            title=title,
            thread_id=thread_id,
            metadata=metadata,
        )
        await self.db.commit()
        await self.db.refresh(conversation)
        return conversation

    async def get_conversation_by_thread_id(self, thread_id: str) -> Conversation | None:
        result = await self.db.execute(select(Conversation).where(Conversation.thread_id == thread_id))
        return result.scalar_one_or_none()

    async def lock_conversation_by_thread_id(self, thread_id: str) -> Conversation | None:
        """锁定线程根记录，串行化同一对话的调度决策。"""
        result = await self.db.execute(
            select(Conversation).where(Conversation.thread_id == thread_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_conversation_by_id(self, conversation_id: int) -> Conversation | None:
        result = await self.db.execute(select(Conversation).where(Conversation.id == conversation_id))
        return result.scalar_one_or_none()

    def _ensure_metadata(self, conversation: Conversation) -> dict:
        metadata = dict(conversation.extra_metadata or {})
        attachments = metadata.get("attachments", [])
        metadata["attachments"] = [dict(item) for item in attachments if isinstance(item, dict)]
        return metadata

    async def _save_metadata(self, conversation: Conversation, metadata: dict) -> None:
        conversation.extra_metadata = metadata
        flag_modified(conversation, "extra_metadata")
        conversation.updated_at = utc_now_naive()
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
        run_id: str | None = None,
        request_id: str | None = None,
        delivery_status: str = "complete",
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            message_type=message_type,
            extra_metadata=extra_metadata or {},
            image_content=image_content,
            run_id=run_id,
            request_id=request_id,
            delivery_status=delivery_status,
        )

        self.db.add(message)
        conversation = await self.get_conversation_by_id(conversation_id)
        if conversation:
            conversation.updated_at = utc_now_naive()

        await self.db.commit()
        await self.db.refresh(message)

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
        run_id: str | None = None,
        request_id: str | None = None,
        delivery_status: str = "complete",
    ) -> Message | None:
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
            run_id=run_id,
            request_id=request_id,
            delivery_status=delivery_status,
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
        if langgraph_tool_call_id:
            existing = await self.get_tool_call_by_langgraph_id(langgraph_tool_call_id)
            if existing:
                logger.debug(
                    "Tool call already exists for langgraph_tool_call_id=%s, skip insert",
                    langgraph_tool_call_id,
                )
                return existing

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
        query = (
            select(Message)
            .options(
                selectinload(Message.tool_calls),
                selectinload(Message.feedbacks),
            )
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )

        if limit:
            query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        return list(result.scalars().unique().all())

    async def get_messages_by_thread_id(
        self, thread_id: str, limit: int | None = None, offset: int = 0
    ) -> list[Message]:
        conversation = await self.get_conversation_by_thread_id(thread_id)
        if not conversation:
            logger.warning(f"Conversation not found for thread_id: {thread_id}")
            return []

        return await self.get_messages(conversation.id, limit, offset)

    async def list_conversations(
        self,
        uid: str | None = None,
        agent_id: str | None = None,
        status: str = "active",
        limit: int | None = None,
        offset: int = 0,
        exclude_sources: tuple[str, ...] = (),
    ) -> list[Conversation]:
        """List conversations with pinned conversations always included first.

        The limit applies only to non-pinned conversations to ensure pinned
        conversations are always visible in the list.
        """

        base_conditions = [Conversation.status == status]
        if uid:
            base_conditions.append(Conversation.uid == str(uid))
        if agent_id:
            base_conditions.append(Conversation.agent_id == agent_id)
        base_conditions.extend(self._exclude_source_conditions(exclude_sources))

        # First, get all pinned conversations (no limit)
        pinned_query = (
            select(Conversation)
            .where(*base_conditions)
            .where(Conversation.is_pinned)
            .order_by(Conversation.updated_at.desc())
        )
        result = await self.db.execute(pinned_query)
        pinned_conversations = list(result.scalars().all())

        # Then, get non-pinned conversations with limit/offset
        remaining_limit = None
        remaining_offset = offset

        if limit is not None:
            # Calculate how many slots are taken by pinned conversations
            pinned_count = len(pinned_conversations)
            if pinned_count >= limit:
                # All slots taken by pinned conversations
                return pinned_conversations[:limit]
            remaining_limit = limit - pinned_count

        if remaining_limit is not None and remaining_limit > 0:
            non_pinned_query = (
                select(Conversation)
                .where(*base_conditions)
                .where(~Conversation.is_pinned)
                .order_by(Conversation.updated_at.desc())
                .limit(remaining_limit)
                .offset(remaining_offset)
            )
            result = await self.db.execute(non_pinned_query)
            non_pinned_conversations = list(result.scalars().all())
        else:
            non_pinned_conversations = []

        return pinned_conversations + non_pinned_conversations

    async def list_active_conversations_for_user(self, uid: str) -> list[Conversation]:
        """返回用户全部 active 对话，按最近更新时间排序。"""
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.uid == str(uid), Conversation.status == "active")
            .order_by(Conversation.updated_at.desc())
        )
        return list(result.scalars().all())

    async def search_conversations_by_message_content(
        self,
        *,
        uid: str,
        query: str,
        agent_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
        exclude_sources: tuple[str, ...] = (),
    ) -> tuple[list[dict], bool]:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return [], False

        conversation_conditions = [
            Conversation.uid == str(uid),
            Conversation.status == "active",
        ]
        if agent_id:
            conversation_conditions.append(Conversation.agent_id == agent_id)
        conversation_conditions.extend(self._exclude_source_conditions(exclude_sources))

        message_conditions = self._message_search_conditions(normalized_query)
        summary = (
            select(
                Message.conversation_id.label("conversation_id"),
                func.count(Message.id).label("matched_count"),
                func.max(Message.created_at).label("latest_match_at"),
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(*conversation_conditions, *message_conditions)
            .group_by(Message.conversation_id)
            .subquery()
        )

        result = await self.db.execute(
            select(Conversation, summary.c.matched_count, summary.c.latest_match_at)
            .join(summary, Conversation.id == summary.c.conversation_id)
            .order_by(summary.c.latest_match_at.desc(), Conversation.updated_at.desc(), Conversation.id.desc())
            .limit(limit + 1)
            .offset(offset)
        )
        rows = list(result.all())
        has_more = len(rows) > limit
        rows = rows[:limit]

        items: list[dict] = []
        for conversation, matched_count, latest_match_at in rows:
            snippet_result = await self.db.execute(
                select(Message.id, Message.content, Message.created_at)
                .where(Message.conversation_id == conversation.id, *message_conditions)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(MESSAGE_SEARCH_SNIPPETS_PER_THREAD)
            )
            snippet_rows = list(snippet_result.all())
            snippets = [
                {
                    "message_id": message_id,
                    "content": self._build_message_search_snippet(content, normalized_query),
                    "created_at": created_at,
                }
                for message_id, content, created_at in snippet_rows
            ]

            items.append(
                {
                    "conversation": conversation,
                    "matched_count": int(matched_count or 0),
                    "latest_match_at": latest_match_at,
                    "message_id": snippets[0]["message_id"] if snippets else None,
                    "snippets": snippets,
                }
            )

        return items, has_more

    async def update_conversation(
        self,
        thread_id: str,
        title: str | None = None,
        status: str | None = None,
        metadata: dict | None = None,
        is_pinned: bool | None = None,
    ) -> Conversation | None:
        conversation = await self.get_conversation_by_thread_id(thread_id)
        if not conversation:
            return None

        normalized_title = self._normalize_title(title)
        if normalized_title is not None:
            conversation.title = normalized_title
        if status is not None:
            conversation.status = status
        if is_pinned is not None:
            conversation.is_pinned = is_pinned

        if metadata is not None:
            current_metadata = dict(conversation.extra_metadata or {})
            current_metadata.update(metadata)
            conversation.extra_metadata = current_metadata

        conversation.updated_at = utc_now_naive()
        await self.db.commit()
        await self.db.refresh(conversation)

        logger.info(f"Updated conversation {thread_id}")
        return conversation

    async def delete_conversation(self, thread_id: str, soft_delete: bool = True) -> bool:
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
        result = await self.db.execute(
            select(ConversationStats).where(ConversationStats.conversation_id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def update_stats(
        self,
        conversation_id: int,
        tokens_used: int | None = None,
        model_used: str | None = None,
        user_feedback: dict | None = None,
    ) -> ConversationStats | None:
        stats = await self.get_stats(conversation_id)
        if not stats:
            return None

        if tokens_used is not None:
            stats.total_tokens += tokens_used
        if model_used is not None:
            stats.model_used = model_used
        if user_feedback is not None:
            stats.user_feedback = user_feedback

        stats.updated_at = utc_now_naive()
        await self.db.commit()
        await self.db.refresh(stats)

        return stats

    async def get_tool_call_by_langgraph_id(self, langgraph_tool_call_id: str) -> ToolCall | None:
        result = await self.db.execute(
            select(ToolCall)
            .where(ToolCall.langgraph_tool_call_id == langgraph_tool_call_id)
            .order_by(ToolCall.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def update_tool_call_output(
        self,
        langgraph_tool_call_id: str,
        tool_output: str,
        status: str = "success",
        error_message: str | None = None,
    ) -> ToolCall | None:
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
        from sqlalchemy import func

        stats = await self.get_stats(conversation_id)
        if stats:
            result = await self.db.execute(select(func.count()).where(Message.conversation_id == conversation_id))
            message_count = result.scalar()
            stats.message_count = message_count
            await self.db.commit()

    async def get_attachments(self, conversation_id: int) -> list[dict]:
        conversation = await self.get_conversation_by_id(conversation_id)
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
        conversation = await self.get_conversation_by_id(conversation_id)
        if not conversation:
            return None

        metadata = self._ensure_metadata(conversation)
        attachments = metadata.get("attachments", [])
        attachments = [item for item in attachments if item.get("file_id") != attachment_info.get("file_id")]
        attachments.append(attachment_info)
        metadata["attachments"] = attachments
        await self._save_metadata(conversation, metadata)
        return attachment_info

    async def add_attachments(self, conversation_id: int, attachment_infos: list[dict]) -> list[dict] | None:
        conversation = await self.get_conversation_by_id(conversation_id)
        if not conversation:
            return None

        metadata = self._ensure_metadata(conversation)
        attachments = metadata.get("attachments", [])
        incoming_ids = {item.get("file_id") for item in attachment_infos}
        attachments = [item for item in attachments if item.get("file_id") not in incoming_ids]
        attachments.extend(attachment_infos)
        metadata["attachments"] = attachments
        await self._save_metadata(conversation, metadata)
        return attachment_infos

    async def update_attachment_status(
        self, conversation_id: int, file_id: str, status: str, update_fields: dict | None = None
    ) -> dict | None:
        conversation = await self.get_conversation_by_id(conversation_id)
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

    async def bind_attachments_to_request(
        self, conversation_id: int, request_id: str, file_ids: list[str]
    ) -> list[dict]:
        conversation = await self.get_conversation_by_id(conversation_id)
        if not conversation or not request_id or not file_ids:
            return []

        file_id_set = {str(file_id).strip() for file_id in file_ids if str(file_id).strip()}
        if not file_id_set:
            return []

        metadata = self._ensure_metadata(conversation)
        attachments = metadata.get("attachments", [])
        changed = False

        for item in attachments:
            if item.get("file_id") not in file_id_set:
                continue
            if item.get("request_id"):
                continue
            item["request_id"] = request_id
            changed = True

        if changed:
            metadata["attachments"] = attachments
            await self._save_metadata(conversation, metadata)
        return [dict(item) for item in attachments if item.get("request_id") == request_id]

    async def get_attachments_by_request_id(self, conversation_id: int, request_id: str) -> list[dict]:
        attachments = await self.get_attachments(conversation_id)
        return [item for item in attachments if item.get("request_id") == request_id]

    async def remove_attachment(self, conversation_id: int, file_id: str) -> bool:
        conversation = await self.get_conversation_by_id(conversation_id)
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
