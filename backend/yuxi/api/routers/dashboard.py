"""Dashboard 统计与监控 HTTP 路由。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.api.dependencies.auth import get_db, get_superadmin_user
from yuxi.modules.agents.services.sandbox import get_vm_stats
from yuxi.modules.identity.models import User
from yuxi.modules.system.services.dashboard import DashboardService

dashboard = APIRouter(prefix="/dashboard", tags=["Dashboard"])


class UserActivityStats(BaseModel):
    """用户活跃度统计。"""

    total_users: int
    active_users_24h: int
    active_users_30d: int
    daily_active_users: list[dict]


class VmStats(BaseModel):
    """执行节点实时 VM 数量。"""

    active_vms: int
    total_vms: int


class ToolCallStats(BaseModel):
    """工具调用统计。"""

    total_calls: int
    successful_calls: int
    failed_calls: int
    success_rate: float
    most_used_tools: list[dict]
    tool_error_distribution: dict
    daily_tool_calls: list[dict]


class AgentAnalytics(BaseModel):
    """AI 智能体分析。"""

    total_agents: int
    agent_session_counts: list[dict]
    agent_tool_usage: list[dict]
    agent_names: dict[str, str] = {}


class SessionListItem(BaseModel):
    """Dashboard 对话列表项。"""

    thread_id: str
    uid: str
    username: str | None = None
    user_avatar: str | None = None
    user_deleted: bool = False
    agent_id: str
    agent_name: str | None = None
    agent_avatar: str | None = None
    agent_deleted: bool = False
    title: str | None
    status: str
    is_pinned: bool = False
    message_count: int
    total_tokens: int | None = None
    token_usage_complete: bool = False
    created_at: str
    updated_at: str


class SessionListResponse(BaseModel):
    """会话分页列表响应。"""

    items: list[SessionListItem]
    total: int
    limit: int
    offset: int


class SessionFilterOption(BaseModel):
    """会话审计筛选选项。"""

    uid: str | None = None
    username: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    avatar: str | None = None
    is_deleted: bool = False


class SessionFilterOptionsResponse(BaseModel):
    """会话审计用户与 Agent 筛选项。"""

    users: list[SessionFilterOption]
    agents: list[SessionFilterOption]


class SessionDetailResponse(BaseModel):
    """Dashboard 对话详情。"""

    thread_id: str
    uid: str
    username: str | None = None
    user_avatar: str | None = None
    user_deleted: bool = False
    agent_id: str
    agent_name: str | None = None
    agent_avatar: str | None = None
    agent_deleted: bool = False
    title: str | None
    status: str
    is_pinned: bool = False
    message_count: int
    created_at: str
    updated_at: str
    total_tokens: int | None
    token_usage_complete: bool = False
    messages: list[dict]


class TimeSeriesStats(BaseModel):
    """时间序列统计数据。"""

    data: list[dict]
    categories: list[str]
    total_count: int
    average_count: float
    peak_count: int
    peak_date: str
    agent_names: dict[str, str] | None = None


class ThreadSummary(BaseModel):
    """会话汇总指标。"""

    total_threads: int
    active_threads: int
    total_messages: int
    total_tokens: int
    avg_messages_per_thread: float
    avg_tokens_per_thread: float
    pinned_threads: int = 0


class ThreadDailyTrend(BaseModel):
    """每日会话趋势。"""

    date: str
    new_threads: int
    active_threads: int
    message_count: int


class ThreadAgentStat(BaseModel):
    """智能体会话分布指标。"""

    agent_id: str
    agent_name: str
    thread_count: int
    message_count: int
    token_count: int
    avg_messages: float
    agent_avatar: str | None = None


class AgentSessionStat(BaseModel):
    """所选创建范围内的单个智能体会话指标。"""

    agent_id: str
    agent_name: str
    thread_count: int
    message_count: int
    avg_messages: float


class AgentSessionDistribution(BaseModel):
    """智能体会话分布与同口径摘要。"""

    total_threads: int
    agent_count: int
    avg_messages_per_thread: float
    agent_distribution: list[AgentSessionStat]


class ThreadUserStat(BaseModel):
    """高频用户统计项。"""

    uid: str
    username: str | None
    avatar: str | None
    thread_count: int
    message_count: int
    last_active_at: str | None


class ThreadAnalyticsResponse(BaseModel):
    """会话多维分析响应模型。"""

    summary: ThreadSummary
    daily_trends: list[ThreadDailyTrend]
    depth_distribution: dict[str, int]
    agent_distribution: list[ThreadAgentStat]
    top_users: list[ThreadUserStat]
    status_distribution: dict[str, int]


@dashboard.get("/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_superadmin_user),
):
    """获取基础统计指标（超级管理员权限）。"""
    return await DashboardService(db).get_basic_stats()


@dashboard.get("/stats/users", response_model=UserActivityStats)
async def get_user_activity_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_superadmin_user),
):
    """获取用户活动统计（超级管理员权限）。"""
    return UserActivityStats(**await DashboardService(db).get_user_activity_stats())


@dashboard.get("/stats/vms", response_model=VmStats)
async def get_dashboard_vm_stats(current_user: User = Depends(get_superadmin_user)):
    """只向超级管理员返回实时计数，不触发 VM 生命周期动作。"""
    return await get_vm_stats()


@dashboard.get("/stats/tools", response_model=ToolCallStats)
async def get_tool_call_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_superadmin_user),
):
    """获取工具调用统计（超级管理员权限）。"""
    return ToolCallStats(**await DashboardService(db).get_tool_call_stats())


@dashboard.get("/stats/agents", response_model=AgentAnalytics)
async def get_agent_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_superadmin_user),
):
    """获取智能体分析（超级管理员权限）。"""
    return AgentAnalytics(**await DashboardService(db).get_agent_analytics())


@dashboard.get("/stats/calls/timeseries", response_model=TimeSeriesStats)
async def get_call_timeseries_stats(
    type: Literal["models", "agents", "tokens", "tools", "sessions"] = "models",
    time_range: Literal["14hours", "14days", "14weeks"] = "14days",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_superadmin_user),
):
    """获取调用分析时间序列统计（超级管理员权限）。"""
    data = await DashboardService(db).get_call_timeseries(
        metric_type=type,
        time_range=time_range,
    )
    return TimeSeriesStats(**data)


@dashboard.get("/stats/agents/sessions", response_model=AgentSessionDistribution)
async def get_agent_session_distribution(
    time_range: Literal["all", "7days", "30days", "3months"] = "all",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_superadmin_user),
):
    """按会话创建范围读取分布，仅超级管理员可访问。"""
    return await DashboardService(db).get_agent_session_distribution(time_range=time_range)


@dashboard.get("/stats/threads", response_model=ThreadAnalyticsResponse)
async def get_thread_analytics_stats(
    time_range: Literal["7days", "14days", "30days", "90days"] = "30days",
    agent_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_superadmin_user),
):
    """获取会话多维分析统计（超级管理员权限）。"""
    data = await DashboardService(db).get_thread_analytics(
        time_range=time_range,
        agent_id=agent_id,
    )
    return ThreadAnalyticsResponse(**data)


@dashboard.get("/sessions/options", response_model=SessionFilterOptionsResponse)
async def get_session_filter_options(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_superadmin_user),
):
    """获取会话审计用户与 Agent 筛选项（超级管理员权限）。"""
    return await DashboardService(db).get_session_filter_options()


@dashboard.get("/sessions", response_model=SessionListResponse)
async def get_all_sessions(
    uid: str | None = None,
    agent_id: str | None = None,
    status: Literal["active", "archived", "deleted", "all"] = "all",
    search: Annotated[str | None, Query(max_length=255)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_superadmin_user),
):
    """获取所有对话（超级管理员权限）。"""
    return await DashboardService(db).list_sessions(
        uid=uid,
        agent_id=agent_id,
        status=status,
        search=search,
        limit=limit,
        offset=offset,
    )


@dashboard.get("/sessions/{thread_id}", response_model=SessionDetailResponse)
async def get_session_detail(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_superadmin_user),
):
    """获取指定对话详情（超级管理员权限）。"""
    data = await DashboardService(db).get_session_detail(thread_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")
    return data
