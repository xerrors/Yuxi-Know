"""
对话域持久化 Repository（Async）
"""

import json
import uuid as uuid_lib

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from yuxi.infrastructure.observability.logging import logger
from yuxi.modules.agents.models.messages import (
    AUDIT_MESSAGE_TYPES,
    MODEL_AUDIT_MESSAGE_TYPE,
    TOOL_AUDIT_MESSAGE_TYPE,
    Message,
    ToolCall,
)
from yuxi.modules.agents.models.runs import AGENT_RUN_TERMINAL_STATUSES, AgentRun
from yuxi.modules.agents.models.sessions import UNVIEWED_RUN_MARKER, Session
from yuxi.shared.datetime import utc_now
from yuxi.shared.strings import truncate_utf8

MAX_SESSION_TITLE_LENGTH = 255
MESSAGE_SEARCH_SNIPPET_RADIUS = 72
MESSAGE_SEARCH_SNIPPET_MAX_LENGTH = 180
MESSAGE_SEARCH_SNIPPETS_PER_THREAD = 2
MESSAGE_SEARCH_ROLES = ("user", "assistant")
MESSAGE_SEARCH_EXCLUDED_TYPES = (
    MODEL_AUDIT_MESSAGE_TYPE,
    TOOL_AUDIT_MESSAGE_TYPE,
    "tool_result",
)
ALL_APP_SCOPES = object()

# ==== 历史对话检索参数 ====
MEMORY_HISTORY_SEARCH_MAX_LIMIT = 10  # 单次历史搜索最多返回的消息条数。
MEMORY_HISTORY_SEARCH_QUERY_MAX_CHARS = 256  # 历史搜索关键词允许的最大字符数。
MEMORY_HISTORY_SEARCH_SNIPPET_MAX_BYTES = 512  # 单条搜索结果摘要的最大 UTF-8 字节数。
MEMORY_HISTORY_SEARCH_RESPONSE_MAX_BYTES = 16 * 1024  # 历史搜索完整 JSON 响应的最大字节数。
MEMORY_HISTORY_READ_MAX_LIMIT = 20  # 单次历史读取最多返回的消息条数。
MEMORY_HISTORY_MESSAGE_MAX_BYTES = 8 * 1024  # 单条历史消息正文的最大 UTF-8 字节数。
MEMORY_HISTORY_MESSAGES_MAX_BYTES = 32 * 1024  # 一次历史读取中全部消息正文的合计字节上限。
MEMORY_HISTORY_TOOL_CALL_MAX_COUNT = 10  # 显式读取工具调用时最多返回的记录数。
MEMORY_HISTORY_TOOL_CALL_MAX_BYTES = 4 * 1024  # 单条工具调用序列化后的最大字节数。
MEMORY_HISTORY_TOOL_CALLS_MAX_BYTES = 16 * 1024  # 一次历史读取中全部工具调用的合计字节上限。
MEMORY_HISTORY_READ_RESPONSE_MAX_BYTES = 64 * 1024  # 历史读取完整 JSON 响应的最大字节数。


def _json_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8"))


def _state_proven_model_tool_call_condition():
    """只允许终态 State 已证明的 Model 兼容行进入普通读模型。"""
    return and_(
        Message.message_type == MODEL_AUDIT_MESSAGE_TYPE,
        Message.tool_calls.any(),
        Message.extra_metadata["state_reconciled"].as_boolean().is_(True),
        Message.run_id.in_(select(AgentRun.id).where(AgentRun.status.in_(AGENT_RUN_TERMINAL_STATUSES))),
    )


