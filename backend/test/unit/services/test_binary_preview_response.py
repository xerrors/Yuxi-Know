"""内存二进制预览完整响应的协议回归。"""

import pytest
from yuxi.services.file_preview import _preview_response
from yuxi.utils.filepreview import PreviewResult

from server.routers.workspace_router import _binary_preview_response


@pytest.mark.parametrize("owner", ["knowledge", "workspace"])
async def test_memory_pdf_is_one_body_with_length(owner):
    """带大量换行的 PDF 必须逐字完整且只发送一个正文块。"""
    content = b"%PDF-1.4\n" + b"binary-data\n" * 7100
    if owner == "knowledge":
        response = _binary_preview_response(
            {"content": content, "filename": "报表.pdf", "preview_type": "pdf", "media_type": "application/pdf"}
        )
    else:
        response = _preview_response(PreviewResult(content, "pdf", True, "application/pdf", "报表.pdf"))
    messages = []

    async def send(message):
        """观察真实 ASGI 协议输出。"""
        messages.append(message)

    async def receive():
        """仅提供标准请求结束信号。"""
        return {"type": "http.request", "body": b"", "more_body": False}

    await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
    body = [message for message in messages if message["type"] == "http.response.body"]
    assert len(body) == 1
    assert body[0]["body"] == content and not body[0].get("more_body", False)
    assert response.headers["content-length"] == str(len(content))
    assert response.headers["x-yuxi-preview-type"] == "pdf"
