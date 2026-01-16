from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from src.services.mcp_service import get_mcp_tools
from src.utils import logger


class DynamicToolMiddleware(AgentMiddleware):
    """动态工具选择中间件 - 支持 MCP 工具的动态加载和注册

    注意：所有可能用到的 MCP 工具必须在初始化时预加载并注册到 self.tools
    运行时只是根据配置筛选工具，不能动态添加新工具
    """

    def __init__(
        self,
        base_tools: list[Any],
        mcp_servers: list[str] | None = None,
        basic_tools: list[Any] | None = None,
        kb_tools: list[Any] | None = None,
        mcp_tools: list[Any] | None = None,
    ):
        """初始化中间件

        Args:
            base_tools: 基础工具列表
            mcp_servers: 需要预加载的 MCP 服务器列表（可选）
        """
        super().__init__()
        self.tools: list[Any] = base_tools
        self._all_mcp_tools: dict[str, list[Any]] = {}  # 所有已加载的 MCP 工具
        self._mcp_servers = mcp_servers or []

        self.basic_tools: list[Any] = basic_tools or []  # 基础工具
        self.kb_tools: list[Any] = kb_tools or []  # 基于知识库的工具
        self.mcp_tools: list[Any] = mcp_tools or []  # 基于MCP的工具

    async def initialize_mcp_tools(self) -> None:
        """异步初始化：预加载所有可能用到的 MCP 工具"""
        for mcp_name in self._mcp_servers:
            if mcp_name not in self._all_mcp_tools:
                logger.info(f"Pre-loading MCP tools from: {mcp_name}")
                mcp_tools = await get_mcp_tools(mcp_name)
                self._all_mcp_tools[mcp_name] = mcp_tools
                # 将 MCP 工具注册到 middleware.tools
                self.tools.extend(mcp_tools)
                logger.info(f"Registered {len(mcp_tools)} tools from {mcp_name}")

    async def awrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        """根据配置动态选择工具（从已注册的工具中筛选）"""
        # 从 runtime context 获取配置
        selected_tools = getattr(request.runtime.context, "tools", [])
        selected_mcp_tools = getattr(request.runtime.context, "user_mcp_tools", [])
        selected_knowledges = getattr(request.runtime.context, "user_knowledges", [])

        enabled_tools = []

        # 根据配置筛选基础工具
        if selected_tools and isinstance(selected_tools, list) and len(selected_tools) > 0:
            enabled_tools = [tool for tool in self.basic_tools if tool.name in selected_tools]

        # 根据配置筛选 MCP 工具（从已注册的工具中选择）
        if selected_mcp_tools and isinstance(selected_mcp_tools, list) and len(selected_mcp_tools) > 0:
            mcp_tools_from_selected = [tool for tool in self.mcp_tools if tool.metadata["id"] in selected_mcp_tools]
            enabled_tools.extend(mcp_tools_from_selected)
        else:
            enabled_tools.extend(self.mcp_tools)

        # 筛选知识工具
        if selected_knowledges and isinstance(selected_knowledges, list) and len(selected_knowledges) > 0:
            knowledge_tools_from_selected = [tool for tool in self.kb_tools if tool.name in selected_knowledges]
            enabled_tools.extend(knowledge_tools_from_selected)
        else:
            enabled_tools.extend(self.kb_tools)

        logger.info(
            f"Dynamic tool selection: {len(enabled_tools)} tools enabled: {[tool.name for tool in enabled_tools]}, "
            f"selected_tools: {selected_tools}, "
            f"selected_mcp_tools: {selected_mcp_tools}, "
            f"selected_knowledges: {selected_knowledges}"
        )

        # 更新 request 中的工具列表
        request = request.override(tools=enabled_tools)
        return await handler(request)
