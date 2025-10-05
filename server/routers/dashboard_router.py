"""
Dashboard Router - Statistics and monitoring endpoints

Provides centralized dashboard APIs for monitoring system-wide statistics.
"""

import traceback
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from server.routers.auth_router import get_admin_user
from server.utils.auth_middleware import get_db
from src.storage.conversation import ConversationManager
from src.storage.db.models import User
from src.utils.logging_config import logger


dashboard = APIRouter(prefix="/dashboard", tags=["Dashboard"])


# =============================================================================
# Response Models
# =============================================================================


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
# Conversation Management
# =============================================================================


@dashboard.get("/conversations", response_model=list[ConversationListItem])
async def get_all_conversations(
    user_id: str | None = None,
    agent_id: str | None = None,
    status: str = "active",
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """Get all conversations (Admin only)"""
    from src.storage.db.models import Conversation, ConversationStats

    try:
        # Build query
        query = db.query(Conversation, ConversationStats).outerjoin(
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

        results = query.all()

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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """Get conversation detail (Admin only)"""
    try:
        conv_manager = ConversationManager(db)
        conversation = conv_manager.get_conversation_by_thread_id(thread_id)

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Get messages and stats
        messages = conv_manager.get_messages(conversation.id)
        stats = conv_manager.get_stats(conversation.id)

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
# Statistics
# =============================================================================


@dashboard.get("/stats")
async def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """Get dashboard statistics (Admin only)"""
    from src.storage.db.models import Conversation, Message, MessageFeedback

    try:
        # Basic counts
        total_conversations = db.query(func.count(Conversation.id)).scalar() or 0
        active_conversations = (
            db.query(func.count(Conversation.id)).filter(Conversation.status == "active").scalar() or 0
        )
        total_messages = db.query(func.count(Message.id)).scalar() or 0
        total_users = db.query(func.count(distinct(Conversation.user_id))).scalar() or 0

        # Conversations by agent
        conversations_by_agent = (
            db.query(Conversation.agent_id, func.count(Conversation.id).label("count"))
            .group_by(Conversation.agent_id)
            .all()
        )

        # Recent activity (last 24 hours)
        yesterday = datetime.utcnow() - timedelta(days=1)
        recent_conversations = (
            db.query(func.count(Conversation.id)).filter(Conversation.created_at >= yesterday).scalar() or 0
        )
        recent_messages = db.query(func.count(Message.id)).filter(Message.created_at >= yesterday).scalar() or 0

        # Feedback statistics
        total_feedbacks = db.query(func.count(MessageFeedback.id)).scalar() or 0
        like_count = db.query(func.count(MessageFeedback.id)).filter(MessageFeedback.rating == "like").scalar() or 0
        dislike_count = (
            db.query(func.count(MessageFeedback.id)).filter(MessageFeedback.rating == "dislike").scalar() or 0
        )

        # Calculate satisfaction rate
        satisfaction_rate = round((like_count / total_feedbacks * 100), 2) if total_feedbacks > 0 else 0

        # Recent feedback (last 24 hours)
        recent_feedbacks = (
            db.query(func.count(MessageFeedback.id)).filter(MessageFeedback.created_at >= yesterday).scalar() or 0
        )

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total_conversations": total_conversations,
            "active_conversations": active_conversations,
            "total_messages": total_messages,
            "total_users": total_users,
            "conversations_by_agent": [
                {"agent_id": agent_id or "unknown", "count": count} for agent_id, count in conversations_by_agent
            ],
            "recent_activity": {
                "conversations_24h": recent_conversations,
                "messages_24h": recent_messages,
            },
            "feedback_stats": {
                "total_feedbacks": total_feedbacks,
                "like_count": like_count,
                "dislike_count": dislike_count,
                "satisfaction_rate": satisfaction_rate,
                "recent_feedbacks_24h": recent_feedbacks,
            },
        }
    except Exception as e:
        logger.error(f"Error getting dashboard stats: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to get dashboard stats: {str(e)}")


# =============================================================================
# Feedback Management
# =============================================================================


class FeedbackListItem(BaseModel):
    """Feedback list item"""

    id: int
    message_id: int
    user_id: str
    rating: str
    reason: str | None
    created_at: str
    message_content: str
    conversation_title: str | None
    agent_id: str


@dashboard.get("/feedbacks", response_model=list[FeedbackListItem])
async def get_all_feedbacks(
    rating: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user),
):
    """Get all feedback records (Admin only)"""
    from src.storage.db.models import MessageFeedback, Message, Conversation

    try:
        # Build query with joins
        query = (
            db.query(MessageFeedback, Message, Conversation)
            .join(Message, MessageFeedback.message_id == Message.id)
            .join(Conversation, Message.conversation_id == Conversation.id)
        )

        # Apply filters
        if rating and rating in ["like", "dislike"]:
            query = query.filter(MessageFeedback.rating == rating)

        # Order and paginate
        query = query.order_by(MessageFeedback.created_at.desc()).limit(limit).offset(offset)

        results = query.all()

        return [
            {
                "id": feedback.id,
                "message_id": feedback.message_id,
                "user_id": feedback.user_id,
                "rating": feedback.rating,
                "reason": feedback.reason,
                "created_at": feedback.created_at.isoformat(),
                "message_content": message.content[:100] + ("..." if len(message.content) > 100 else ""),
                "conversation_title": conversation.title,
                "agent_id": conversation.agent_id,
            }
            for feedback, message, conversation in results
        ]
    except Exception as e:
        logger.error(f"Error getting feedbacks: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to get feedbacks: {str(e)}")
