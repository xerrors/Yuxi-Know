"""
Common utilities and base classes for agents.

This module provides a unified namespace for commonly used base classes and utilities,
allowing simplified imports like:
    from src.agents.common import BaseAgent, BaseContext, BaseState

For other specific functions, use the original import style:
    from src.agents.common.tools import query_knowledge_graph
    from src.agents.common.mcp import MCP_SERVERS
"""

# Base classes - 核心基类
from src.agents.common.base import BaseAgent
from src.agents.common.context import BaseContext

# MCP - 核心 MCP 函数
from src.agents.common.mcp import get_mcp_tools

# Model utilities - 模型加载
from src.agents.common.models import load_chat_model
from src.agents.common.state import BaseState

# Tools - 核心工具函数
from src.agents.common.tools import gen_tool_info, get_buildin_tools

__all__ = [
    # Base classes
    "BaseAgent",
    "BaseContext",
    "BaseState",
    # Model utilities
    "load_chat_model",
    # Core tools
    "get_buildin_tools",
    "gen_tool_info",
    # Core MCP
    "get_mcp_tools",
]
