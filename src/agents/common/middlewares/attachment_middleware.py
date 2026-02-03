"""附件注入中间件 - 使用 LangChain 标准中间件实现

支持两种模式：
1. MinIO 模式（默认）：将附件保存到 MinIO 存储，提示模型自主读取
2. 文件系统模式（已废弃）：将附件保存到本地文件系统
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import NotRequired

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from src.agents.common.backends.minio_backend import MinIOBackend
from src.utils import logger


class AttachmentState(AgentState):
    """扩展 AgentState 以支持附件"""

    attachments: NotRequired[list[dict]]


def _build_attachment_prompt(attachments: Sequence[dict], thread_id: str) -> str | None:
    """Render attachments into a system prompt block with file paths.

    提示模型使用 read_file 工具读取附件内容。
    """
    if not attachments:
        return None

    valid_attachments = [a for a in attachments if a.get("status") == "parsed" and a.get("markdown")]

    if not valid_attachments:
        return None

    attachment_infos: list[str] = []
    for idx, attachment in enumerate(valid_attachments, 1):
        file_id = attachment.get("file_id", f"file_{idx}")
        file_name = attachment.get("file_name") or f"附件 {idx}"
        truncated = "（已截断）" if attachment.get("truncated") else ""

        file_path = f"{thread_id}/{file_id}.md"
        attachment_infos.append(f"- {file_name}{truncated}: /attachments/{file_path}")

    lines = [
        "用户上传了以下附件，已保存到文件系统中：",
        "",
        *attachment_infos,
        "",
        "请使用 read_file 工具读取附件内容后，再回答用户的问题。如果附件与问题无关，可以忽略附件内容。",
    ]

    return "\n".join(lines)


class AttachmentMiddleware(AgentMiddleware[AttachmentState]):
    """
    LangChain 标准中间件：从 State 中读取附件并注入到消息中。

    根据官方文档示例：
    https://docs.langchain.com/oss/python/langchain/middleware

    从 request.state 中读取 attachments，将其转换为 SystemMessage 并注入到消息列表开头。

    NOTE: 缺点是无法命中缓存了
    """

    state_schema = AttachmentState

    async def awrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        # Read from State: get uploaded files metadata
        # 首先尝试从 state 获取，如果为空则从 input_context 获取
        attachments = request.state.get("attachments", [])

        # 如果 state 中没有，尝试从 input_context 获取
        if not attachments:
            input_context = request.state.get("input_context", {})
            attachments = input_context.get("attachments", [])

        logger.info(f"AttachmentMiddleware: request.state keys = {list(request.state.keys())}")
        logger.info(f"AttachmentMiddleware: found {len(attachments)} attachments in state")

        # 尝试从输入中获取 attachments（LangGraph 会将输入 state 合并）
        if not attachments:
            # 检查是否有其他方式传递的附件
            logger.info("AttachmentMiddleware: checking for attachments in other locations...")
            # 输入可能直接在 state 中
            logger.info(f"AttachmentMiddleware: state type = {type(request.state)}")

        if attachments:
            # Get thread_id - 尝试从多个来源获取
            thread_id = None

            # 0. 尝试从 request.runtime 获取（LangChain runtime）
            if hasattr(request, "runtime") and request.runtime:
                runtime = request.runtime
                logger.info(f"AttachmentMiddleware: runtime type = {type(runtime)}")
                logger.info(
                    f"AttachmentMiddleware: runtime attrs = {[a for a in dir(runtime) if not a.startswith('_')]}"
                )

                # 检查 runtime.context
                if hasattr(runtime, "context") and runtime.context:
                    ctx = runtime.context
                    logger.info(f"AttachmentMiddleware: runtime.context type = {type(ctx)}")
                    # 如果是 Pydantic 模型，使用 model_dump()
                    if hasattr(ctx, "model_dump"):
                        ctx_dict = ctx.model_dump()
                        logger.info(f"AttachmentMiddleware: runtime.context keys = {list(ctx_dict.keys())}")
                        thread_id = ctx_dict.get("thread_id")
                    elif hasattr(ctx, "__dict__"):
                        logger.info(f"AttachmentMiddleware: runtime.context __dict__ = {ctx.__dict__}")
                        thread_id = ctx.__dict__.get("thread_id")
                    elif isinstance(ctx, dict):
                        logger.info(f"AttachmentMiddleware: runtime.context keys = {list(ctx.keys())}")
                        thread_id = ctx.get("thread_id")

                # 如果还没有 thread_id，检查 runtime 其他属性
                if not thread_id:
                    for attr in ["state", "config", "configurable"]:
                        if hasattr(runtime, attr):
                            val = getattr(runtime, attr)
                            logger.info(f"AttachmentMiddleware: runtime.{attr} = {type(val)}")
                            if isinstance(val, dict):
                                thread_id = val.get("thread_id")
                            elif hasattr(val, "get"):
                                thread_id = val.get("thread_id")
                            if thread_id:
                                break

            # 1. 尝试从 state 获取
            if not thread_id:
                thread_id = request.state.get("thread_id")

            # 2. 尝试从 configurable 获取（LangGraph checkpointer 存储方式）
            if not thread_id:
                configurable = request.state.get("configurable", {})
                if isinstance(configurable, dict):
                    thread_id = configurable.get("thread_id")

            # 3. 尝试从 input_context 获取（如果存在）
            if not thread_id:
                input_context = request.state.get("input_context")
                if input_context is not None:
                    if isinstance(input_context, dict):
                        thread_id = input_context.get("thread_id")
                    elif hasattr(input_context, "thread_id"):
                        thread_id = getattr(input_context, "thread_id", None)

            logger.info(f"AttachmentMiddleware: thread_id = {thread_id}")
            logger.info(f"AttachmentMiddleware: has config = {hasattr(request, 'config')}")
            logger.info(f"AttachmentMiddleware: state keys = {list(request.state.keys())}")

            if not thread_id:
                logger.error(f"AttachmentMiddleware: thread_id not found. input_context type = {type(input_context)}")
                logger.error(f"AttachmentMiddleware: request.state = {dict(request.state)}")

            if not thread_id:
                raise ValueError(
                    "AttachmentMiddleware requires thread_id in input_context. "
                    "Please ensure the conversation has a valid thread_id."
                )

            # Save attachments to filesystem
            attachment_paths = await _save_attachments_to_fs(attachments, thread_id)

            # Build attachment prompt with file paths
            attachment_prompt = _build_attachment_prompt(attachments, thread_id)

            if attachment_prompt:
                logger.info(f"Saved {len(attachment_paths)} attachments to /attachments/{thread_id}/")

                messages = list(request.messages)
                insert_idx = 0
                for idx, msg in enumerate(messages):
                    if isinstance(msg, dict):
                        role = msg.get("role") or msg.get("type")
                        is_system = role == "system"
                    else:
                        msg_type = getattr(msg, "type", None) or getattr(msg, "role", None)
                        is_system = msg_type == "system"

                    if not is_system:
                        break
                    insert_idx = idx + 1

                messages.insert(insert_idx, {"role": "system", "content": attachment_prompt})
                request = request.override(messages=messages)

        return await handler(request)


async def _save_attachments_to_fs(attachments: Sequence[dict], thread_id: str) -> list[str]:
    """Save attachment markdown content to MinIO using MinIOBackend.

    保存路径: /attachments/{thread_id}/{original_file_name}.md (使用原始文件名)
    实际存储: attachments/{thread_id}/{original_file_name}.md (MinIO key)

    使用 MinIOBackend 确保 read_file 工具能够读取这些文件。

    Returns:
        list of saved file paths (relative to /attachments/)
    """
    backend = MinIOBackend(bucket_name="chat-attachments")

    saved_paths: list[str] = []

    for attachment in attachments:
        if attachment.get("status") != "parsed":
            continue

        file_id = attachment.get("file_id")
        file_name = attachment.get("file_name")
        markdown = attachment.get("markdown")

        if not file_id or not file_name or not markdown:
            continue

        # 确保文件名安全：移除路径分隔符，保留原始扩展名
        safe_file_name = file_name.replace("/", "_").replace("\\", "_")
        file_path = f"/attachments/{thread_id}/{safe_file_name}"
        result = backend.write(file_path, markdown)
        if not result.error:
            saved_paths.append(file_path)
            logger.info(f"Saved attachment to MinIO: {file_path}")
        else:
            logger.error(f"Failed to save attachment: {result.error}")

    return saved_paths


# 创建中间件实例，供其他模块使用
# 新的文件系统模式中间件：保存附件到文件系统，提示模型自主读取
save_attachments_to_fs = AttachmentMiddleware()

# 保留旧名称以保持向后兼容（已废弃）
inject_attachment_context = save_attachments_to_fs
