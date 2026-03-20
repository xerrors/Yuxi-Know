import shlex
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents import agent_manager
from src.repositories.conversation_repository import ConversationRepository
from src.sandbox import (
    ProvisionerSandboxBackend,
    ensure_thread_dirs,
    get_sandbox_provider,
    sandbox_uploads_dir,
)
from src.services.doc_converter import ATTACHMENT_ALLOWED_EXTENSIONS, MAX_ATTACHMENT_SIZE_BYTES
from src.utils.datetime_utils import utc_isoformat
from src.utils.logging_config import logger

UPLOADS_VIRTUAL_PREFIX = "/mnt/user-data/uploads"


async def require_user_conversation(conv_repo: ConversationRepository, thread_id: str, user_id: str):
    conversation = await conv_repo.get_conversation_by_thread_id(thread_id)
    if not conversation or conversation.user_id != str(user_id) or conversation.status == "deleted":
        raise HTTPException(status_code=404, detail="对话线程不存在")
    return conversation


def _make_upload_virtual_path(file_name: str) -> str:
    safe_name = file_name.replace("/", "_").replace("\\", "_").strip(" .")
    return f"{UPLOADS_VIRTUAL_PREFIX}/{safe_name or 'attachment.bin'}"


def _artifact_url(thread_id: str, virtual_path: str) -> str:
    return f"/api/chat/thread/{thread_id}/artifacts/{virtual_path.lstrip('/')}"


def _build_state_uploads(attachments: list[dict]) -> list[dict]:
    uploads: list[dict] = []
    for attachment in attachments:
        path = attachment.get("path")
        if not isinstance(path, str) or not path.strip():
            continue

        uploads.append(
            {
                "file_id": attachment.get("file_id"),
                "file_name": attachment.get("file_name"),
                "file_type": attachment.get("file_type"),
                "file_size": attachment.get("file_size", 0),
                "status": attachment.get("status", "uploaded"),
                "uploaded_at": attachment.get("uploaded_at"),
                "path": path,
                "artifact_url": attachment.get("artifact_url"),
            }
        )
    return uploads


async def _sync_thread_upload_state(
    *,
    thread_id: str,
    user_id: str,
    agent_id: str,
    attachments: list[dict],
) -> None:
    try:
        agent = agent_manager.get_agent(agent_id)
        if not agent:
            logger.warning(f"Skip upload state sync: agent not found ({agent_id})")
            return

        graph = await agent.get_graph()
        config = {"configurable": {"thread_id": thread_id, "user_id": str(user_id)}}

        await graph.aupdate_state(
            config=config,
            values={
                "uploads": _build_state_uploads(attachments),
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Failed to sync upload state for thread {thread_id}: {exc}")


def serialize_attachment(record: dict) -> dict:
    path = record.get("path")
    return {
        "file_id": record.get("file_id"),
        "file_name": record.get("file_name"),
        "file_type": record.get("file_type"),
        "file_size": record.get("file_size", 0),
        "status": record.get("status", "uploaded"),
        "uploaded_at": record.get("uploaded_at"),
        "path": path,
        "artifact_url": record.get("artifact_url"),
        "minio_url": record.get("minio_url"),
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
    agent_id: str | None,
    db: AsyncSession,
    current_user_id: str,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    conv_repo = ConversationRepository(db)
    conversations = await conv_repo.list_conversations(
        user_id=str(current_user_id),
        agent_id=agent_id,
        status="active",
        limit=limit,
        offset=offset,
    )

    return [
        {
            "id": conv.thread_id,
            "user_id": conv.user_id,
            "agent_id": conv.agent_id,
            "title": conv.title,
            "is_pinned": bool(conv.is_pinned),
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
    title: str | None = None,
    is_pinned: bool | None = None,
    db: AsyncSession,
    current_user_id: str,
) -> dict:
    conv_repo = ConversationRepository(db)
    await require_user_conversation(conv_repo, thread_id, str(current_user_id))
    updated_conv = await conv_repo.update_conversation(thread_id, title=title, is_pinned=is_pinned)
    if not updated_conv:
        raise HTTPException(status_code=500, detail="更新失败")
    return {
        "id": updated_conv.thread_id,
        "user_id": updated_conv.user_id,
        "agent_id": updated_conv.agent_id,
        "title": updated_conv.title,
        "is_pinned": bool(updated_conv.is_pinned),
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
    if not file.filename:
        raise HTTPException(status_code=400, detail="无法识别的文件名")

    file_name = Path(file.filename).name
    await file.seek(0)
    file_content = await file.read()
    file_size = len(file_content)
    if file_size > MAX_ATTACHMENT_SIZE_BYTES:
        max_size_mb = MAX_ATTACHMENT_SIZE_BYTES // (1024 * 1024)
        raise HTTPException(status_code=400, detail=f"附件过大，当前仅支持 {max_size_mb} MB 以内的文件")

    upload_virtual_path = _make_upload_virtual_path(file_name)
    artifact_url = _artifact_url(thread_id, upload_virtual_path)

    ensure_thread_dirs(thread_id)
    uploads_dir = sandbox_uploads_dir(thread_id)
    upload_actual_path = uploads_dir / Path(upload_virtual_path).name
    upload_actual_path.write_bytes(file_content)

    provider = get_sandbox_provider()
    connection = provider.get(thread_id, create_if_missing=False)
    if connection is not None:
        backend = ProvisionerSandboxBackend(thread_id=thread_id)
        backend.upload_files(
            [
                (upload_virtual_path, file_content),
            ]
        )

    attachment_record = {
        "file_id": uuid.uuid4().hex,
        "file_name": file_name,
        "file_type": file.content_type,
        "file_size": file_size,
        "status": "uploaded",
        "uploaded_at": utc_isoformat(),
        "path": upload_virtual_path,
        "artifact_url": artifact_url,
        "minio_url": None,
        "storage_path": str(upload_actual_path),
    }

    await conv_repo.add_attachment(conversation.id, attachment_record)
    all_attachments = await conv_repo.get_attachments(conversation.id)
    await _sync_thread_upload_state(
        thread_id=thread_id,
        user_id=str(current_user_id),
        agent_id=conversation.agent_id,
        attachments=all_attachments,
    )

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

    existing_attachments = await conv_repo.get_attachments(conversation.id)
    target_attachment = next((item for item in existing_attachments if item.get("file_id") == file_id), None)

    removed = await conv_repo.remove_attachment(conversation.id, file_id)
    if not removed:
        raise HTTPException(status_code=404, detail="附件不存在或已被删除")

    if target_attachment:
        candidate = target_attachment.get("storage_path")
        if candidate:
            try:
                file_path = Path(candidate)
                if file_path.exists():
                    file_path.unlink()
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Failed to remove attachment file {candidate}: {exc}")

    all_attachments = await conv_repo.get_attachments(conversation.id)
    await _sync_thread_upload_state(
        thread_id=thread_id,
        user_id=str(current_user_id),
        agent_id=conversation.agent_id,
        attachments=all_attachments,
    )

    if target_attachment:
        provider = get_sandbox_provider()
        connection = provider.get(thread_id, create_if_missing=False)
        if connection is not None:
            backend = ProvisionerSandboxBackend(thread_id=thread_id)
            delete_commands = []
            path = target_attachment.get("path")
            if isinstance(path, str) and path.strip():
                delete_commands.append(f"rm -f {shlex.quote(path)}")
            if delete_commands:
                backend.execute(" && ".join(delete_commands))

    return {"message": "附件已删除"}
