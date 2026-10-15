"""Dashboard 统计与监控业务用例服务。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from yuxi.modules.agents.repositories.messages import MessageRepository
from yuxi.modules.agents.services.message_audits import serialize_tool_audit
from yuxi.modules.agents.repositories.sessions import SessionRepository
from yuxi.modules.system.repositories.dashboard import DashboardRepository
from yuxi.shared.datetime import format_utc_datetime


class DashboardService:
    """封装 Dashboard 统计读模型、会话查询与时间序列分析。"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = DashboardRepository(db)
        self.session_repo = SessionRepository(db)

    async def get_basic_stats(self) -> dict[str, Any]:
        """读取基础统计指标（会话数、消息数、用户数）。"""
        return await self.repo.get_basic_stats()

    async def get_user_activity_stats(self, *, now: datetime | None = None) -> dict[str, Any]:
        """统计用户总量与活跃趋势。"""
        return await self.repo.get_user_activity_stats(now=now)

    async def get_tool_call_stats(self, *, now: datetime | None = None) -> dict[str, Any]:
        """统计工具调用总量、成功率与分布。"""
        return await self.repo.get_tool_call_stats(now=now)

    async def get_agent_analytics(self) -> dict[str, Any]:
        """汇总智能体对话与工具使用情况。"""
        return await self.repo.get_agent_analytics()

    async def get_call_timeseries(self, *, metric_type: str, time_range: str = "14days") -> dict[str, Any]:
        """查询调用分析时间序列。"""
        return await self.repo.get_call_timeseries(
            metric_type=metric_type,
            time_range=time_range,
        )

    async def get_thread_analytics(
        self,
        *,
        time_range: str = "30days",
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """汇总会话（Thread）多维分析统计。"""
        return await self.repo.get_thread_analytics(
            time_range=time_range,
            agent_id=agent_id,
        )

    async def get_session_filter_options(self) -> dict[str, list[dict[str, Any]]]:
        """读取会话审计用户与 Agent 筛选项。"""
        return await self.repo.get_session_filter_options()

    async def list_sessions(
        self,
        *,
        uid: str | None = None,
        agent_id: str | None = None,
        status: str = "all",
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """分页查询并组装 Dashboard 对话列表。"""
        return await self.repo.list_sessions(
            uid=uid,
            agent_id=agent_id,
            status=status,
            search=search,
            limit=limit,
            offset=offset,
        )

    async def get_session_detail(self, thread_id: str) -> dict[str, Any] | None:
        """获取指定会话完整消息流水与统计。"""
        agent_session = await self.session_repo.get_session_by_thread_id(thread_id)
        if not agent_session:
            return None

        messages = await MessageRepository(self.db).get_messages(agent_session.id)
        executions = await MessageRepository(self.db).list_tool_executions([message.id for message in messages])
        tools_by_source = {}
        for execution in executions:
            source_id = execution.extra_metadata["source_model_message_id"]
            tools_by_source.setdefault(source_id, []).append(serialize_tool_audit(execution))
        audit_metadata = await self.repo.get_session_audit_metadata(agent_session)
        message_list = []
        for message in messages:
            message_data = {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "message_type": message.message_type,
                "created_at": format_utc_datetime(message.created_at) or "",
            }
            message_data["tool_executions"] = tools_by_source.get(message.id, [])
            message_list.append(message_data)

        return {
            "thread_id": agent_session.thread_id,
            "uid": agent_session.uid,
            "username": audit_metadata["username"],
            "user_avatar": audit_metadata["user_avatar"],
            "user_deleted": audit_metadata["user_deleted"],
            "agent_id": agent_session.agent_id,
            "agent_name": audit_metadata["agent_name"],
            "agent_avatar": audit_metadata["agent_avatar"],
            "agent_deleted": audit_metadata["agent_deleted"],
            "title": agent_session.title,
            "status": agent_session.status,
            "is_pinned": bool(agent_session.is_pinned),
            "message_count": len(message_list),
            "created_at": format_utc_datetime(agent_session.created_at) or "",
            "updated_at": format_utc_datetime(agent_session.updated_at) or "",
            **await self.repo.get_session_token_usage(agent_session.id),
            "messages": message_list,
        }
