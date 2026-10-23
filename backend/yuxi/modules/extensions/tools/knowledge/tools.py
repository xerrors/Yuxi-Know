"""知识库工具模块"""

from typing import Any

from langgraph.prebuilt.tool_node import ToolRuntime
from pydantic import BaseModel, Field

from yuxi.modules.extensions.tools.knowledge.client import INTERNAL_KNOWLEDGE_MCP, KnowledgeMCPUnavailable, call_knowledge_mcp
from yuxi.modules.extensions.tools.registry import tool
from yuxi.modules.knowledge.schemas import FindInputSchema, OpenInputSchema, SearchFileInput, SearchInputSchema

# ========== 通用知识库工具 ==========


def get_common_kb_tools() -> list:
    """获取通用知识库工具列表

    返回 5 个通用工具：
    - list_kbs: 列出用户可访问的知识库
    - query_kb: 在指定知识库中检索
    - find_kb_document: 在指定文件内定位关键词或正则模式
    - open_kb_document: 按 file_id 分段打开知识库文档
    - search_file: 搜索知识库中的文件
    """
    return [
        list_kbs,
        query_kb,
        find_kb_document,
        open_kb_document,
        search_file,
    ]


class ListKBsInput(BaseModel):
    """列出用户可访问的知识库输入模型"""

    # Langchain 的 runtime 注入机制要求必须有参数
    dummy: str = Field(default="", description="Dummy parameter - ignore")


@tool(category="knowledge", tags=["知识库"], display_name="列出知识库", args_schema=ListKBsInput)
async def list_kbs(dummy: str, runtime: ToolRuntime) -> str:
    """列出当前用户可访问的知识库列表

    返回用户基于权限可访问的知识库名称列表。这个列表是根据用户的角色和部门信息过滤后的结果，
    但不包括用户在当前对话中未启用的知识库。

    Returns:
        用户可访问的知识库名称列表（字符串格式）
    """
    result = await _call_knowledge_tool(runtime, "list_kbs", {})
    return "当前没有可访问的知识库" if result == [] else result


QueryKBInput = SearchInputSchema


@tool(category="knowledge", tags=["知识库"], display_name="检索知识库", args_schema=QueryKBInput)
async def query_kb(kb_id: str, query_text: str, file_name: str | None = None, runtime: ToolRuntime = None) -> Any:
    """在指定知识库中检索内容

    当用户需要查询具体内容时使用此工具。kb_id 是知识库资源 ID，也就是 kb_id；返回结果中的
    file_id 可继续用于 find_kb_document 或 open_kb_document。
    """
    return await _call_knowledge_tool(runtime, "query_kb", {"kb_id": kb_id, "query_text": query_text, "file_name": file_name})


OpenKBDocumentInput = OpenInputSchema


@tool(category="knowledge", tags=["知识库"], display_name="打开知识库文档", args_schema=OpenKBDocumentInput)
async def open_kb_document(
    kb_id: str,
    file_id: str,
    line: int | None = None,
    offset: int | None = None,
    window_size: int = 1800,
    runtime: ToolRuntime = None,
) -> dict[str, Any] | str:
    """按行窗口打开知识库文档原文

    当 query_kb 返回的片段不足以回答问题，或需要查看某个文档的上下文时使用。
    kb_id 是知识库资源 ID，也就是 kb_id；file_id 是知识库文件 ID。
    """
    return await _call_knowledge_tool(
        runtime, "open_kb_document", {"kb_id": kb_id, "file_id": file_id, "line": line, "offset": offset, "window_size": window_size}
    )


FindKBDocumentInput = FindInputSchema


@tool(category="knowledge", tags=["知识库"], display_name="定位文档内容", args_schema=FindKBDocumentInput)
async def find_kb_document(
    kb_id: str,
    file_id: str,
    patterns: list[str],
    use_regex: bool = False,
    case_sensitive: bool = False,
    max_windows: int = 5,
    window_size: int = 80,
    runtime: ToolRuntime = None,
) -> dict[str, Any] | str:
    """在已知知识库文件内做关键词或正则定位。

    当 query_kb 已找到候选文件，但需要在该文件内定位术语、指标、章节或实体时使用。
    """
    return await _call_knowledge_tool(
        runtime,
        "find_kb_document",
        {
            "kb_id": kb_id,
            "file_id": file_id,
            "patterns": patterns,
            "use_regex": use_regex,
            "case_sensitive": case_sensitive,
            "max_windows": max_windows,
            "window_size": window_size,
        },
    )


@tool(category="knowledge", tags=["知识库"], display_name="搜索知识库文件", args_schema=SearchFileInput)
async def search_file(
    kb_name: str | None = None,
    query: str | None = None,
    offset: int = 0,
    limit: int = 300,
    runtime: ToolRuntime = None,
    kb_id: str | None = None,
) -> dict[str, Any] | str:
    """搜索知识库中的文件

    当用户需要查找特定文件时使用此工具。用户指定知识库时，每次调用均传入该库的 kb_id，
    包括后续换关键词的搜索；从 list_kbs 返回结果获取 ID，不根据名称猜测。
    仅在用户未限定知识库或明确需要跨库查找时，省略知识库条件，搜索所有可访问的知识库。
    如果不指定搜索关键词，将返回所有文件。

    Args:
        kb_id: 知识库资源 ID；与名称同时指定时需同时匹配
        kb_name: 知识库名称，为空时按 ID 或关键词搜索
        query: 搜索关键词，为空时返回所有文件
        offset: 偏移量，从 0 开始
        limit: 返回数量限制，默认 300

    Returns:
        匹配的文件列表和分页信息
    """
    return await _call_knowledge_tool(
        runtime, "search_file", {"kb_id": kb_id, "kb_name": kb_name, "query": query, "offset": offset, "limit": limit}
    )


# ========== 共享 helper（细节层） ==========


async def _call_knowledge_tool(runtime: ToolRuntime | None, name: str, arguments: dict[str, Any]) -> Any:
    """只从可信上下文取得委托身份，失败进入现有 MCP 能力提示。"""
    context = getattr(runtime, "context", None)
    uid = getattr(context, "uid", None)
    if not uid:
        return "无法获取用户信息"
    unavailable = getattr(context, "mcp_unavailable", None)
    try:
        result = await call_knowledge_mcp(
            name,
            arguments,
            uid=uid,
            selection=getattr(context, "knowledges", []),
            run_id=getattr(context, "run_id", None),
        )
    except KnowledgeMCPUnavailable as exc:
        if unavailable is not None:
            unavailable[INTERNAL_KNOWLEDGE_MCP] = str(exc)
        raise
    if unavailable is not None:
        unavailable.pop(INTERNAL_KNOWLEDGE_MCP, None)
    return result
