import shlex
import uuid
from datetime import UTC, datetime
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
from src.services.doc_converter import (
    ATTACHMENT_ALLOWED_EXTENSIONS,
    MAX_ATTACHMENT_SIZE_BYTES,
    convert_upload_to_markdown,
)
from src.utils.datetime_utils import utc_isoformat
from src.utils.logging_config import logger

UPLOADS_VIRTUAL_PREFIX = "/mnt/user-data/uploads"
LEGACY_ATTACHMENTS_PREFIX = "/attachments/"


async def require_user_conversation(conv_repo: ConversationRepository, thread_id: str, user_id: str):
    conversation = await conv_repo.get_conversation_by_thread_id(thread_id)
    if not conversation or conversation.user_id != str(user_id) or conversation.status == "deleted":
        raise HTTPException(status_code=404, detail="对话线程不存在")
    return conversation


def _sanitize_file_stem(file_name: str) -> str:
    base_name = file_name
    for ext in [".docx", ".txt", ".html", ".htm", ".pdf", ".md"]:
        if file_name.lower().endswith(ext):
            base_name = file_name[: -len(ext)]
            break
    safe_name = base_name.replace("/", "_").replace("\\", "_").strip(" .")
    return safe_name or "attachment"


def _make_attachment_markdown_virtual_path(file_name: str) -> str:
    return f"{UPLOADS_VIRTUAL_PREFIX}/{_sanitize_file_stem(file_name)}.md"


def _make_attachment_original_virtual_path(file_name: str) -> str:
    safe_name = file_name.replace("/", "_").replace("\\", "_").strip(" .")
    return f"{UPLOADS_VIRTUAL_PREFIX}/{safe_name or 'attachment.bin'}"


def _artifact_url(thread_id: str, virtual_path: str) -> str:
    return f"/api/chat/thread/{thread_id}/artifacts/{virtual_path.lstrip('/')}"


def _build_state_files(attachments: list[dict]) -> dict:
    files = {}
    for attachment in attachments:
        if attachment.get("status") != "parsed":
            continue

        file_path = attachment.get("file_path")
        markdown = attachment.get("markdown")
        if not file_path or not markdown:
            continue

        now = datetime.now(UTC).isoformat()
        files[file_path] = {
            "content": markdown.split("\n"),
            "created_at": attachment.get("uploaded_at", now),
            "modified_at": attachment.get("uploaded_at", now),
        }
    return files


async def _sync_thread_attachment_state(
    *,
    thread_id: str,
    user_id: str,
    agent_id: str,
    attachments: list[dict],
) -> None:
    try:
        agent = agent_manager.get_agent(agent_id)
        if not agent:
            logger.warning(f"Skip attachment state sync: agent not found ({agent_id})")
            return

        graph = await agent.get_graph()
        config = {"configurable": {"thread_id": thread_id, "user_id": str(user_id)}}

        state = await graph.aget_state(config)
        state_values = getattr(state, "values", {}) if state else {}
        existing_files = state_values.get("files", {}) if isinstance(state_values, dict) else {}
        if not isinstance(existing_files, dict):
            existing_files = {}

        next_attachment_files = _build_state_files(attachments)
        prev_attachment_paths = {
            path
            for path in existing_files.keys()
            if isinstance(path, str)
            and (path.startswith(LEGACY_ATTACHMENTS_PREFIX) or path.startswith(f"{UPLOADS_VIRTUAL_PREFIX}/"))
        }
        next_attachment_paths = set(next_attachment_files.keys())

        file_updates: dict[str, dict | None] = {**next_attachment_files}
        for removed_path in prev_attachment_paths - next_attachment_paths:
            file_updates[removed_path] = None

        await graph.aupdate_state(
            config=config,
            values={
                "attachments": attachments,
                "files": file_updates,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Failed to sync attachment state for thread {thread_id}: {exc}")


def serialize_attachment(record: dict) -> dict:
    return {
        "file_id": record.get("file_id"),
        "file_name": record.get("file_name"),
        "file_type": record.get("file_type"),
        "file_size": record.get("file_size", 0),
        "status": record.get("status", "parsed"),
        "uploaded_at": record.get("uploaded_at"),
        "truncated": record.get("truncated", False),
        "virtual_path": record.get("virtual_path") or record.get("file_path"),
        "artifact_url": record.get("artifact_url"),
        "original_virtual_path": record.get("original_virtual_path"),
        "original_artifact_url": record.get("original_artifact_url"),
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

    markdown_virtual_path = _make_attachment_markdown_virtual_path(conversion.file_name)
    original_virtual_path = _make_attachment_original_virtual_path(conversion.file_name)
    markdown_artifact_url = _artifact_url(thread_id, markdown_virtual_path)
    original_artifact_url = _artifact_url(thread_id, original_virtual_path)

    ensure_thread_dirs(thread_id)
    uploads_dir = sandbox_uploads_dir(thread_id)
    markdown_actual_path = uploads_dir / Path(markdown_virtual_path).name
    original_actual_path = uploads_dir / Path(original_virtual_path).name

    await file.seek(0)
    file_content = await file.read()
    markdown_actual_path.write_text(conversion.markdown, encoding="utf-8")
    original_actual_path.write_bytes(file_content)

    provider = get_sandbox_provider()
    connection = provider.get(thread_id, create_if_missing=False)
    if connection is not None:
        backend = ProvisionerSandboxBackend(thread_id=thread_id)
        backend.upload_files(
            [
                (markdown_virtual_path, conversion.markdown.encode("utf-8")),
                (original_virtual_path, file_content),
            ]
        )

    attachment_record = {
        "file_id": conversion.file_id,
        "file_name": conversion.file_name,
        "file_type": conversion.file_type,
        "file_size": conversion.file_size,
        "status": "parsed",
        "markdown": conversion.markdown,
        "uploaded_at": utc_isoformat(),
        "truncated": conversion.truncated,
        "file_path": markdown_virtual_path,
        "virtual_path": markdown_virtual_path,
        "artifact_url": markdown_artifact_url,
        "original_virtual_path": original_virtual_path,
        "original_artifact_url": original_artifact_url,
        "minio_url": None,
        "storage_path": str(markdown_actual_path),
        "original_storage_path": str(original_actual_path),
    }
    await conv_repo.add_attachment(conversation.id, attachment_record)
    all_attachments = await conv_repo.get_attachments(conversation.id)
    await _sync_thread_attachment_state(
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
        for candidate in [
            target_attachment.get("storage_path"),
            target_attachment.get("original_storage_path"),
        ]:
            if not candidate:
                continue
            try:
                file_path = Path(candidate)
                if file_path.exists():
                    file_path.unlink()
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Failed to remove attachment file {candidate}: {exc}")

    all_attachments = await conv_repo.get_attachments(conversation.id)
    await _sync_thread_attachment_state(
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
            for path in [
                target_attachment.get("virtual_path") or target_attachment.get("file_path"),
                target_attachment.get("original_virtual_path"),
            ]:
                if isinstance(path, str) and path.strip():
                    delete_commands.append(f"rm -f {shlex.quote(path)}")
            if delete_commands:
                backend.execute(" && ".join(delete_commands))

    return {"message": "附件已删除"}
