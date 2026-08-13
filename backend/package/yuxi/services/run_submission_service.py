"""统一的 AgentRun 消息提交应用服务。

Web Chat、Agent Call 和评估入口只在路由/适配层处理各自的输入输出协议，
实际的 AgentRunRequest 入队、Conversation 绑定和提交后派发都从这里进入。
Resume 与 Subagent 保留各自的特殊生命周期，不经过本服务。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from yuxi.agents.buildin import agent_manager
from yuxi.repositories.agent_repository import AgentRepository
from yuxi.repositories.agent_run_repository import AgentRunRepository
from yuxi.repositories.agent_run_request_repository import AgentRunRequestRepository
from yuxi.repositories.conversation_repository import ConversationRepository
from yuxi.services.agent_request_queue_service import finalize_intake, intake_request
from yuxi.services.input_message_service import AgentRunInputMessage
from yuxi.storage.postgres.models_business import User


@dataclass(frozen=True)
class RunOrigin:
    """描述一次 Run 请求的入口来源与传输通道。"""

    source: str
    channel: str
    external_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunSubmissionCommand:
    """统一的消息型 Run 提交命令。"""

    agent_slug: str
    thread_id: str
    request_id: str
    input_message: AgentRunInputMessage
    origin: RunOrigin
    request_metadata: dict[str, Any] = field(default_factory=dict)
    model_spec: str | None = None
    tool_approval_mode: str | None = None
    queue_policy: str = "enqueue"
    create_conversation: bool = False
    conversation_title: str | None = None
    agent_kind: str = "main"


async def submit_run_command(
    *,
    command: RunSubmissionCommand,
    current_user: User,
    db: AsyncSession,
) -> dict[str, Any]:
    """校验作用域、写入 Request 并在提交后投递消息型 AgentRun。

    ``create_conversation`` 仅用于没有显式 Thread 的外部入口；普通 Web Chat
    必须复用已经创建的 Conversation。不同入口的协议适配不应绕过这里。
    """

    origin = command.origin
    if not origin.source.strip() or not origin.channel.strip():
        raise HTTPException(status_code=422, detail="Run origin source/channel 不能为空")
    if len(origin.source) > 32:
        raise HTTPException(status_code=422, detail="Run origin source 不能超过 32 个字符")
    if len(origin.channel) > 32:
        raise HTTPException(status_code=422, detail="Run origin channel 不能超过 32 个字符")
    external_id = str(origin.external_id).strip() if origin.external_id is not None else None
    if external_id == "":
        external_id = None
    origin_metadata = {
        key: value for key, value in origin.metadata.items() if key not in {"source", "channel", "external_id"}
    }

    agent_repo = AgentRepository(db)
    agent_item = await agent_repo.get_visible_by_slug(
        slug=command.agent_slug,
        user=current_user,
        kind=command.agent_kind,
    )
    if not agent_item:
        raise HTTPException(status_code=404, detail="智能体不存在")

    existing_request = await AgentRunRequestRepository(db).get_by_request_id(command.request_id)
    existing_run = await AgentRunRepository(db).get_run_by_request_id(command.request_id)
    if existing_run and not existing_request:
        if existing_run.uid != str(current_user.uid):
            raise HTTPException(status_code=409, detail="request_id 冲突")
        if existing_run.agent_slug != agent_item.slug or existing_run.run_type != "chat":
            raise HTTPException(status_code=409, detail="request_id 冲突")
        if command.thread_id and existing_run.conversation_thread_id != command.thread_id:
            raise HTTPException(status_code=409, detail="request_id 冲突")
        return {
            "request_id": command.request_id,
            "status": existing_run.status,
            "queue_policy": command.queue_policy,
            "queue_position": 0,
            "message_id": existing_run.input_message_id,
            "run_id": existing_run.id,
            "stream_url": f"/api/agent/runs/{existing_run.id}/events",
            "request_events_url": None,
            "thread_id": existing_run.conversation_thread_id,
        }
    if existing_request and command.thread_id and existing_request.conversation_thread_id != command.thread_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "request_id_conflict", "message": "request_id 已用于其他请求作用域"},
        )

    agent_backend = agent_manager.get_agent(agent_item.backend_id)
    if not agent_backend:
        raise HTTPException(status_code=404, detail=f"智能体后端 {agent_item.backend_id} 不存在")

    conversation_repo = ConversationRepository(db)
    conversation = await conversation_repo.get_conversation_by_thread_id(command.thread_id)
    if not conversation:
        if not command.create_conversation:
            raise HTTPException(status_code=404, detail="对话线程不存在")
        try:
            async with db.begin_nested():
                conversation = await conversation_repo.add_conversation(
                    uid=str(current_user.uid),
                    agent_id=agent_item.slug,
                    title=command.conversation_title,
                    thread_id=command.thread_id,
                    metadata={
                        **origin_metadata,
                        "source": origin.source,
                        "channel": origin.channel,
                    },
                )
        except IntegrityError:
            conversation = await conversation_repo.get_conversation_by_thread_id(command.thread_id)
            if not conversation:
                raise

    request_metadata = dict(command.request_metadata or {})
    request_metadata["channel"] = origin.channel
    for key, value in origin_metadata.items():
        if key in {"source", "channel"}:
            continue
        request_metadata.setdefault(key, value)

    intake = await intake_request(
        db=db,
        request_id=command.request_id,
        uid=str(current_user.uid),
        agent_slug=agent_item.slug,
        thread_id=command.thread_id,
        source=origin.source,
        channel=origin.channel,
        external_id=external_id,
        origin_metadata=origin_metadata,
        queue_policy=command.queue_policy,
        input_message=command.input_message,
        agent_item=agent_item,
        agent_backend=agent_backend,
        model_spec=command.model_spec,
        tool_approval_mode=command.tool_approval_mode,
        meta=request_metadata,
    )
    await finalize_intake(db=db, intake=intake)

    return {
        "request_id": intake.request_id,
        "status": intake.status,
        "queue_policy": intake.queue_policy,
        "queue_position": intake.queue_position,
        "message_id": intake.message_id,
        "run_id": intake.run_id,
        "stream_url": f"/api/agent/runs/{intake.run_id}/events" if intake.run_id else None,
        "request_events_url": (
            f"/api/agent/requests/{intake.request_id}/events" if intake.status == "queued" else None
        ),
        "thread_id": intake.thread_id,
    }
