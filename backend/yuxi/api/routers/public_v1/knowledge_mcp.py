"""将知识库 MCP 服务装配到 API 身份边界。"""

from fastapi import HTTPException
from starlette.responses import JSONResponse

from yuxi.api.dependencies.auth import get_current_user, get_required_user
from yuxi.modules.knowledge.mcp.server import KnowledgeMCP


def create_knowledge_mcp() -> KnowledgeMCP:
    """以产品 API Key 认证规则装配知识库 MCP 服务。"""
    return KnowledgeMCP(authenticate_api_key=_authenticate_api_key)


async def _authenticate_api_key(request, authorization, db):
    """沿用 API Key 的权限级别、部门约束和使用时间记录。"""
    try:
        return await get_required_user(await get_current_user(request, authorization, db))
    except HTTPException as exc:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
