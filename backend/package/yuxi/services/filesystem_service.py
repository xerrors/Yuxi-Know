from __future__ import annotations

import asyncio

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from yuxi.agents.backends import (
    ProvisionerSandboxBackend,
    create_agent_composite_backend,
    resolve_visible_knowledge_bases_for_context,
)
from yuxi.agents.backends.sandbox.backend import _looks_like_binary
from yuxi.agents.context import BaseContext
from yuxi.repositories.agent_config_repository import AgentConfigRepository
from yuxi.repositories.conversation_repository import ConversationRepository
from yuxi.services.conversation_service import require_user_conversation
from yuxi.storage.postgres.models_business import User


async def _resolve_filesystem_context(
    *,
    db: AsyncSession,
    user: User,
    agent_id: str,
    agent_config_id: int | None,
) -> BaseContext:
    context = BaseContext(thread_id="", user_id=str(user.id))
    repo = AgentConfigRepository(db)

    config_item = None
    if agent_config_id is not None:
        config_item = await repo.get_by_id(config_id=int(agent_config_id))
        if config_item is not None and (
            config_item.department_id != user.department_id or config_item.agent_id != agent_id
        ):
            config_item = None

    if config_item is None:
        config_item = await repo.get_or_create_default(
            department_id=user.department_id,
            agent_id=agent_id,
            created_by=str(user.id),
        )

    context.update_from_dict((config_item.config_json or {}).get("context", {}))
    return context


async def _resolve_filesystem_state(
    *,
    thread_id: str,
    user: User,
    db: AsyncSession,
    agent_id: str | None,
    agent_config_id: int | None,
):
    conv_repo = ConversationRepository(db)
    conversation = await require_user_conversation(conv_repo, thread_id, str(user.id))

    runtime_context = await _resolve_filesystem_context(
        db=db,
        user=user,
        agent_id=agent_id or conversation.agent_id,
        agent_config_id=agent_config_id,
    )
    runtime_context.thread_id = thread_id
    runtime_context.user_id = str(user.id)
    await resolve_visible_knowledge_bases_for_context(runtime_context)

    sandbox_backend = ProvisionerSandboxBackend(thread_id=thread_id, user_id=str(user.id))
    return conversation, runtime_context, sandbox_backend


async def list_filesystem_entries_view(
    *,
    thread_id: str,
    path: str,
    agent_id: str | None,
    agent_config_id: int | None,
    current_user: User,
    db: AsyncSession,
) -> dict:
    if not thread_id:
        raise HTTPException(status_code=422, detail="thread_id 不能为空")

    normalized_path = (path or "/").strip() or "/"

    _conversation, runtime_context = await _resolve_filesystem_state(
        thread_id=thread_id,
        user=current_user,
        db=db,
        agent_id=agent_id,
        agent_config_id=agent_config_id,
    )

    runtime_stub = type("RuntimeStub", (), {"context": runtime_context})()
    composite_backend = create_agent_composite_backend(runtime_stub)
    try:
        entries = await asyncio.to_thread(composite_backend.ls_info, normalized_path)
    except PermissionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return {"entries": entries or []}


async def read_file_content_view(
    *,
    thread_id: str,
    path: str,
    agent_id: str | None,
    agent_config_id: int | None,
    current_user: User,
    db: AsyncSession,
) -> dict:
    if not thread_id:
        raise HTTPException(status_code=422, detail="thread_id 不能为空")
    if not path:
        raise HTTPException(status_code=422, detail="path 不能为空")

    normalized_path = path.strip()

    _conversation, runtime_context = await _resolve_filesystem_state(
        thread_id=thread_id,
        user=current_user,
        db=db,
        agent_id=agent_id,
        agent_config_id=agent_config_id,
    )

    runtime_stub = type("RuntimeStub", (), {"context": runtime_context})()
    composite_backend = create_agent_composite_backend(runtime_stub)
    try:
        responses = await asyncio.to_thread(composite_backend.download_files, [normalized_path])
    except PermissionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    response = responses[0] if responses else None
    if response is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    if response.error == "file_not_found":
        raise HTTPException(status_code=404, detail="文件不存在")
    if response.error == "is_directory":
        raise HTTPException(status_code=400, detail="当前路径是目录")
    if response.error == "read_failed":
        raise HTTPException(status_code=400, detail="文件读取失败")
    if response.error:
        raise HTTPException(status_code=400, detail=response.error)

    raw_content = response.content or b""
    if _looks_like_binary(raw_content):
        raise HTTPException(status_code=400, detail="当前文件是二进制文件，不能按文本读取")
    try:
        content = raw_content.decode("utf-8")
    except UnicodeDecodeError:
        content = raw_content.decode("utf-8", errors="replace")

    return {"content": content}
