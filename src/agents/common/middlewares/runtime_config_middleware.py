from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from src import knowledge_base
from src.agents.common import load_chat_model
from src.agents.common.tools import get_tools_from_context


def _is_system_message(msg: Any) -> bool:
    if isinstance(msg, dict):
        role = msg.get("role") or msg.get("type")
        return role == "system"
    msg_type = getattr(msg, "type", None) or getattr(msg, "role", None)
    return msg_type == "system"


def _get_message_content(msg: Any) -> str | None:
    if isinstance(msg, dict):
        content = msg.get("content")
        return str(content) if content is not None else None
    content = getattr(msg, "content", None)
    return str(content) if content is not None else None


class RuntimeConfigMiddleware(AgentMiddleware):
    async def awrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        # 虽然功能实现了， 但是总感觉怪怪的 TODO 优化下
        runtime_context = request.runtime.context

        effective_context = runtime_context
        blocked_knowledges: list[str] = []
        requested_knowledges = getattr(runtime_context, "knowledges", None)
        department_id = getattr(runtime_context, "department_id", None)

        if department_id and isinstance(requested_knowledges, list) and requested_knowledges:
            user_info = {"role": "user", "department_id": department_id}
            accessible_databases = await knowledge_base.get_databases_by_user(user_info)
            accessible_kb_names = {
                db.get("name")
                for db in accessible_databases.get("databases", [])
                if isinstance(db, dict) and db.get("name")
            }
            filtered_knowledges = [kb for kb in requested_knowledges if kb in accessible_kb_names]
            blocked_knowledges = [kb for kb in requested_knowledges if kb not in accessible_kb_names]
            if blocked_knowledges:
                effective_context = replace(runtime_context)
                effective_context.knowledges = filtered_knowledges

        model = load_chat_model(getattr(runtime_context, "model", None))
        tools = await get_tools_from_context(effective_context)

        system_prompt = getattr(runtime_context, "system_prompt", None)
        notice = None
        if blocked_knowledges:
            notice = f"注意：已自动过滤无权访问的知识库：{', '.join(blocked_knowledges)}"

        existing_systems: list[Any] = []
        remaining: list[Any] = []
        in_prefix = True
        for msg in request.messages:
            if in_prefix and _is_system_message(msg):
                existing_systems.append(msg)
            else:
                in_prefix = False
                remaining.append(msg)

        existing_contents = [_get_message_content(m) for m in existing_systems]

        new_systems: list[Any] = []
        if system_prompt:
            try:
                idx = existing_contents.index(system_prompt)
            except ValueError:
                new_systems.append({"role": "system", "content": system_prompt})
            else:
                new_systems.append(existing_systems.pop(idx))
                existing_contents.pop(idx)

        if notice and notice not in existing_contents:
            new_systems.append({"role": "system", "content": notice})

        messages = [*new_systems, *existing_systems, *remaining]

        request = request.override(model=model, tools=tools, messages=messages)
        return await handler(request)
