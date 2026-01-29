from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage

from src.agents.common import load_chat_model
from src.agents.common.tools import get_buildin_tools, get_kb_based_tools
from src.services.mcp_service import get_enabled_mcp_tools
from src.utils.datetime_utils import shanghai_now
from src.utils.logging_config import logger


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
        # 这里的工具只是提供给 langchain 调用，并不是真正的绑定在模型上（后续会过滤）
        self.kb_tools = get_kb_based_tools()
        self.buildin_tools = get_buildin_tools()
        self.tools = self.kb_tools + self.buildin_tools + (extra_tools or [])
        logger.debug(f"Initialized tools: {len(self.tools)}")

    async def awrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        runtime_context = request.runtime.context

        model = load_chat_model(getattr(runtime_context, "model", None))
        enabled_tools = await self.get_tools_from_context(runtime_context)
        existing_tools = list(request.tools or [])

        # 合并之前中间件设置的 tools，避免覆盖
        merged_tools = []
        for t_bind in existing_tools:
            if t_bind in enabled_tools or t_bind not in self.tools:
                merged_tools.append(t_bind)

        # 动态生成 system message，添加当前时间
        cur_datetime = f"当前时间：{shanghai_now().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        system_prompt = getattr(runtime_context, "system_prompt", "") or ""
        new_content = list(request.system_message.content_blocks) + [
            {"type": "text", "text": f"{cur_datetime}\n\n{system_prompt}"}
        ]
        new_system_message = SystemMessage(content=new_content)

        logger.debug(f"RuntimeConfigMiddleware: model={model}, tools={[t.name for t in merged_tools]}. ")

        request = request.override(model=model, tools=merged_tools, system_message=new_system_message)
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
                else:
                    logger.warning(f"Tool '{tool_name}' not found in available tools. {tools_map.keys()=}")

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
