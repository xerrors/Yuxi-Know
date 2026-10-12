"""对话 Image 复用鉴权文件预览的真实 HTTP 契约。"""

import base64
from urllib.parse import quote

import pytest

from test.integration.api.helpers import create_default_agent_thread, delete_created_threads

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.mark.self_managed_resources
async def test_widget_image_preview_reads_real_file_without_artifact_registration(test_client, standard_user, admin_headers):
    """未登记的沙盒图片按当前 Thread 授权读取，越权与跳转拒绝。"""
    headers = standard_user["headers"]
    thread_id = await create_default_agent_thread(test_client, headers, title_prefix="widget-image")
    try:
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j4AAAAABJRU5ErkJggg==")
        name = "图片 #1.png"
        upload = await test_client.post(
            "/api/viewer/filesystem/upload",
            data={"thread_id": thread_id, "parent_path": "/"},
            files={"files": (name, png, "image/png")},
            headers=headers,
        )
        assert upload.status_code == 200, upload.text
        [entry] = upload.json()["entries"]
        url = quote(entry["artifact_url"], safe="/")
        response = await test_client.get(url, params={"preview": "true"}, headers=headers)
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("image/png")
        assert response.content == png
        anonymous = await test_client.get(url, params={"preview": "true"})
        assert anonymous.status_code == 401
        cross_user = await test_client.get(url, params={"preview": "true"}, headers=admin_headers)
        assert cross_user.status_code == 404
        traversal = url.rsplit("/", 1)[0] + "/%2E%2E/secret.png"
        denied = await test_client.get(traversal, params={"preview": "true"}, headers=headers)
        assert denied.status_code == 403, denied.text
        missing = await test_client.get(url + ".missing", params={"preview": "true"}, headers=headers)
        assert missing.status_code == 404
    finally:
        await delete_created_threads(thread_id)
