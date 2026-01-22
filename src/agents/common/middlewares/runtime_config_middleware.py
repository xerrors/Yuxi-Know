from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from src.agents.common import load_chat_model
from src.agents.common.tools import get_kb_based_tools
from src.services.mcp_service import get_enabled_mcp_tools
from src.utils.logging_config import logger


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
    """运行时配置中间件 - 应用模型/工具/知识库/MCP/提示词配置

    注意：所有可能用到的知识库工具必须在初始化时预加载并注册到 self.tools
    运行时根据配置从 self.tools 中筛选工具，不能动态添加新工具
    """

    def __init__(self, *, extra_tools: list[Any] | None = None):
        """初始化中间件

        Args:
            extra_tools: 额外工具列表（从 create_agent 的 tools 参数传入）
        """
        super().__init__()
        # 这里的工具只是提供给 langchain 调用，并不是真正的绑定在模型上
        self.kb_tools = get_kb_based_tools()
        self.tools = self.kb_tools + (extra_tools or [])
        logger.debug(f"Initialized tools: {len(self.tools)}")

    async def awrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        runtime_context = request.runtime.context

        model = load_chat_model(getattr(runtime_context, "model", None))
        enabled_tools = await self.get_tools_from_context(runtime_context)
        system_prompt = getattr(runtime_context, "system_prompt", None)

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

        messages = [*new_systems, *existing_systems, *remaining]

        request = request.override(model=model, tools=enabled_tools, messages=messages)
        return await handler(request)

    async def get_tools_from_context(self, context) -> list:
        """从上下文配置中获取工具列表"""
        # 1. 基础工具 (从 context.tools 中筛选)
        selected_tools = []

        if context.tools:
            # 创建工具映射表
            tools_map = {t.name: t for t in self.tools}
            for tool_name in context.tools:
                if tool_name in tools_map:
                    selected_tools.append(tools_map[tool_name])

        # 2. 知识库工具
        if context.knowledges:
            kb_tools = get_kb_based_tools(db_names=context.knowledges)
            selected_tools.extend(kb_tools)

        # 3. MCP 工具（使用统一入口，自动过滤 disabled_tools）
        if context.mcps:
            for server_name in context.mcps:
                mcp_tools = await get_enabled_mcp_tools(server_name)
                selected_tools.extend(mcp_tools)

        return selected_tools
