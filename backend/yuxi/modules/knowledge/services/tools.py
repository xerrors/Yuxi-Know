"""Knowledge MCP 与 Public API 共用的知识库查询工具用例。"""

from __future__ import annotations

from typing import Any

from yuxi.modules.knowledge.runtime import knowledge_base


class KnowledgeToolError(ValueError):
    """表示工具输入或知识库可见性不满足调用条件。"""

    def __init__(self, message: str, *, not_found: bool = False) -> None:
        super().__init__(message)
        self.not_found = not_found


def list_kbs(visible_kbs: list[dict[str, Any]], *, include_capabilities: bool = False) -> list[dict[str, Any]]:
    """列出可见知识库的工具展示字段。"""
    result = []
    for kb in visible_kbs:
        item = {
            "kb_id": kb.get("kb_id"),
            "name": kb.get("name", ""),
            "description": kb.get("description") or "无描述",
        }
        if include_capabilities:
            item["supports_documents"] = knowledge_base.knowledge_base_type_supports_documents(kb.get("kb_type"))
        result.append(item)
    return result


def require_visible_kb(kb_id: str, visible_kbs: list[dict[str, Any]]) -> str:
    """在当前可见集合中验证知识库 ID。"""
    if not visible_kbs:
        raise KnowledgeToolError("无法获取当前会话可访问的知识库", not_found=True)
    normalized = str(kb_id or "").strip()
    if normalized not in {str(kb.get("kb_id") or "").strip() for kb in visible_kbs}:
        raise KnowledgeToolError(f"知识库资源 '{normalized}' 不存在或当前会话未启用", not_found=True)
    return normalized


async def query_kb(
    kb_id: str,
    query_text: str,
    visible_kbs: list[dict[str, Any]],
    *,
    file_name: str | None = None,
    kb_service: Any = None,
) -> Any:
    """在可见知识库中检索结构化片段。"""
    if not kb_id:
        raise KnowledgeToolError("请提供 kb_id")
    if not query_text:
        raise KnowledgeToolError("请提供查询内容")
    target = require_visible_kb(kb_id, visible_kbs)
    options = {"file_name": file_name} if file_name else {}
    return await (kb_service or knowledge_base).retrieve(target, query_text, **options)


async def open_kb_document(
    kb_id: str,
    file_id: str,
    visible_kbs: list[dict[str, Any]],
    *,
    line: int | None = None,
    offset: int | None = None,
    window_size: int = 1800,
    kb_service: Any = None,
) -> Any:
    """按行窗口打开可见知识库的文档。"""
    if not str(kb_id or "").strip():
        raise KnowledgeToolError("请提供 kb_id")
    if not str(file_id or "").strip():
        raise KnowledgeToolError("请提供 file_id")
    target = require_visible_kb(kb_id, visible_kbs)
    start = int(line) - 1 if line is not None else int(offset or 0)
    return await (kb_service or knowledge_base).open_document(
        target,
        str(file_id).strip(),
        offset=start,
        limit=window_size,
    )


async def find_kb_document(
    kb_id: str,
    file_id: str,
    patterns: list[str],
    visible_kbs: list[dict[str, Any]],
    *,
    use_regex: bool = False,
    case_sensitive: bool = False,
    max_windows: int = 5,
    window_size: int = 80,
    kb_service: Any = None,
) -> Any:
    """在可见知识库的指定文件中定位内容。"""
    if not str(kb_id or "").strip():
        raise KnowledgeToolError("请提供 kb_id")
    if not str(file_id or "").strip():
        raise KnowledgeToolError("请提供 file_id")
    if not patterns:
        raise KnowledgeToolError("请提供 patterns")
    target = require_visible_kb(kb_id, visible_kbs)
    return await (kb_service or knowledge_base).find_in_document(
        target,
        str(file_id).strip(),
        patterns,
        use_regex=use_regex,
        case_sensitive=case_sensitive,
        max_windows=max_windows,
        window_size=window_size,
    )


async def search_file(
    visible_kbs: list[dict[str, Any]],
    *,
    kb_id: str | None = None,
    kb_name: str | None = None,
    query: str | None = None,
    offset: int = 0,
    limit: int = 300,
    kb_service: Any = None,
) -> Any:
    """按可见范围和文件名搜索知识库文件。"""
    if not kb_id and not kb_name and not query:
        raise KnowledgeToolError("请提供知识库 ID、名称或搜索关键词，不能同时为空")
    if not visible_kbs:
        raise KnowledgeToolError("无法获取当前会话可访问的知识库", not_found=True)
    target_kbs = visible_kbs
    if kb_id:
        target = require_visible_kb(kb_id, visible_kbs)
        target_kbs = [kb for kb in target_kbs if kb.get("kb_id") == target]
    if kb_name:
        target_kbs = [kb for kb in target_kbs if kb.get("name") == kb_name]
        if not target_kbs:
            raise KnowledgeToolError(f"知识库 '{kb_name}' 不存在或当前会话未启用", not_found=True)
    service = kb_service or knowledge_base
    searchable = [kb for kb in target_kbs if service.knowledge_base_type_supports_documents(kb.get("kb_type"))]
    if not searchable:
        raise KnowledgeToolError("当前匹配的知识库只支持检索，不支持文件搜索")
    return await service.search_document_files(searchable, query=query, offset=offset, limit=limit)
