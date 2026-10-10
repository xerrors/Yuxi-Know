"""把中立 Workspace preview 结果装配为 HTTP 响应。"""

from __future__ import annotations

from urllib.parse import quote

from fastapi.responses import Response
from yuxi.utils.filepreview import PreviewResult
from yuxi.workspace.preview import preview_workspace_file


async def render_file_preview(
    path: str,
    raw_content: bytes,
    *,
    office_cache_key: str,
) -> dict | Response:
    """把持久文件预览结果转换为 Workspace/Viewer HTTP 响应。"""
    result = await preview_workspace_file(path, raw_content, office_cache_key=office_cache_key)
    return _preview_response(result)


def _preview_response(result: PreviewResult) -> dict | Response:
    if not isinstance(result.content, bytes):
        return result.payload()
    filename = result.filename or "preview"
    return Response(
        result.content,
        media_type=result.media_type or "application/octet-stream",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
            "X-Yuxi-Preview-Type": result.preview_type,
            "X-Yuxi-Preview-Filename": quote(filename),
        },
    )
