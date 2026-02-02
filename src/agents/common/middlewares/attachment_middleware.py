"""附件注入中间件 - 使用 LangChain 标准中间件实现

支持两种模式：
1. 文件系统模式（默认）：将附件保存到 /attachments/{thread_id}/，提示模型自主读取
2. 内嵌模式（已废弃）：将附件内容直接拼接到消息中
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NotRequired

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from src.utils import logger

# 附件存储根目录
ATTACHMENTS_ROOT = Path("attachments")


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
        attachments = request.state.get("attachments", [])

        if attachments:
            # Get thread_id from input_context
            input_context = request.state.get("input_context", {})
            thread_id = input_context.get("thread_id")

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
                logger.debug(f"Saved {len(attachment_paths)} attachments to /attachments/{thread_id}/")

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
    """Save attachment markdown content to filesystem.

    保存路径: /attachments/{thread_id}/{file_id}.md

    Returns:
        list of saved file paths
    """
    # Ensure directory exists
    thread_dir = ATTACHMENTS_ROOT / thread_id
    thread_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: list[str] = []

    for attachment in attachments:
        if attachment.get("status") != "parsed":
            continue

        file_id = attachment.get("file_id")
        markdown = attachment.get("markdown")

        if not file_id or not markdown:
            continue

        file_path = thread_dir / f"{file_id}.md"
        file_path.write_text(markdown, encoding="utf-8")
        saved_paths.append(str(file_path))
        logger.debug(f"Saved attachment to {file_path}")

    return saved_paths


# 创建中间件实例，供其他模块使用
# 新的文件系统模式中间件：保存附件到文件系统，提示模型自主读取
save_attachments_to_fs = AttachmentMiddleware()

# 保留旧名称以保持向后兼容（已废弃）
inject_attachment_context = save_attachments_to_fs
