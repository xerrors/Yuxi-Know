"""Agent 的知识库数据边界：只通过平台 HTTP MCP 读取。"""

import asyncio
import os
from datetime import timedelta
from typing import Any

import httpx
from langchain_core.tools import ToolException
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from yuxi.infrastructure.observability.logging import logger
from yuxi.modules.extensions.mcp.service import runtime_mcp_failure_message
from yuxi.modules.identity.security import create_knowledge_token

INTERNAL_KNOWLEDGE_MCP = "platform:knowledge"
KNOWLEDGE_MCP_TIMEOUT_SECONDS = 120


class KnowledgeMCPError(ToolException):
    """仅包含 MCP 边界允许公开的失败提示。"""


class KnowledgeMCPUnavailable(KnowledgeMCPError):
    """连接、认证或服务故障使本次运行的知识能力不可用。"""


async def call_knowledge_mcp(
    name: str,
    arguments: dict[str, Any],
    *,
    uid: str,
    selection: str | list[str],
    run_id: str | None = None,
) -> Any:
    """握手并执行真实 MCP 工具，保持原有结构化结果形状。"""
    try:
        async with (
            asyncio.timeout(KNOWLEDGE_MCP_TIMEOUT_SECONDS),
            httpx.AsyncClient(
                auth=_KnowledgeDelegationAuth(uid, selection, run_id),
                timeout=httpx.Timeout(KNOWLEDGE_MCP_TIMEOUT_SECONDS, connect=5),
                follow_redirects=False,
                trust_env=False,
            ) as http_client,
            streamable_http_client(os.environ.get("YUXI_KNOWLEDGE_MCP_URL", "http://api:5050/api/mcp"), http_client=http_client) as (
                read,
                write,
                _,
            ),
            ClientSession(read, write, read_timeout_seconds=timedelta(seconds=KNOWLEDGE_MCP_TIMEOUT_SECONDS)) as session,
        ):
            await session.initialize()
            result = await session.call_tool(name, arguments)
        if result.isError:
            # 此服务公开的工具错误只含固定指导语，不转发第三方任意异常。
            raise KnowledgeMCPError("\n".join(item.text for item in result.content if item.type == "text"))
        payload = result.structuredContent
        if not isinstance(payload, dict):
            raise KnowledgeMCPError("知识库 MCP 返回了无效结果")
        if name == "list_kbs":
            return payload["knowledge_bases"]
        return payload
    except KnowledgeMCPError:
        raise
    except Exception as exc:
        logger.bind(component="knowledge_mcp", server_slug=INTERNAL_KNOWLEDGE_MCP, error_type=type(exc).__name__, available=False).warning(
            "Knowledge MCP unavailable: error_type={}", type(exc).__name__
        )
        raise KnowledgeMCPUnavailable(f"知识库 MCP 不可用：{runtime_mcp_failure_message(exc)}") from exc


async def list_knowledge_bases(uid: str, *, selection: str | list[str] = "all") -> list[dict[str, Any]]:
    """资源选择器和引用过滤也通过 MCP 读取当前权限摘要。"""
    return await call_knowledge_mcp("list_kbs", {"include_capabilities": True}, uid=uid, selection=selection)


class _KnowledgeDelegationAuth(httpx.Auth):
    """每次 HTTP 出站使用可信身份重新签发短期委托。"""

    def __init__(self, uid: str, selection: str | list[str], run_id: str | None):
        """绑定本次调用的可信用户与会话范围。"""
        self.uid, self.selection, self.run_id = uid, selection, run_id

    async def async_auth_flow(self, request):
        """委托凭据不进入模型参数、持久化工具结果或全局缓存。"""
        request.headers["Authorization"] = "Bearer " + create_knowledge_token(uid=self.uid, selection=self.selection, run_id=self.run_id)
        yield request
