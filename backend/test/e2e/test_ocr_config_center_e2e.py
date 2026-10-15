from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from PIL import Image, ImageDraw, ImageFont

from test.live_api_cleanup import (
    make_test_session_title,
)
from test.e2e.e2e_helpers import cleanup_uploaded_chat_attachment

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e]


async def test_admin_ocr_config_drives_real_tmp_attachment_parse(
    e2e_client: httpx.AsyncClient,
    e2e_headers: dict[str, str],
    e2e_agent_context: dict[str, str],
    tmp_path: Path,
):
    """验证管理员配置能驱动真实临时附件 OCR，并回收测试创建的资源。"""

    configs_response = await e2e_client.get("/api/system/config", headers=e2e_headers)
    assert configs_response.status_code == 200, configs_response.text
    previous_default = configs_response.json()["default_ocr_engine"]
    image_path = tmp_path / "ocr-config-center.png"
    _build_ocr_image(image_path)
    thread_id = None
    uploaded = None
    parsed = None
    attachment = None

    try:
        update_response = await e2e_client.post(
            "/api/system/config/update",
            json={"default_ocr_engine": "rapid_ocr"},
            headers=e2e_headers,
        )
        assert update_response.status_code == 200, update_response.text

        options_response = await e2e_client.get("/api/system/ocr/options", headers=e2e_headers)
        assert options_response.status_code == 200, options_response.text
        assert options_response.json()["default_engine"] == "rapid_ocr"

        thread_response = await e2e_client.post(
            "/api/v1/agents/sessions",
            json={
                "agent_id": e2e_agent_context["agent_slug"],
                "title": make_test_session_title("ocr-config-e2e"),
            },
            headers={**e2e_headers, "Idempotency-Key": f"ocr-config-{uuid4().hex}"},
        )
        assert thread_response.status_code == 201, thread_response.text
        thread_id = str(thread_response.json()["id"])

        with image_path.open("rb") as image_file:
            upload_response = await e2e_client.post(
                "/api/v1/agents/files",
                files={"file": (image_path.name, image_file, "image/png")},
                headers=e2e_headers,
            )
        assert upload_response.status_code == 201, upload_response.text
        uploaded = upload_response.json()
        options = await e2e_client.get(f"/api/agent/files/{uploaded['id']}", headers=e2e_headers)
        assert "rapid_ocr" in options.json()["parse_methods"]

        parse_response = await e2e_client.post(
            f"/api/agent/files/{uploaded['id']}/parse",
            json={"parse_method": None},
            headers=e2e_headers,
        )
        assert parse_response.status_code == 200, parse_response.text
        parsed = parse_response.json()
        assert parsed["parse_method"] == "rapid_ocr"

        from yuxi.infrastructure.postgres.manager import pg_manager
        from yuxi.modules.agents.repositories.sessions import SessionRepository

        pg_manager.initialize()
        async with pg_manager.get_async_session_context() as db:
            session = await SessionRepository(db).get_session_by_thread_id(thread_id)
            session.queue_paused = True
        accepted = await e2e_client.post(
            f"/api/v1/agents/sessions/{thread_id}/events",
            headers={**e2e_headers, "Idempotency-Key": uuid4().hex},
            json={
                "events": [
                    {
                        "type": "agent.session.input.message",
                        "input": [
                            {
                                "role": "user",
                                "content": [{"type": "input_text", "text": "保存 OCR 文档"}],
                            }
                        ],
                        "yuxi": {"mode": "follow_up", "attachment_file_ids": [uploaded["id"]]},
                    }
                ]
            },
        )
        assert accepted.status_code == 202, accepted.text
        [attachment] = (await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/attachments", headers=e2e_headers)).json()["attachments"]
        cancelled = await e2e_client.post(
            f"/api/v1/agents/sessions/{thread_id}/events",
            headers={**e2e_headers, "Idempotency-Key": uuid4().hex},
            json={"events": [{"type": "yuxi.session.input.cancel_input", "input_id": accepted.json()["input_id"]}]},
        )
        assert cancelled.status_code == 202, cancelled.text
        assert attachment["status"] == "parsed"
        assert attachment["path"].endswith(".md")
        assert attachment["artifact_url"]

        file_response = await e2e_client.get(
            attachment["artifact_url"],
            headers=e2e_headers,
        )
        assert file_response.status_code == 200, file_response.text
        recognized = file_response.text.upper()
        assert "OCR" in recognized
        assert "CONFIG" in recognized
        assert "CENTER" in recognized
    finally:
        try:
            restore_default = await e2e_client.post(
                "/api/system/config/update",
                json={"default_ocr_engine": previous_default},
                headers=e2e_headers,
            )
            assert restore_default.status_code == 200, restore_default.text
        finally:
            await _cleanup_created_resources(
                e2e_client=e2e_client,
                e2e_headers=e2e_headers,
                thread_id=thread_id,
                attachment=attachment,
                uploaded=uploaded,
                parsed=parsed,
            )


def _build_ocr_image(path: Path) -> None:
    """生成包含稳定英文文本的真实 OCR 测试图片。"""

    image = Image.new("RGB", (1400, 260), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 72)
    draw.text((60, 80), "OCR CONFIG CENTER E2E", fill="black", font=font)
    image.save(path)


async def _cleanup_created_resources(
    *,
    e2e_client: httpx.AsyncClient,
    e2e_headers: dict[str, str],
    thread_id: str | None,
    attachment: dict | None,
    uploaded: dict | None,
    parsed: dict | None,
) -> None:
    """删除 E2E 创建的正式附件、临时 MinIO 对象和对话线程。"""

    if thread_id and attachment:
        response = await e2e_client.delete(
            f"/api/v1/agents/sessions/{thread_id}/attachments/{attachment['file_id']}",
            headers=e2e_headers,
        )
        assert response.status_code == 200, response.text

    if uploaded:
        me = await e2e_client.get("/api/auth/me", headers=e2e_headers)
        await cleanup_uploaded_chat_attachment(str(me.json()["uid"]), uploaded["id"])

    if thread_id:
        response = await e2e_client.post(f"/api/v1/agents/sessions/{thread_id}/archive", headers=e2e_headers)
        assert response.status_code == 200, response.text
