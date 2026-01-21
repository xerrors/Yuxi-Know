"""
Dashboard Router - Statistics and monitoring endpoints
仪表板 - 统计和监控端点

Provides centralized dashboard APIs for monitoring system-wide statistics.
提供系统级统计和监控的API接口，用于监控系统运行状态、用户活动、工具调用、知识库使用等。
"""

import traceback
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import String, cast, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.routers.auth_router import get_admin_user
from server.utils.auth_middleware import get_db
from src.storage.conversation import ConversationManager
from src.storage.db.models import User
from src.utils.datetime_utils import UTC, ensure_shanghai, shanghai_now, utc_now
from src.utils.logging_config import logger


dashboard = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# =============================================================================
# Response Models
# =============================================================================


class UserActivityStats(BaseModel):
    """用户活跃度统计"""

    total_users: int
    active_users_24h: int
    active_users_30d: int
    daily_active_users: list[dict]  # 最近7天每日活跃用户


class ToolCallStats(BaseModel):
    """工具调用统计"""

    total_calls: int
    successful_calls: int
    failed_calls: int
    success_rate: float
    most_used_tools: list[dict]
    tool_error_distribution: dict
    daily_tool_calls: list[dict]  # 最近7天每日工具调用数


class KnowledgeStats(BaseModel):
    """知识库统计"""

    total_databases: int
    total_files: int
    total_nodes: int
    total_storage_size: int  # 字节
    databases_by_type: dict
    file_type_distribution: dict


class AgentAnalytics(BaseModel):
    """AI智能体分析"""

    total_agents: int
    agent_conversation_counts: list[dict]
    agent_satisfaction_rates: list[dict]
    agent_tool_usage: list[dict]
    top_performing_agents: list[dict]


class ConversationListItem(BaseModel):
    """Conversation list item"""

    thread_id: str
    user_id: str
    agent_id: str
    title: str
    status: str
    message_count: int
    created_at: str
    updated_at: str


class ConversationDetailResponse(BaseModel):
    """Conversation detail"""

    thread_id: str
    user_id: str
    agent_id: str
    title: str
    status: str
    message_count: int
    created_at: str
    updated_at: str
    total_tokens: int
    messages: list[dict]


# =============================================================================
# Conversation Management - 对话管理
# =============================================================================


