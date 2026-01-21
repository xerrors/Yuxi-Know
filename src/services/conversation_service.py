import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.conversation_repository import ConversationRepository
from src.services.doc_converter import (
    ATTACHMENT_ALLOWED_EXTENSIONS,
    MAX_ATTACHMENT_SIZE_BYTES,
    convert_upload_to_markdown,
)
from src.utils.datetime_utils import utc_isoformat
from src.utils.logging_config import logger


async def require_user_conversation(conv_repo: ConversationRepository, thread_id: str, user_id: str):
    conversation = await conv_repo.get_conversation_by_thread_id(thread_id)
    if not conversation or conversation.user_id != str(user_id) or conversation.status == "deleted":
        raise HTTPException(status_code=404, detail="对话线程不存在")
    return conversation


def serialize_attachment(record: dict) -> dict:
    return {
        "file_id": record.get("file_id"),
        "file_name": record.get("file_name"),
        "file_type": record.get("file_type"),
        "file_size": record.get("file_size", 0),
        "status": record.get("status", "parsed"),
        "uploaded_at": record.get("uploaded_at"),
        "truncated": record.get("truncated", False),
    }


async def create_thread_view(
    *,
    agent_id: str,
    title: str | None,
    metadata: dict | None,
    db: AsyncSession,
    current_user_id: str,
) -> dict:
    thread_id = str(uuid.uuid4())
    conv_repo = ConversationRepository(db)
    conversation = await conv_repo.create_conversation(
        user_id=str(current_user_id),
        agent_id=agent_id,
        title=title or "新的对话",
        thread_id=thread_id,
        metadata=metadata,
    )

    return {
        "id": conversation.thread_id,
        "user_id": conversation.user_id,
        "agent_id": conversation.agent_id,
        "title": conversation.title,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
    }


async def list_threads_view(
    *,
    agent_id: str,
    db: AsyncSession,
    current_user_id: str,
) -> list[dict]:
    if not agent_id:
        raise HTTPException(status_code=422, detail="agent_id 不能为空")

    conv_repo = ConversationRepository(db)
    conversations = await conv_repo.list_conversations(
        user_id=str(current_user_id),
        agent_id=agent_id,
        status="active",
    )

    return [
        {
            "id": conv.thread_id,
            "user_id": conv.user_id,
            "agent_id": conv.agent_id,
            "title": conv.title,
            "created_at": conv.created_at.isoformat(),
            "updated_at": conv.updated_at.isoformat(),
        }
        for conv in conversations
    ]


async def delete_thread_view(
    *,
    thread_id: str,
    db: AsyncSession,
    current_user_id: str,
) -> dict:
    conv_repo = ConversationRepository(db)
    await require_user_conversation(conv_repo, thread_id, str(current_user_id))
    deleted = await conv_repo.delete_conversation(thread_id, soft_delete=True)
    if not deleted:
        raise HTTPException(status_code=404, detail="对话线程不存在")
    return {"message": "删除成功"}


async def update_thread_view(
    *,
    thread_id: str,
    title: str | None,
    db: AsyncSession,
    current_user_id: str,
) -> dict:
    conv_repo = ConversationRepository(db)
    await require_user_conversation(conv_repo, thread_id, str(current_user_id))
    updated_conv = await conv_repo.update_conversation(thread_id, title=title)
    if not updated_conv:
        raise HTTPException(status_code=500, detail="更新失败")
    return {
        "id": updated_conv.thread_id,
        "user_id": updated_conv.user_id,
        "agent_id": updated_conv.agent_id,
        "title": updated_conv.title,
        "created_at": updated_conv.created_at.isoformat(),
        "updated_at": updated_conv.updated_at.isoformat(),
    }


async def upload_thread_attachment_view(
    *,
    thread_id: str,
    file: UploadFile,
    db: AsyncSession,
    current_user_id: str,
) -> dict:
    conv_repo = ConversationRepository(db)
    conversation = await require_user_conversation(conv_repo, thread_id, str(current_user_id))

    try:
        conversion = await convert_upload_to_markdown(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"附件解析失败: {exc}")
        raise HTTPException(status_code=500, detail="附件解析失败，请稍后重试") from exc

    attachment_record = {
        "file_id": conversion.file_id,
        "file_name": conversion.file_name,
        "file_type": conversion.file_type,
        "file_size": conversion.file_size,
        "status": "parsed",
        "markdown": conversion.markdown,
        "uploaded_at": utc_isoformat(),
        "truncated": conversion.truncated,
    }
    await conv_repo.add_attachment(conversation.id, attachment_record)

    return serialize_attachment(attachment_record)


async def list_thread_attachments_view(
    *,
    thread_id: str,
    db: AsyncSession,
    current_user_id: str,
) -> dict:
    conv_repo = ConversationRepository(db)
    conversation = await require_user_conversation(conv_repo, thread_id, str(current_user_id))
    attachments = await conv_repo.get_attachments(conversation.id)
    return {
        "attachments": [serialize_attachment(item) for item in attachments],
        "limits": {
            "allowed_extensions": sorted(ATTACHMENT_ALLOWED_EXTENSIONS),
            "max_size_bytes": MAX_ATTACHMENT_SIZE_BYTES,
        },
    }


async def delete_thread_attachment_view(
    *,
    thread_id: str,
    file_id: str,
    db: AsyncSession,
    current_user_id: str,
) -> dict:
    conv_repo = ConversationRepository(db)
    conversation = await require_user_conversation(conv_repo, thread_id, str(current_user_id))
    removed = await conv_repo.remove_attachment(conversation.id, file_id)
    if not removed:
        raise HTTPException(status_code=404, detail="附件不存在或已被删除")
    return {"message": "附件已删除"}
