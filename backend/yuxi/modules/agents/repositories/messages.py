"""正式消息的持久写入、可见性和读取。"""

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from yuxi.infrastructure.observability.logging import logger
from yuxi.modules.agents.models.messages import AUDIT_MESSAGE_TYPES, MODEL_AUDIT_MESSAGE_TYPE, TOOL_AUDIT_MESSAGE_TYPE, Message
from yuxi.modules.agents.models.runs import AGENT_RUN_TERMINAL_STATUSES, AgentRun
from yuxi.modules.agents.models.sessions import Session
from yuxi.shared.datetime import utc_now


def state_proven_model_tool_call_condition():
    """只允许终态 State 已证明的模型调用声明进入工具历史。"""
    return and_(
        Message.message_type == MODEL_AUDIT_MESSAGE_TYPE,
        func.json_array_length(Message.extra_metadata["tool_calls"]) > 0,
        Message.extra_metadata["state_reconciled"].as_boolean().is_(True),
        Message.run_id.in_(select(AgentRun.id).where(AgentRun.status.in_(AGENT_RUN_TERMINAL_STATUSES))),
    )


MESSAGE_SEARCH_ROLES = ("user", "assistant")
MESSAGE_SEARCH_EXCLUDED_TYPES = (MODEL_AUDIT_MESSAGE_TYPE, TOOL_AUDIT_MESSAGE_TYPE, "tool_result")


def message_search_conditions(query: str):
    """按用户/助手角色和可见消息类型构造转义搜索条件。"""
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    return [
        Message.role.in_(MESSAGE_SEARCH_ROLES),
        or_(Message.message_type.is_(None), Message.message_type.notin_(MESSAGE_SEARCH_EXCLUDED_TYPES)),
        Message.content.ilike(pattern, escape="\\"),
    ]


class MessageRepository:
    """在调用方事务内维护正式消息。"""

    def __init__(self, db_session: AsyncSession):
        """绑定调用者的持久事务。"""
        self.db = db_session

    async def add_message(
        self,
        session_record_id: int,
        role: str,
        content: str,
        message_type: str = "text",
        extra_metadata: dict | None = None,
        image_content: str | None = None,
        run_id: str | None = None,
        turn_id: str | None = None,
        delivery_status: str = "complete",
    ) -> Message:
        """在调用方事务保存正式消息并更新会话活动时间。"""
        message = Message(
            session_record_id=session_record_id,
            role=role,
            content=content,
            message_type=message_type,
            extra_metadata=extra_metadata or {},
            image_content=image_content,
            run_id=run_id,
            turn_id=turn_id,
            delivery_status=delivery_status,
        )

        self.db.add(message)
        agent_session = await self.db.get(Session, session_record_id)
        if agent_session:
            agent_session.updated_at = utc_now()

        await self.db.flush()
        await self.db.refresh(message)

        logger.debug(f"Added {role} message to agent_session {session_record_id}")
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
        turn_id: str | None = None,
        delivery_status: str = "complete",
    ) -> Message | None:
        """定位线程的 Session 后保存正式消息。"""
        agent_session = await self.db.scalar(select(Session).where(Session.thread_id == thread_id))
        if not agent_session:
            logger.warning(f"Session not found for thread_id: {thread_id}")
            return None

        return await self.add_message(
            session_record_id=agent_session.id,
            role=role,
            content=content,
            message_type=message_type,
            extra_metadata=extra_metadata,
            image_content=image_content,
            run_id=run_id,
            turn_id=turn_id,
            delivery_status=delivery_status,
        )

    async def publish_assistant_output(self, message: Message) -> None:
        """把最终 AIMessage 发布到普通历史并刷新 Session 读模型。"""
        if message.role != "assistant":
            raise ValueError("只有 assistant Message 可以发布为最终输出")
        if message.message_type == MODEL_AUDIT_MESSAGE_TYPE:
            message.message_type = "text"
        agent_session = await self.db.get(Session, message.session_record_id)
        if agent_session is None:
            raise ValueError("最终输出缺少 Session")
        agent_session.updated_at = utc_now()
        await self.db.flush()

    async def get_messages(self, session_record_id: int, limit: int | None = None, offset: int = 0) -> list[Message]:
        """按可见性读取正式消息与已证明的模型声明。"""
        query = (
            select(Message)
            .where(
                Message.session_record_id == session_record_id,
                or_(
                    Message.message_type.is_(None),
                    Message.message_type.notin_(AUDIT_MESSAGE_TYPES),
                    state_proven_model_tool_call_condition(),
                ),
            )
            .order_by(Message.created_at.asc())
        )

        if limit:
            query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        return list(result.scalars().unique().all())

    async def list_tool_executions(self, source_message_ids: list[int], *, limit: int | None = None) -> list[Message]:
        """按已授权的模型消息读取同会话、同 Turn 的唯一工具执行事实。"""
        source = aliased(Message)
        statement = (
            select(Message)
            .join(source, Message.extra_metadata["source_model_message_id"].as_integer() == source.id)
            .where(
                source.id.in_(source_message_ids),
                Message.session_record_id == source.session_record_id,
                Message.turn_id.is_not_distinct_from(source.turn_id),
                Message.role == "tool",
                Message.message_type == TOOL_AUDIT_MESSAGE_TYPE,
            )
            .order_by(Message.created_at, Message.id)
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list((await self.db.scalars(statement)).all())

    async def list_message_audits(self, session_record_id: int, *, limit: int) -> tuple[list[Message], bool]:
        """按持久顺序读取有界调试消息，保留未关联 Run 的输入。"""
        result = await self.db.execute(
            select(Message)
            .outerjoin(AgentRun, AgentRun.id == Message.run_id)
            .where(Message.session_record_id == session_record_id)
            .order_by(
                func.coalesce(AgentRun.created_at, Message.created_at).desc(),
                AgentRun.id.desc().nulls_last(),
                case((Message.run_id.is_not(None) & (Message.role == "user"), 0), else_=1).desc(),
                Message.sequence.desc().nulls_first(),
                Message.id.desc(),
            )
            .limit(limit + 1)
        )
        messages = list(result.scalars().unique().all())
        truncated = len(messages) > limit
        return list(reversed(messages[:limit])), truncated