@dashboard.get("/conversations", response_model=list[ConversationListItem])
async def get_all_conversations(
    user_id: str | None = None,
    agent_id: str | None = None,
    status: str = "active",
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """获取所有对话（管理员权限）"""
    from src.storage.db.models import Conversation, ConversationStats

    try:
        # Build query
        query = select(Conversation, ConversationStats).outerjoin(
            ConversationStats, Conversation.id == ConversationStats.conversation_id
        )

        # Apply filters
        if user_id:
            query = query.filter(Conversation.user_id == user_id)
        if agent_id:
            query = query.filter(Conversation.agent_id == agent_id)
        if status != "all":
            query = query.filter(Conversation.status == status)

        # Order and paginate
        query = query.order_by(Conversation.updated_at.desc()).limit(limit).offset(offset)

        result = await db.execute(query)
        results = result.all()

        return [
            {
                "thread_id": conv.thread_id,
                "user_id": conv.user_id,
                "agent_id": conv.agent_id,
                "title": conv.title,
                "status": conv.status,
                "message_count": stats.message_count if stats else 0,
                "created_at": conv.created_at.isoformat(),
                "updated_at": conv.updated_at.isoformat(),
            }
            for conv, stats in results
        ]
    except Exception as e:
        logger.error(f"Error getting conversations: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to get conversations: {str(e)}")


@dashboard.get("/conversations/{thread_id}", response_model=ConversationDetailResponse)
async def get_conversation_detail(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """获取指定对话详情（管理员权限）"""
    try:
        conv_manager = ConversationManager(db)
        conversation = await conv_manager.get_conversation_by_thread_id(thread_id)

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Get messages and stats
        messages = await conv_manager.get_messages(conversation.id)
        stats = await conv_manager.get_stats(conversation.id)

        # Format messages
        message_list = []
        for msg in messages:
            msg_dict = {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "message_type": msg.message_type,
                "created_at": msg.created_at.isoformat(),
            }

            # Include tool calls if present
            if msg.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "tool_name": tc.tool_name,
                        "tool_input": tc.tool_input,
                        "tool_output": tc.tool_output,
                        "status": tc.status,
                    }
                    for tc in msg.tool_calls
                ]

            message_list.append(msg_dict)

        return {
            "thread_id": conversation.thread_id,
            "user_id": conversation.user_id,
            "agent_id": conversation.agent_id,
            "title": conversation.title,
            "status": conversation.status,
            "message_count": stats.message_count if stats else len(message_list),
            "created_at": conversation.created_at.isoformat(),
            "updated_at": conversation.updated_at.isoformat(),
            "total_tokens": stats.total_tokens if stats else 0,
            "messages": message_list,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation detail: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to get conversation detail: {str(e)}")


# =============================================================================
# 用户活动统计（管理员权限）
# =============================================================================


@dashboard.get("/stats/users", response_model=UserActivityStats)
async def get_user_activity_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """获取用户活动统计（管理员权限）"""
    try:
        from src.storage.db.models import User, Conversation

        now = utc_now()

        # Conversations may store either the numeric user primary key or the login user_id string.
        # Join condition accounts for both representations.
        user_join_condition = or_(
            Conversation.user_id == User.user_id,
            Conversation.user_id == cast(User.id, String),
        )

        # 基础用户统计（排除已删除用户）
        total_users_result = await db.execute(select(func.count(User.id)).filter(User.is_deleted == 0))
        total_users = total_users_result.scalar() or 0

        # 不同时间段的活跃用户数（基于对话活动，排除已删除用户）
        active_users_24h_result = await db.execute(
            select(func.count(distinct(User.id)))
            .select_from(Conversation)
            .join(User, user_join_condition)
            .filter(Conversation.updated_at >= now - timedelta(days=1), User.is_deleted == 0)
        )
        active_users_24h = active_users_24h_result.scalar() or 0

        active_users_30d_result = await db.execute(
            select(func.count(distinct(User.id)))
            .select_from(Conversation)
            .join(User, user_join_condition)
            .filter(Conversation.updated_at >= now - timedelta(days=30), User.is_deleted == 0)
        )
        active_users_30d = active_users_30d_result.scalar() or 0
        # 最近7天每日活跃用户（排除已删除用户）
        daily_active_users = []
        for i in range(7):
            day_start = now - timedelta(days=i + 1)
            day_end = now - timedelta(days=i)

            active_count_result = await db.execute(
                select(func.count(distinct(User.id)))
                .select_from(Conversation)
                .join(User, user_join_condition)
                .filter(Conversation.updated_at >= day_start, Conversation.updated_at < day_end, User.is_deleted == 0)
            )
            active_count = active_count_result.scalar() or 0

            daily_active_users.append({"date": day_start.strftime("%Y-%m-%d"), "active_users": active_count})

        return UserActivityStats(
            total_users=total_users,
            active_users_24h=active_users_24h,
            active_users_30d=active_users_30d,
            daily_active_users=list(reversed(daily_active_users)),  # 按时间正序
        )

    except Exception as e:
        logger.error(f"Error getting user activity stats: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to get user activity stats: {str(e)}")


# =============================================================================
# Tool Call Statistics - 工具调用统计
# =============================================================================


@dashboard.get("/stats/tools", response_model=ToolCallStats)
async def get_tool_call_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """获取工具调用统计（管理员权限）"""
    try:
        from src.storage.db.models import ToolCall

        now = utc_now()

        # 基础工具调用统计
        total_calls_result = await db.execute(select(func.count(ToolCall.id)))
        total_calls = total_calls_result.scalar() or 0

        successful_calls_result = await db.execute(select(func.count(ToolCall.id)).filter(ToolCall.status == "success"))
        successful_calls = successful_calls_result.scalar() or 0
        failed_calls = total_calls - successful_calls
        success_rate = round((successful_calls / total_calls * 100), 2) if total_calls > 0 else 0

        # 最常用工具
        most_used_tools_result = await db.execute(
            select(ToolCall.tool_name, func.count(ToolCall.id).label("count"))
            .group_by(ToolCall.tool_name)
            .order_by(func.count(ToolCall.id).desc())
            .limit(10)
        )
        most_used_tools = most_used_tools_result.all()
        most_used_tools = [{"tool_name": name, "count": count} for name, count in most_used_tools]

        # 工具错误分布
        tool_errors_result = await db.execute(
            select(ToolCall.tool_name, func.count(ToolCall.id).label("error_count"))
            .filter(ToolCall.status == "error")
            .group_by(ToolCall.tool_name)
        )
        tool_errors = tool_errors_result.all()
        tool_error_distribution = {name: count for name, count in tool_errors}

        # 最近7天每日工具调用数
        daily_tool_calls = []
        for i in range(7):
            day_start = now - timedelta(days=i + 1)
            day_end = now - timedelta(days=i)

            daily_count_result = await db.execute(
                select(func.count(ToolCall.id)).filter(ToolCall.created_at >= day_start, ToolCall.created_at < day_end)
            )
            daily_count = daily_count_result.scalar() or 0

            daily_tool_calls.append({"date": day_start.strftime("%Y-%m-%d"), "call_count": daily_count})

        return ToolCallStats(
            total_calls=total_calls,
            successful_calls=successful_calls,
            failed_calls=failed_calls,
            success_rate=success_rate,
            most_used_tools=most_used_tools,
            tool_error_distribution=tool_error_distribution,
            daily_tool_calls=list(reversed(daily_tool_calls)),
        )

    except Exception as e:
        logger.error(f"Error getting tool call stats: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to get tool call stats: {str(e)}")


# =============================================================================
# 知识库统计（管理员权限）
# =============================================================================


@dashboard.get("/stats/knowledge", response_model=KnowledgeStats)
async def get_knowledge_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """获取知识库统计（管理员权限）"""
    try:
        from src.repositories.knowledge_base_repository import KnowledgeBaseRepository
        from src.repositories.knowledge_file_repository import KnowledgeFileRepository

        kb_repo = KnowledgeBaseRepository()
        file_repo = KnowledgeFileRepository()

        kb_rows = await kb_repo.get_all()
        total_databases = len(kb_rows)

        databases_by_type: dict[str, int] = {}
        files_by_type: dict[str, int] = {}
        total_files = 0
        total_nodes = 0
        total_storage_size = 0

        file_type_mapping = {
            "txt": "文本文件",
            "pdf": "PDF文档",
            "docx": "Word文档",
            "doc": "Word文档",
            "md": "Markdown",
            "html": "HTML网页",
            "htm": "HTML网页",
            "json": "JSON数据",
            "csv": "CSV表格",
            "xlsx": "Excel表格",
            "xls": "Excel表格",
            "pptx": "PowerPoint",
            "ppt": "PowerPoint",
            "png": "PNG图片",
            "jpg": "JPEG图片",
            "jpeg": "JPEG图片",
            "gif": "GIF图片",
            "svg": "SVG图片",
            "mp4": "MP4视频",
            "mp3": "MP3音频",
            "zip": "ZIP压缩包",
            "rar": "RAR压缩包",
            "7z": "7Z压缩包",
        }

        for kb in kb_rows:
            kb_type = (kb.kb_type or "unknown").lower()
            display_type = {
                "lightrag": "LightRAG",
                "faiss": "FAISS",
                "milvus": "Milvus",
                "qdrant": "Qdrant",
                "elasticsearch": "Elasticsearch",
                "unknown": "未知类型",
            }.get(kb_type, kb.kb_type or "未知类型")
            databases_by_type[display_type] = databases_by_type.get(display_type, 0) + 1

            files = await file_repo.list_by_db_id(kb.db_id)
            total_files += len(files)
            for record in files:
                file_ext = (record.file_type or "").lower()
                display_name = file_type_mapping.get(file_ext, file_ext.upper() + "文件" if file_ext else "其他")
                files_by_type[display_name] = files_by_type.get(display_name, 0) + 1
                total_storage_size += int(record.file_size or 0)

        return KnowledgeStats(
            total_databases=total_databases,
            total_files=total_files,
            total_nodes=total_nodes,
            total_storage_size=total_storage_size,
            databases_by_type=databases_by_type,
            file_type_distribution=files_by_type,  # 保持API兼容，但使用新的数据
        )

    except Exception as e:
        logger.error(f"Error getting knowledge stats: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to get knowledge stats: {str(e)}")


# =============================================================================
# 智能体分析（管理员权限）
# =============================================================================


@dashboard.get("/stats/agents", response_model=AgentAnalytics)
async def get_agent_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """获取智能体分析（管理员权限）"""
    try:
        from src.storage.db.models import Conversation, MessageFeedback, Message, ToolCall

        # 获取所有智能体
        agents_result = await db.execute(
            select(Conversation.agent_id, func.count(Conversation.id).label("conversation_count")).group_by(
                Conversation.agent_id
            )
        )
        agents = agents_result.all()

        total_agents = len(agents)
        agent_conversation_counts = [{"agent_id": agent_id, "conversation_count": count} for agent_id, count in agents]

        # 智能体满意度统计
        agent_satisfaction = []
        for agent_id, _ in agents:
            total_feedbacks_result = await db.execute(
                select(func.count(MessageFeedback.id))
                .join(Message, MessageFeedback.message_id == Message.id)
                .join(Conversation, Message.conversation_id == Conversation.id)
                .filter(Conversation.agent_id == agent_id)
            )
            total_feedbacks = total_feedbacks_result.scalar() or 0

            positive_feedbacks_result = await db.execute(
                select(func.count(MessageFeedback.id))
                .join(Message, MessageFeedback.message_id == Message.id)
                .join(Conversation, Message.conversation_id == Conversation.id)
                .filter(Conversation.agent_id == agent_id, MessageFeedback.rating == "like")
            )
            positive_feedbacks = positive_feedbacks_result.scalar() or 0

            satisfaction_rate = round((positive_feedbacks / total_feedbacks * 100), 2) if total_feedbacks > 0 else 100

            agent_satisfaction.append(
                {"agent_id": agent_id, "satisfaction_rate": satisfaction_rate, "total_feedbacks": total_feedbacks}
            )

        # 智能体工具使用统计
        agent_tool_usage = []
        for agent_id, _ in agents:
            tool_usage_count_result = await db.execute(
                select(func.count(ToolCall.id))
                .join(Message, ToolCall.message_id == Message.id)
                .join(Conversation, Message.conversation_id == Conversation.id)
                .filter(Conversation.agent_id == agent_id)
            )
            tool_usage_count = tool_usage_count_result.scalar() or 0

            agent_tool_usage.append({"agent_id": agent_id, "tool_usage_count": tool_usage_count})

        # 表现最佳的智能体（按对话数排序）
        top_performing_agents = []
        for i, (agent_id, conv_count) in enumerate(agents):
            # 获取满意度数据
            satisfaction_data = next(
                (s for s in agent_satisfaction if s["agent_id"] == agent_id), {"satisfaction_rate": 0}
            )

            top_performing_agents.append(
                {
                    "agent_id": agent_id,
                    "conversation_count": conv_count,
                    "satisfaction_rate": satisfaction_data["satisfaction_rate"],
                }
            )

        # 按对话数排序，取前5名
        top_performing_agents.sort(key=lambda x: x["conversation_count"], reverse=True)
        top_performing_agents = top_performing_agents[:5]

        return AgentAnalytics(
            total_agents=total_agents,
            agent_conversation_counts=agent_conversation_counts,
            agent_satisfaction_rates=agent_satisfaction,
            agent_tool_usage=agent_tool_usage,
            top_performing_agents=top_performing_agents,
        )

    except Exception as e:
        logger.error(f"Error getting agent analytics: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to get agent analytics: {str(e)}")


# =============================================================================
# 基础统计（管理员权限）
# =============================================================================


@dashboard.get("/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """获取基础统计（管理员权限）"""
    from src.storage.db.models import Conversation, Message, MessageFeedback

    try:
        # Basic counts
        total_conversations_result = await db.execute(select(func.count(Conversation.id)))
        total_conversations = total_conversations_result.scalar() or 0

        active_conversations_result = await db.execute(
            select(func.count(Conversation.id)).filter(Conversation.status == "active")
        )
        active_conversations = active_conversations_result.scalar() or 0

        total_messages_result = await db.execute(select(func.count(Message.id)))
        total_messages = total_messages_result.scalar() or 0

        total_users_result = await db.execute(select(func.count(User.id)).filter(User.is_deleted == 0))
        total_users = total_users_result.scalar() or 0

        # Feedback statistics
        total_feedbacks_result = await db.execute(select(func.count(MessageFeedback.id)))
        total_feedbacks = total_feedbacks_result.scalar() or 0

        like_count_result = await db.execute(
            select(func.count(MessageFeedback.id)).filter(MessageFeedback.rating == "like")
        )
        like_count = like_count_result.scalar() or 0

        # Calculate satisfaction rate
        satisfaction_rate = round((like_count / total_feedbacks * 100), 2) if total_feedbacks > 0 else 100

        return {
            "total_conversations": total_conversations,
            "active_conversations": active_conversations,
            "total_messages": total_messages,
            "total_users": total_users,
            "feedback_stats": {
                "total_feedbacks": total_feedbacks,
                "satisfaction_rate": satisfaction_rate,
            },
        }
    except Exception as e:
        logger.error(f"Error getting dashboard stats: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to get dashboard stats: {str(e)}")


# =============================================================================
# 反馈管理（管理员权限）
# =============================================================================


class FeedbackListItem(BaseModel):
    """反馈列表项"""

    id: int
    user_id: str
    username: str | None
    avatar: str | None
    rating: str
    reason: str | None
    created_at: str
    message_content: str
    conversation_title: str | None
    agent_id: str


@dashboard.get("/feedbacks", response_model=list[FeedbackListItem])
async def get_all_feedbacks(
    rating: str | None = None,
    agent_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """获取所有反馈记录（管理员权限）"""
    from src.storage.db.models import MessageFeedback, Message, Conversation, User

    try:
        # Build query with joins including User table
        # Try both User.id and User.user_id as MessageFeedback.user_id might be stored as either
        query = (
            select(MessageFeedback, Message, Conversation, User)
            .join(Message, MessageFeedback.message_id == Message.id)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .outerjoin(
                User,
                (MessageFeedback.user_id == User.id) | (MessageFeedback.user_id == User.user_id),
            )
        )

        # Apply filters
        if rating and rating in ["like", "dislike"]:
            query = query.filter(MessageFeedback.rating == rating)
        if agent_id:
            query = query.filter(Conversation.agent_id == agent_id)

        # Order by creation time (most recent first)
        query = query.order_by(MessageFeedback.created_at.desc())

        results = await db.execute(query)
        results = results.all()

        # Debug logging (privacy-safe)
        logger.info(f"Found {len(results)} feedback records")
        # Removed sensitive user data from logs for privacy compliance

        return [
            {
                "id": feedback.id,
                "message_id": feedback.message_id,
                "user_id": feedback.user_id,
                "username": user.username if user else None,
                "avatar": user.avatar if user else None,
                "rating": feedback.rating,
                "reason": feedback.reason,
                "created_at": feedback.created_at.isoformat(),
                "message_content": message.content,
                "conversation_title": conversation.title,
                "agent_id": conversation.agent_id,
            }
            for feedback, message, conversation, user in results
        ]
    except Exception as e:
        logger.error(f"Error getting feedbacks: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to get feedbacks: {str(e)}")


# =============================================================================
# 调用分析时间序列统计（管理员权限）
# =============================================================================


class TimeSeriesStats(BaseModel):
    """时间序列统计数据"""

    data: list[dict]  # [{"date": "2024-01-01", "data": {"item1": 50, "item2": 30}, "total": 80}, ...]
    categories: list[str]  # 所有类别名称
    total_count: int
    average_count: float
    peak_count: int
    peak_date: str


@dashboard.get("/stats/calls/timeseries", response_model=TimeSeriesStats)
async def get_call_timeseries_stats(
    type: str = "models",  # models/agents/tokens/tools
    time_range: str = "14days",  # 14hours/14days/14weeks
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """获取调用分析时间序列统计（管理员权限）"""
    try:
        from src.storage.db.models import Conversation, Message, ToolCall

        # 计算时间范围（使用北京时间 UTC+8）
        now = utc_now()
        local_now = shanghai_now()

        if time_range == "14hours":
            intervals = 14
            # 包含当前小时：从13小时前开始
            start_time = now - timedelta(hours=intervals - 1)
            group_format = func.strftime("%Y-%m-%d %H:00", func.datetime(Message.created_at, "+8 hours"))
            base_local_time = ensure_shanghai(start_time)
        elif time_range == "14weeks":
            intervals = 14
            # 包含当前周：从13周前开始，并对齐到当周周一 00:00
            local_start = local_now - timedelta(weeks=intervals - 1)
            local_start = local_start - timedelta(days=local_start.weekday())
            local_start = local_start.replace(hour=0, minute=0, second=0, microsecond=0)
            start_time = local_start.astimezone(UTC)
            group_format = func.strftime("%Y-%W", func.datetime(Message.created_at, "+8 hours"))
            base_local_time = local_start
        else:  # 14days (default)
            intervals = 14
            # 包含当前天：从13天前开始
            start_time = now - timedelta(days=intervals - 1)
            group_format = func.strftime("%Y-%m-%d", func.datetime(Message.created_at, "+8 hours"))
            base_local_time = ensure_shanghai(start_time)

        # 根据类型查询数据
        if type == "models":
            # 模型调用统计（基于消息数量，按模型分组）
            # 从message的extra_metadata中提取模型信息
            query_result = await db.execute(
                select(
                    group_format.label("date"),
                    func.count(Message.id).label("count"),
                    func.json_extract(Message.extra_metadata, "$.response_metadata.model_name").label("category"),
                )
                .filter(Message.role == "assistant", Message.created_at >= start_time)
                .filter(Message.extra_metadata.isnot(None))
                .group_by(group_format, func.json_extract(Message.extra_metadata, "$.response_metadata.model_name"))
                .order_by(group_format)
            )
            query = query_result.all()
        elif type == "agents":
            # 智能体调用统计（基于对话更新时间，按智能体分组）
            # 为对话创建独立的时间格式化器
            if time_range == "14hours":
                conv_group_format = func.strftime("%Y-%m-%d %H:00", func.datetime(Conversation.updated_at, "+8 hours"))
            elif time_range == "14weeks":
                conv_group_format = func.strftime("%Y-%W", func.datetime(Conversation.updated_at, "+8 hours"))
            else:  # 14days
                conv_group_format = func.strftime("%Y-%m-%d", func.datetime(Conversation.updated_at, "+8 hours"))

            query_result = await db.execute(
                select(
                    conv_group_format.label("date"),
                    func.count(Conversation.id).label("count"),
                    Conversation.agent_id.label("category"),
                )
                .filter(Conversation.updated_at.isnot(None))
                .filter(Conversation.updated_at >= start_time)
                .group_by(conv_group_format, Conversation.agent_id)
                .order_by(conv_group_format)
            )
            query = query_result.all()
        elif type == "tokens":
            # Token消耗统计（区分input/output tokens）
            # 先查询input tokens
            from sqlalchemy import literal

            input_query_result = await db.execute(
                select(
                    group_format.label("date"),
                    func.sum(
                        func.coalesce(func.json_extract(Message.extra_metadata, "$.usage_metadata.input_tokens"), 0)
                    ).label("count"),
                    literal("input_tokens").label("category"),
                )
                .filter(
                    Message.created_at >= start_time,
                    Message.extra_metadata.isnot(None),
                    func.json_extract(Message.extra_metadata, "$.usage_metadata").isnot(None),
                )
                .group_by(group_format)
                .order_by(group_format)
            )
            input_query = input_query_result.all()

            # 查询output tokens
            output_query_result = await db.execute(
                select(
                    group_format.label("date"),
                    func.sum(
                        func.coalesce(func.json_extract(Message.extra_metadata, "$.usage_metadata.output_tokens"), 0)
                    ).label("count"),
                    literal("output_tokens").label("category"),
                )
                .filter(
                    Message.created_at >= start_time,
                    Message.extra_metadata.isnot(None),
                    func.json_extract(Message.extra_metadata, "$.usage_metadata").isnot(None),
                )
                .group_by(group_format)
                .order_by(group_format)
            )
            output_query = output_query_result.all()

            # 合并两个查询结果
            input_results = input_query
            output_results = output_query
            results = input_results + output_results
        elif type == "tools":
            # 工具调用统计（按工具名称分组）
            # 为工具调用创建独立的时间格式化器
            if time_range == "14hours":
                tool_group_format = func.strftime("%Y-%m-%d %H:00", func.datetime(ToolCall.created_at, "+8 hours"))
            elif time_range == "14weeks":
                tool_group_format = func.strftime("%Y-%W", func.datetime(ToolCall.created_at, "+8 hours"))
            else:  # 14days
                tool_group_format = func.strftime("%Y-%m-%d", func.datetime(ToolCall.created_at, "+8 hours"))

            query_result = await db.execute(
                select(
                    tool_group_format.label("date"),
                    func.count(ToolCall.id).label("count"),
                    ToolCall.tool_name.label("category"),
                )
                .filter(ToolCall.created_at >= start_time)
                .group_by(tool_group_format, ToolCall.tool_name)
                .order_by(tool_group_format)
            )
            query = query_result.all()
        else:
            raise HTTPException(status_code=422, detail=f"Invalid type: {type}")

        if type != "tokens":
            results = query

        # 处理堆叠数据格式
        # 首先收集所有类别
        categories = set()
        for result in results:
            if hasattr(result, "category") and result.category:
                categories.add(result.category)

        # 如果没有类别数据，提供默认类别
        if not categories:
            if type == "models":
                categories.add("unknown_model")
            elif type == "agents":
                categories.add("unknown_agent")
            elif type == "tokens":
                categories.update(["input_tokens", "output_tokens"])
            elif type == "tools":
                categories.add("unknown_tool")

        categories = sorted(list(categories))

        # 重新组织数据：按时间点分组每个类别的数据
        time_data = {}

        def normalize_week_key(raw_key: str) -> str:
            base_date = datetime.strptime(f"{raw_key}-1", "%Y-%W-%w")
            iso_year, iso_week, _ = base_date.isocalendar()
            return f"{iso_year}-{iso_week:02d}"

        for result in results:
            date_key = result.date
            if time_range == "14weeks":
                date_key = normalize_week_key(date_key)
            category = getattr(result, "category", "unknown")
            count = result.count

            if date_key not in time_data:
                time_data[date_key] = {}

            time_data[date_key][category] = count

        # 填充缺失的时间点（使用北京时间）
        data = []
        # 从起始点开始（北京时间）
        current_time = base_local_time

        if time_range == "14hours":
            delta = timedelta(hours=1)
        elif time_range == "14weeks":
            delta = timedelta(weeks=1)
        else:
            delta = timedelta(days=1)

        for i in range(intervals):
            if time_range == "14hours":
                date_key = current_time.strftime("%Y-%m-%d %H:00")
            elif time_range == "14weeks":
                iso_year, iso_week, _ = current_time.isocalendar()
                date_key = f"{iso_year}-{iso_week:02d}"
            else:
                date_key = current_time.strftime("%Y-%m-%d")

            # 获取该时间点的数据
            day_data = time_data.get(date_key, {})
            day_total = sum(day_data.values())

            # 确保所有类别都有值（缺失的补0）
            for category in categories:
                if category not in day_data:
                    day_data[category] = 0

            data.append({"date": date_key, "data": day_data, "total": day_total})
            current_time += delta

        # 计算统计指标
        if type == "tools":
            # 对于工具调用，显示所有时间的总数（与ToolStatsComponent保持一致）
            from src.storage.db.models import ToolCall

            total_count_result = await db.execute(select(func.count(ToolCall.id)))
            total_count = total_count_result.scalar() or 0
        else:
            # 其他类型使用时间序列数据的总和
            total_count = sum(item["total"] for item in data)

        average_count = round(total_count / intervals, 2) if intervals > 0 else 0
        peak_data = max(data, key=lambda x: x["total"]) if data else {"total": 0, "date": ""}

        return TimeSeriesStats(
            data=data,
            categories=categories,
            total_count=total_count,
            average_count=average_count,
            peak_count=peak_data["total"],
            peak_date=peak_data["date"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting call timeseries stats: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to get call timeseries stats: {str(e)}")