class SessionRepository:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    def _normalize_title(self, title: str | None) -> str | None:
        if title is None:
            return None
        normalized = str(title).strip()
        if not normalized:
            return ""
        if len(normalized) > MAX_SESSION_TITLE_LENGTH:
            logger.warning(f"Session title too long ({len(normalized)}), truncate to {MAX_SESSION_TITLE_LENGTH}")
            return normalized[:MAX_SESSION_TITLE_LENGTH]
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

    async def add_session(
        self,
        *,
        uid: str,
        agent_id: str,
        title: str | None = None,
        thread_id: str | None = None,
        metadata: dict | None = None,
        config_snapshot: dict | None = None,
        project_id: str,
        creation_request_id: str | None = None,
        app_id: str | None = None,
    ) -> Session:
        """创建对话和统计记录但只 flush，供外层事务继续绑定关系。"""
        if not thread_id:
            thread_id = str(uuid_lib.uuid4())

        metadata = (metadata or {}).copy()
        metadata.pop("attachments", None)

        normalized_title = self._normalize_title(title)
        metadata.pop("auto_title", None)
        if not normalized_title:
            metadata["auto_title"] = "pending"

        agent_session = Session(
            thread_id=thread_id,
            tree_root_thread_id=thread_id,
            creation_request_id=creation_request_id,
            uid=str(uid),
            app_id=app_id,
            agent_id=agent_id,
            title=normalized_title or "New Session",
            status="active",
            extra_metadata=metadata,
            config_snapshot=config_snapshot,
            last_viewed_run_id=UNVIEWED_RUN_MARKER,
            project_id=project_id,
        )

        self.db.add(agent_session)
        await self.db.flush()

        logger.info(f"Created agent_session: {agent_session.thread_id} for user {uid}")
        return agent_session

    async def public_facts(self, sessions, *, uid, app_id) -> list[tuple]:
        """批量读取资源事实，列表、搜索和详情共享同一查询集合。"""
        from yuxi.modules.agents.models.runs import AGENT_RUN_TERMINAL_STATUSES
        from yuxi.modules.agents.repositories.runs import AgentRunRepository
        from yuxi.modules.agents.repositories.turn import AgentTurnRepository

        ids = [session.thread_id for session in sessions]
        if not ids:
            return []
        views = await AgentTurnRepository(self.db).list_current_views(thread_ids=ids, uid=uid, app_id=app_id)
        latest = await AgentRunRepository(self.db).get_latest_top_level_runs_for_threads(uid, ids)
        timestamps = await self.get_last_activity_for_threads(uid=uid, app_id=app_id, thread_ids=ids)
        result = []
        for session in sessions:
            turn, run, count = views[session.thread_id]
            run_id, run_status = latest.get(session.thread_id, (None, None))
            unread = bool(run_id and run_status in AGENT_RUN_TERMINAL_STATUSES and run_id != session.last_viewed_run_id)
            result.append((session, turn, run, count, timestamps.get(session.thread_id, session.created_at), unread))
        return result

    async def get_session_by_thread_id(self, thread_id: str) -> Session | None:
        result = await self.db.execute(select(Session).where(Session.thread_id == thread_id))
        return result.scalar_one_or_none()

    async def lock_session_by_thread_id(self, thread_id: str) -> Session | None:
        """锁定线程根记录，串行化同一对话的调度决策。"""
        # 身份键不变；允许树通知的外键键共享锁，避免 Session → 树锁反向等待。
        result = await self.db.execute(
            select(Session).where(Session.thread_id == thread_id).with_for_update(key_share=True).execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_session_by_id(self, session_record_id: int) -> Session | None:
        result = await self.db.execute(select(Session).where(Session.id == session_record_id))
        return result.scalar_one_or_none()

    async def mark_thread_viewed(self, thread_id: str, run_id: str) -> Session | None:
        """记录用户最近查看过的顶层 run id；重复标记同一 run 时保持幂等。"""
        agent_session = await self.get_session_by_thread_id(thread_id)
        if not agent_session:
            return None
        if agent_session.last_viewed_run_id != run_id:
            agent_session.last_viewed_run_id = run_id
            await self.db.commit()
            await self.db.refresh(agent_session)
        return agent_session

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
        commit: bool = True,
    ) -> Message:
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
        agent_session = await self.get_session_by_id(session_record_id)
        if agent_session:
            agent_session.updated_at = utc_now()

        await self.db.flush()
        await self.db.refresh(message)

        if commit:
            await self.db.commit()

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
        commit: bool = True,
    ) -> Message | None:
        agent_session = await self.get_session_by_thread_id(thread_id)
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
            commit=commit,
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
        commit: bool = True,
    ) -> ToolCall:
        if langgraph_tool_call_id:
            result = await self.db.execute(
                select(ToolCall)
                .where(ToolCall.message_id == message_id, ToolCall.langgraph_tool_call_id == langgraph_tool_call_id)
                .order_by(ToolCall.created_at.desc())
                .limit(1)
            )
            existing = result.scalar_one_or_none()
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
        await self.db.flush()
        await self.db.refresh(tool_call)
        if commit:
            await self.db.commit()

        logger.debug(f"Added tool call {tool_name} to message {message_id}")
        return tool_call

    async def publish_assistant_output(self, message: Message) -> None:
        """把最终 AIMessage 发布到普通历史并刷新 Session 读模型。"""
        if message.role != "assistant":
            raise ValueError("只有 assistant Message 可以发布为最终输出")
        if message.message_type == MODEL_AUDIT_MESSAGE_TYPE:
            message.message_type = "text"
        agent_session = await self.get_session_by_id(message.session_record_id)
        if agent_session is None:
            raise ValueError("最终输出缺少 Session")
        agent_session.updated_at = utc_now()
        await self.db.flush()

    async def get_messages(self, session_record_id: int, limit: int | None = None, offset: int = 0) -> list[Message]:
        query = (
            select(Message)
            .options(
                selectinload(Message.tool_calls),
            )
            .where(
                Message.session_record_id == session_record_id,
                or_(
                    Message.message_type.is_(None),
                    Message.message_type.notin_(AUDIT_MESSAGE_TYPES),
                    _state_proven_model_tool_call_condition(),
                ),
            )
            .order_by(Message.created_at.asc())
        )

        if limit:
            query = query.limit(limit).offset(offset)

        result = await self.db.execute(query)
        return list(result.scalars().unique().all())

    async def get_message_source_ids_by_thread_id(self, thread_id: str) -> set[str]:
        """读取全部持久 Message 来源 ID，包括普通历史隐藏的审计行。"""
        agent_session = await self.get_session_by_thread_id(thread_id)
        if agent_session is None:
            return set()
        result = await self.db.execute(select(Message.extra_metadata).where(Message.session_record_id == agent_session.id))
        return {
            str(metadata["id"]) for metadata in result.scalars().all() if isinstance(metadata, dict) and isinstance(metadata.get("id"), str)
        }

    async def list_message_audits(self, session_record_id: int, *, limit: int) -> tuple[list[Message], bool]:
        """按持久顺序读取有界调试消息，保留未关联 Run 的输入。"""
        result = await self.db.execute(
            select(Message)
            .outerjoin(AgentRun, AgentRun.id == Message.run_id)
            .options(selectinload(Message.tool_calls))
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

    async def list_agent_runs_for_trace(self, session_record_id: int, *, limit: int) -> tuple[list[AgentRun], bool]:
        """按创建顺序返回有界 AgentRun 调试事实。"""
        result = await self.db.execute(
            select(AgentRun)
            .where(AgentRun.session_record_id == session_record_id)
            .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
            .limit(limit + 1)
        )
        runs = list(result.scalars().all())
        truncated = len(runs) > limit
        return list(reversed(runs[:limit])), truncated

    async def list_public_sessions(
        self,
        *,
        uid: str,
        app_id: str | None,
        agent_id: str | None,
        after: str | None,
        limit: int,
        order: str,
        archived: bool = False,
        is_pinned: bool | None = None,
    ) -> tuple[list[Session], bool]:
        """按完整作用域和稳定创建顺序读取有界会话页。"""
        conditions = [
            Session.uid == uid,
            Session.app_id == app_id,
            Session.status == ("archived" if archived else "active"),
        ]
        if agent_id:
            conditions.append(Session.agent_id == agent_id)
        if is_pinned is not None:
            conditions.append(Session.is_pinned == is_pinned)
        query = select(Session).where(*conditions)
        if after:
            anchor = (
                await self.db.execute(select(Session).where(Session.uid == uid, Session.app_id == app_id, Session.thread_id == after))
            ).scalar_one_or_none()
            if anchor is None:
                raise ValueError("after 不属于当前会话作用域")
            from sqlalchemy import tuple_

            position = tuple_(Session.created_at, Session.thread_id)
            boundary = (anchor.created_at, anchor.thread_id)
            query = query.where(position > boundary if order == "asc" else position < boundary)
        sort = (
            [Session.created_at.asc(), Session.thread_id.asc()] if order == "asc" else [Session.created_at.desc(), Session.thread_id.desc()]
        )
        rows = list((await self.db.execute(query.order_by(*sort).limit(limit + 1))).scalars())
        return rows[:limit], len(rows) > limit

    async def get_last_activity_for_threads(self, *, uid: str, app_id: str | None, thread_ids: list[str]) -> dict:
        """从已接收输入与执行时间计算活动时间，不受标题或已读更新影响。"""
        from yuxi.modules.agents.models.inputs import AgentInput, AgentInputReceipt

        result = {}
        for model, times in (
            (AgentInputReceipt, (AgentInputReceipt.created_at,)),
            (AgentInput, (AgentInput.created_at, AgentInput.consumed_at, AgentInput.cancelled_at)),
            (AgentRun, (AgentRun.created_at, AgentRun.started_at, AgentRun.finished_at)),
        ):
            query = (
                select(model.thread_id, *(func.max(column) for column in times))
                .where(model.uid == uid, model.app_id == app_id, model.thread_id.in_(thread_ids))
                .group_by(model.thread_id)
            )
            for thread_id, *values in (await self.db.execute(query)).all():
                timestamp = max((value for value in values if value is not None), default=None)
                if timestamp is not None and (thread_id not in result or timestamp > result[thread_id]):
                    result[thread_id] = timestamp
        return result

    async def search_sessions_by_message_content(
        self,
        *,
        uid: str,
        query: str,
        agent_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
        app_id: str | None | object = ALL_APP_SCOPES,
    ) -> tuple[list[dict], bool]:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return [], False

        session_conditions = [
            Session.uid == str(uid),
            Session.status == "active",
        ]
        if agent_id:
            session_conditions.append(Session.agent_id == agent_id)
        if app_id is not ALL_APP_SCOPES:
            session_conditions.append(Session.app_id == app_id)

        message_conditions = self._message_search_conditions(normalized_query)
        summary = (
            select(
                Message.session_record_id.label("session_record_id"),
                func.count(Message.id).label("matched_count"),
                func.max(Message.created_at).label("latest_match_at"),
            )
            .join(Session, Session.id == Message.session_record_id)
            .where(*session_conditions, *message_conditions)
            .group_by(Message.session_record_id)
            .subquery()
        )

        result = await self.db.execute(
            select(Session, summary.c.matched_count, summary.c.latest_match_at)
            .join(summary, Session.id == summary.c.session_record_id)
            .order_by(summary.c.latest_match_at.desc(), Session.updated_at.desc(), Session.id.desc())
            .limit(limit + 1)
            .offset(offset)
        )
        rows = list(result.all())
        has_more = len(rows) > limit
        rows = rows[:limit]

        if not rows:
            return [], has_more
        matches = (
            select(
                Message.session_record_id,
                Message.id,
                Message.content,
                Message.created_at,
                func.row_number()
                .over(
                    partition_by=Message.session_record_id,
                    order_by=(Message.created_at.desc(), Message.id.desc()),
                )
                .label("rank"),
            )
            .where(Message.session_record_id.in_([session.id for session, *_ in rows]), *message_conditions)
            .subquery()
        )
        snippets_by_session = {session.id: [] for session, *_ in rows}
        snippet_result = await self.db.execute(
            select(matches)
            .where(matches.c.rank <= MESSAGE_SEARCH_SNIPPETS_PER_THREAD)
            .order_by(matches.c.session_record_id, matches.c.rank)
        )
        for session_id, message_id, content, created_at, _rank in snippet_result:
            snippets_by_session[session_id].append(
                {
                    "message_id": message_id,
                    "content": self._build_message_search_snippet(content, normalized_query),
                    "created_at": created_at,
                }
            )
        items: list[dict] = []
        for agent_session, matched_count, latest_match_at in rows:
            snippets = snippets_by_session[agent_session.id]

            items.append(
                {
                    "agent_session": agent_session,
                    "matched_count": int(matched_count or 0),
                    "latest_match_at": latest_match_at,
                    "message_id": snippets[0]["message_id"] if snippets else None,
                    "snippets": snippets,
                }
            )

        return items, has_more

    async def search_memory_messages(self, *, uid: str, query: str, limit: int = 5) -> dict:
        """搜索当前用户可见的普通主 Agent 历史消息。"""
        normalized_query = str(query or "").strip()
        if not normalized_query:
            raise ValueError("query 不能为空")
        if len(normalized_query) > MEMORY_HISTORY_SEARCH_QUERY_MAX_CHARS:
            raise ValueError(f"query 最多 {MEMORY_HISTORY_SEARCH_QUERY_MAX_CHARS} 个字符")
        bounded_limit = max(1, min(int(limit), MEMORY_HISTORY_SEARCH_MAX_LIMIT))
        message_conditions = self._message_search_conditions(normalized_query)

        result = await self.db.execute(
            select(
                Session.thread_id,
                Session.title,
                Message.id,
                Message.role,
                Message.content,
            )
            .join(Session, Session.id == Message.session_record_id)
            .where(
                *self._memory_session_conditions(uid),
                *message_conditions,
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(bounded_limit)
        )

        items: list[dict] = []
        response_truncated = False
        for row in result.all():
            snippet = self._build_message_search_snippet(row.content, normalized_query)
            snippet, snippet_truncated = truncate_utf8(snippet, MEMORY_HISTORY_SEARCH_SNIPPET_MAX_BYTES)
            item = {
                "thread_id": row.thread_id,
                "title": row.title,
                "message_id": row.id,
                "role": row.role,
                "content": snippet,
            }
            if snippet_truncated:
                item["truncated"] = True
            items.append(item)
            if _json_size({"items": items}) > MEMORY_HISTORY_SEARCH_RESPONSE_MAX_BYTES:
                items.pop()
                response_truncated = True
                break
        response = {"items": items}
        if response_truncated:
            response["truncated"] = True
        return response

    async def read_memory_messages(
        self,
        *,
        uid: str,
        thread_id: str,
        message_id: int | None = None,
        limit: int = 20,
        include_tools: bool = False,
    ) -> dict:
        """读取当前用户普通主 Agent 线程的有界历史。"""
        bounded_limit = max(1, min(int(limit), MEMORY_HISTORY_READ_MAX_LIMIT))
        session_result = await self.db.execute(
            select(Session.id, Session.thread_id, Session.title).where(
                Session.thread_id == str(thread_id),
                *self._memory_session_conditions(uid),
            )
        )
        agent_session = session_result.one_or_none()
        if agent_session is None:
            raise ValueError("历史线程不存在或不可见")

        message_type_condition = or_(
            Message.message_type.is_(None),
            Message.message_type.notin_(MESSAGE_SEARCH_EXCLUDED_TYPES),
        )
        if include_tools:
            message_type_condition = or_(message_type_condition, _state_proven_model_tool_call_condition())
        message_conditions = [
            Message.session_record_id == agent_session.id,
            Message.role.in_(MESSAGE_SEARCH_ROLES),
            message_type_condition,
        ]
        if message_id is None:
            query = (
                self._memory_message_select()
                .where(*message_conditions)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(bounded_limit)
            )
            result = await self.db.execute(query)
            rows = list(result.all())
            rows.reverse()
        else:
            anchor_id = int(message_id)
            anchor_result = await self.db.execute(select(Message.id).where(Message.id == anchor_id, *message_conditions))
            if anchor_result.scalar_one_or_none() is None:
                raise ValueError("历史消息不存在或不属于该线程")

            before_limit = (bounded_limit + 1) // 2
            before_query = (
                self._memory_message_select()
                .where(*message_conditions, Message.id <= anchor_id)
                .order_by(Message.id.desc())
                .limit(before_limit)
            )
            before_result = await self.db.execute(before_query)
            before = list(before_result.all())
            before.reverse()

            after_limit = bounded_limit - len(before)
            after = []
            if after_limit:
                after_query = (
                    self._memory_message_select()
                    .where(*message_conditions, Message.id > anchor_id)
                    .order_by(Message.id.asc())
                    .limit(after_limit)
                )
                after_result = await self.db.execute(after_query)
                after = list(after_result.all())
            rows = before + after

        messages = self._serialize_memory_messages(rows)
        tool_calls, tools_truncated = await self._serialize_memory_tool_calls(
            [item["message_id"] for item in messages],
            include_tools=include_tools,
        )
        is_truncated = tools_truncated or any(item.get("truncated") for item in messages)
        payload = {
            "thread_id": agent_session.thread_id,
            "title": agent_session.title,
            "messages": messages,
            "tool_calls": tool_calls,
        }
        if is_truncated:
            payload["truncated"] = True
        self._fit_memory_read_response(payload)
        return payload

    def _memory_session_conditions(self, uid: str) -> list:
        """构建用户可见主 Agent Session 条件。"""
        return [
            Session.uid == str(uid),
            Session.status == "active",
        ]

    @staticmethod
    def _memory_message_select():
        return select(
            Message.id,
            Message.role,
            Message.content,
        )

    @staticmethod
    def _serialize_memory_messages(rows: list) -> list[dict]:
        messages: list[dict] = []
        remaining = MEMORY_HISTORY_MESSAGES_MAX_BYTES
        for row in rows:
            content_budget = min(MEMORY_HISTORY_MESSAGE_MAX_BYTES, remaining)
            content, truncated = truncate_utf8(row.content, content_budget)
            remaining = max(0, remaining - len(content.encode("utf-8")))
            msg_item = {
                "message_id": row.id,
                "role": row.role,
                "content": content,
            }
            if truncated:
                msg_item["truncated"] = True
            messages.append(msg_item)
        return messages

    async def _serialize_memory_tool_calls(
        self,
        message_ids: list[int],
        *,
        include_tools: bool,
    ) -> tuple[list[dict], bool]:
        if not include_tools or not message_ids:
            return [], False
        result = await self.db.execute(
            select(
                ToolCall.langgraph_tool_call_id,
                ToolCall.tool_name,
                ToolCall.tool_input,
                ToolCall.tool_output,
                ToolCall.status,
                ToolCall.error_message,
            )
            .where(ToolCall.message_id.in_(message_ids))
            .order_by(ToolCall.created_at.asc(), ToolCall.id.asc())
            .limit(MEMORY_HISTORY_TOOL_CALL_MAX_COUNT + 1)
        )
        rows = list(result.all())
        truncated = len(rows) > MEMORY_HISTORY_TOOL_CALL_MAX_COUNT
        tool_calls: list[dict] = []
        used_bytes = 0
        for row in rows[:MEMORY_HISTORY_TOOL_CALL_MAX_COUNT]:
            tool_input = json.dumps(row.tool_input or {}, ensure_ascii=False, separators=(",", ":"))
            tool_input, input_truncated = truncate_utf8(tool_input, 1024)
            tool_output, output_truncated = truncate_utf8(row.tool_output, 2048)
            error, error_truncated = truncate_utf8(row.error_message, 512)
            tool_item = {
                "tool_call_id": row.langgraph_tool_call_id,
                "name": row.tool_name,
                "input": tool_input,
                "output": tool_output,
                "status": row.status,
                "error": error,
            }
            if input_truncated or output_truncated or error_truncated:
                tool_item["truncated"] = True
            item_size = _json_size(tool_item)
            if item_size > MEMORY_HISTORY_TOOL_CALL_MAX_BYTES or used_bytes + item_size > MEMORY_HISTORY_TOOL_CALLS_MAX_BYTES:
                truncated = True
                break
            used_bytes += item_size
            tool_calls.append(tool_item)
        return tool_calls, truncated

    @staticmethod
    def _fit_memory_read_response(payload: dict) -> None:
        """确保历史读取最终 JSON 响应不超过协议预算。"""
        while _json_size(payload) > MEMORY_HISTORY_READ_RESPONSE_MAX_BYTES and payload["tool_calls"]:
            payload["tool_calls"].pop()
            payload["truncated"] = True
        while _json_size(payload) > MEMORY_HISTORY_READ_RESPONSE_MAX_BYTES and payload["messages"]:
            payload["messages"].pop(0)
            payload["truncated"] = True
