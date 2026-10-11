from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import httpx
import pytest
from PIL import Image, ImageDraw, ImageFont

from e2e_helpers import delete_agent
from test.e2e.e2e_helpers import create_public_thread
from test.e2e.e2e_helpers import output_text

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e, pytest.mark.slow]

RUN_TIMEOUT_SECONDS = int(os.getenv("E2E_RUN_TIMEOUT_SECONDS", "240"))
VISION_MODEL = os.getenv("E2E_VISION_MODEL")
NON_VISION_MODEL = os.getenv("E2E_NON_VISION_MODEL")


async def _create_agent(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    uid: str,
    model: str,
) -> str:
    slug = f"e2e-read-file-{uuid.uuid4().hex[:8]}"
    response = await client.post(
        "/api/agent",
        json={
            "name": f"E2E read_file {slug[-8:]}",
            "slug": slug,
            "backend_id": "ChatbotAgent",
            "visibility": "shared",
            "description": "read_file 多模态真实链路测试智能体",
            "config_json": {
                "context": {
                    "model": model,
                    "system_prompt": (
                        "你是 read_file 端到端测试智能体。用户要求读取附件时，必须先调用 read_file，"
                        "不得根据文件名猜测内容。严格按用户指定格式回答。"
                    ),
                    "tools": [],
                    "knowledges": [],
                    "mcps": [],
                    "skills": [],
                    "model_retry_times": 0,
                }
            },
            "share_config": {
                "version": 2,
                "read_scope": {"access_level": "user", "department_ids": [], "user_uids": [uid]},
                "manage_scope": None,
            },
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return slug


async def _upload(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    thread_id: str,
    file_path: Path,
) -> str:
    with file_path.open("rb") as handle:
        upload_response = await client.post(
            "/api/v1/agents/files",
            files={"file": (file_path.name, handle)},
            headers=headers,
        )
    assert upload_response.status_code == 201, upload_response.text
    uploaded = upload_response.json()
    assert uploaded["filename"] == file_path.name
    return str(uploaded["id"])


async def _run(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    thread_id: str,
    query: str,
    attachment_file_id: str,
) -> str:
    """将带附件的消息投递到 Public Thread 并读取本 Turn 结果。"""
    response = await client.post(
        f"/api/v1/agents/sessions/{thread_id}/events",
        json={
            "events": [
                {
                    "type": "agent.session.input.message",
                    "input": [
                        {
                            "role": "user",
                            "content": [{"type": "input_text", "text": query}],
                        }
                    ],
                    "yuxi": {"mode": "follow_up", "attachment_file_ids": [attachment_file_id]},
                }
            ],
        },
        headers={**headers, "Idempotency-Key": f"read-file-input-{uuid.uuid4().hex}"},
    )
    assert response.status_code == 202, response.text
    from test.e2e.e2e_helpers import wait_for_consumed_input

    accepted = await wait_for_consumed_input(client, headers, response.json())
    turn_id = str(accepted["turn_id"])
    run_id = str(accepted["run_id"])

    deadline = asyncio.get_running_loop().time() + RUN_TIMEOUT_SECONDS
    completed = False
    try:
        while asyncio.get_running_loop().time() < deadline:
            result = await client.get(f"/api/v1/agents/sessions/{thread_id}/turns/{turn_id}", headers=headers)
            assert result.status_code == 200, result.text
            turn = result.json()
            if turn["status"] in {"completed", "failed", "cancelled"}:
                completed = True
                assert turn["status"] == "completed", turn
                assert turn["yuxi"]["result_run_id"] == run_id, turn
                assert turn["yuxi"]["output"] is not None, turn
                return str(output_text(turn["yuxi"]["output"]))
            await asyncio.sleep(2)
        pytest.fail(f"read_file E2E Turn timed out: {turn_id}")
    finally:
        if not completed:
            cancel = await client.post(
                f"/api/v1/agents/sessions/{thread_id}/events",
                json={"events": [{"type": "agent.session.input.cancel", "yuxi": {"turn_id": turn_id}}]},
                headers={**headers, "Idempotency-Key": f"read-file-cancel-{turn_id}"},
            )
            assert cancel.status_code in {202, 409}, cancel.text
            for _ in range(60):
                settled = await client.get(f"/api/v1/agents/sessions/{thread_id}/turns/{turn_id}", headers=headers)
                assert settled.status_code == 200, settled.text
                if settled.json()["status"] in {"completed", "failed", "cancelled"}:
                    break
                await asyncio.sleep(1)


def _write_test_image(path: Path) -> None:
    image = Image.new("RGB", (128, 128), "red")
    ImageDraw.Draw(image).rectangle((40, 40, 88, 88), fill="blue")
    image.save(path, format="PNG")


def _write_ocr_test_image(path: Path) -> None:
    image = Image.new("RGB", (720, 180), "white")
    font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 56)
    ImageDraw.Draw(image).text((35, 55), "OCR FALLBACK OK", fill="black", font=font)
    image.save(path, format="PNG")


async def test_read_file_image_and_document_real_agent_runs(
    tmp_path: Path,
    e2e_client: httpx.AsyncClient,
    e2e_headers: dict[str, str],
    e2e_agent_context: dict[str, str],
) -> None:
    if not VISION_MODEL:
        pytest.skip("E2E_VISION_MODEL is not configured for the external vision model test.")

    slug = await _create_agent(
        e2e_client,
        e2e_headers,
        uid=e2e_agent_context["uid"],
        model=VISION_MODEL,
    )
    thread_ids: list[str] = []
    try:
        image_path = tmp_path / "shape.png"
        _write_test_image(image_path)
        image_thread = await create_public_thread(e2e_client, e2e_headers, slug, tag="read-file-e2e")
        thread_ids.append(image_thread)
        image_file_id = await _upload(e2e_client, e2e_headers, thread_id=image_thread, file_path=image_path)
        image_output = await _run(
            e2e_client,
            e2e_headers,
            thread_id=image_thread,
            query="调用 read_file 检查 shape.png。中心方块是什么颜色？只回答英文颜色单词。",
            attachment_file_id=image_file_id,
        )
        assert image_output.strip().lower() == "blue", image_output

        document_path = tmp_path / "sample.pdf"
        document_path.write_bytes(b"%PDF-1.4\n% read_file boundary test\n")
        document_thread = await create_public_thread(e2e_client, e2e_headers, slug, tag="read-file-e2e")
        thread_ids.append(document_thread)
        document_file_id = await _upload(
            e2e_client,
            e2e_headers,
            thread_id=document_thread,
            file_path=document_path,
        )
        document_output = await _run(
            e2e_client,
            e2e_headers,
            thread_id=document_thread,
            query="只调用 read_file 读取 sample.pdf，不要调用其他工具。简短复述工具返回的处理建议。",
            attachment_file_id=document_file_id,
        )
        assert "ocr_parse_file" in document_output, document_output
    finally:
        for thread_id in thread_ids:
            archive = await e2e_client.post(f"/api/v1/agents/sessions/{thread_id}/archive", headers=e2e_headers)
            assert archive.status_code == 200, archive.text
        await delete_agent(e2e_client, e2e_headers, slug)


async def test_non_vision_model_uses_ocr_fallback(
    tmp_path: Path,
    e2e_client: httpx.AsyncClient,
    e2e_headers: dict[str, str],
    e2e_agent_context: dict[str, str],
) -> None:
    if not NON_VISION_MODEL:
        pytest.skip("E2E_NON_VISION_MODEL is not configured for the external capability rejection test.")

    slug = await _create_agent(
        e2e_client,
        e2e_headers,
        uid=e2e_agent_context["uid"],
        model=NON_VISION_MODEL,
    )
    thread_id = None
    try:
        image_path = tmp_path / "ocr-text.png"
        _write_ocr_test_image(image_path)
        thread_id = await create_public_thread(e2e_client, e2e_headers, slug, tag="read-file-e2e")
        image_file_id = await _upload(e2e_client, e2e_headers, thread_id=thread_id, file_path=image_path)
        output = await _run(
            e2e_client,
            e2e_headers,
            thread_id=thread_id,
            query="调用 read_file 读取 ocr-text.png 中的文字，只回答图片中的英文文字。",
            attachment_file_id=image_file_id,
        )
        assert "OCR FALLBACK OK" in " ".join(output.upper().split()), output
    finally:
        if thread_id:
            archive = await e2e_client.post(f"/api/v1/agents/sessions/{thread_id}/archive", headers=e2e_headers)
            assert archive.status_code == 200, archive.text
        await delete_agent(e2e_client, e2e_headers, slug)
