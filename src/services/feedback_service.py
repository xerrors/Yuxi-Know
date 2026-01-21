import traceback

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.postgres.models_business import Conversation, Message, MessageFeedback
from src.utils.logging_config import logger


async def submit_message_feedback_view(
    *,
    message_id: int,
    rating: str,
    reason: str | None,
    db: AsyncSession,
    current_user_id: str,
) -> dict:
    if rating not in ["like", "dislike"]:
        raise HTTPException(status_code=422, detail="Rating must be 'like' or 'dislike'")

    try:
        message_result = await db.execute(select(Message).filter_by(id=message_id))
        message = message_result.scalar_one_or_none()
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        conversation_result = await db.execute(select(Conversation).filter_by(id=message.conversation_id))
        conversation = conversation_result.scalar_one_or_none()
        if not conversation or conversation.user_id != str(current_user_id):
            raise HTTPException(status_code=403, detail="Access denied")

        existing_feedback_result = await db.execute(
            select(MessageFeedback).filter_by(message_id=message_id, user_id=str(current_user_id))
        )
        existing_feedback = existing_feedback_result.scalar_one_or_none()
        if existing_feedback:
            raise HTTPException(status_code=409, detail="Feedback already submitted for this message")

        new_feedback = MessageFeedback(
            message_id=message_id,
            user_id=str(current_user_id),
            rating=rating,
            reason=reason,
        )

        db.add(new_feedback)
        await db.commit()
        await db.refresh(new_feedback)

        logger.info(f"User {current_user_id} submitted {rating} feedback for message {message_id}")

        return {
            "id": new_feedback.id,
            "message_id": new_feedback.message_id,
            "rating": new_feedback.rating,
            "reason": new_feedback.reason,
            "created_at": new_feedback.created_at.isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting message feedback: {e}, {traceback.format_exc()}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to submit feedback: {str(e)}")


async def get_message_feedback_view(
    *,
    message_id: int,
    db: AsyncSession,
    current_user_id: str,
) -> dict:
    try:
        feedback_result = await db.execute(
            select(MessageFeedback).filter_by(message_id=message_id, user_id=str(current_user_id))
        )
        feedback = feedback_result.scalar_one_or_none()

        if not feedback:
            return {"has_feedback": False, "feedback": None}

        return {
            "has_feedback": True,
            "feedback": {
                "id": feedback.id,
                "rating": feedback.rating,
                "reason": feedback.reason,
                "created_at": feedback.created_at.isoformat(),
            },
        }

    except Exception as e:
        logger.error(f"Error getting message feedback: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get feedback: {str(e)}")
