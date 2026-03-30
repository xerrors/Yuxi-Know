from __future__ import annotations

import asyncio
import json
import os
import uuid

import httpx
import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e, pytest.mark.slow]

POLL_INTERVAL_SECONDS = float(os.getenv("E2E_RUN_POLL_INTERVAL_SECONDS", "2"))
RUN_TIMEOUT_SECONDS = int(os.getenv("E2E_RUN_TIMEOUT_SECONDS", "240"))

SCRIPT_PATH = "/home/gem/user-data/workspace/bubble_sort.py"
RESULT_PATH = "/home/gem/user-data/outputs/bubble_sort_result.txt"
EXPECTED_OUTPUT = "[1, 2, 4, 5, 8]"


async def _create_thread(client: httpx.AsyncClient, headers: dict[str, str], agent_id: str) -> str:
    response = await client.post(
        "/api/chat/thread",
        json={
            "agent_id": agent_id,
            "title": f"agent-bubble-sort-e2e-{uuid.uuid4().hex[:8]}",
            "metadata": {},
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    thread_id = payload.get("thread_id") or payload.get("id")
    assert thread_id, payload
    return str(thread_id)


async def _create_run(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    agent_config_id: int,
    thread_id: str,
    query: str,
) -> str:
    request_id = f"agent-bubble-sort-{uuid.uuid4()}"
    response = await client.post(
        "/api/chat/runs",
        json={
            "query": query,
            "agent_config_id": agent_config_id,
            "thread_id": thread_id,
            "meta": {"request_id": request_id},
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    run_id = response.json().get("run_id")
    assert run_id, response.text
    return str(run_id)


async def _wait_for_run(client: httpx.AsyncClient, headers: dict[str, str], run_id: str) -> dict:
    deadline = asyncio.get_running_loop().time() + RUN_TIMEOUT_SECONDS
    last_payload: dict | None = None

    while asyncio.get_running_loop().time() < deadline:
        response = await client.get(f"/api/chat/runs/{run_id}", headers=headers)
        assert response.status_code == 200, response.text

        last_payload = response.json().get("run") or {}
        status = str(last_payload.get("status") or "")
        if status in {"completed", "failed", "cancelled", "interrupted"}:
            return last_payload

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    pytest.fail("Run timed out: " + json.dumps(last_payload or {}, ensure_ascii=False))


async def _list_thread_files(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    thread_id: str,
    path: str,
) -> list[dict]:
    response = await client.get(
        f"/api/chat/thread/{thread_id}/files",
        params={"path": path, "recursive": "true"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    files = response.json().get("files")
    assert isinstance(files, list), response.text
    return files


async def _read_thread_file(client: httpx.AsyncClient, headers: dict[str, str], thread_id: str, path: str) -> str:
    response = await client.get(
        f"/api/chat/thread/{thread_id}/files/content",
        params={"path": path},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    lines = response.json().get("content")
    assert isinstance(lines, list), response.text
    return "\n".join(str(line) for line in lines)


async def test_agent_bubble_sort_run_creates_expected_artifacts(
    e2e_client: httpx.AsyncClient,
    e2e_headers: dict[str, str],
    e2e_agent_context: dict[str, str | int],
):
    thread_id = await _create_thread(e2e_client, e2e_headers, str(e2e_agent_context["agent_id"]))

    query = (
        "在工作区创建一个 Python 冒泡排序脚本，并执行它。"
        f"脚本必须保存到 {SCRIPT_PATH}。"
        "脚本内容要求：对列表 [5, 1, 4, 2, 8] 使用冒泡排序，并打印排序后的结果。"
        f"然后执行该脚本，并将标准输出保存到 {RESULT_PATH}。"
        "不要写入其他路径。完成后简单回复这两个文件路径。"
    )
    run_id = await _create_run(
        e2e_client,
        e2e_headers,
        agent_config_id=int(e2e_agent_context["agent_config_id"]),
        thread_id=thread_id,
        query=query,
    )

    run_payload = await _wait_for_run(e2e_client, e2e_headers, run_id)
    assert run_payload.get("status") == "completed", run_payload

    file_entries = await _list_thread_files(e2e_client, e2e_headers, thread_id, "/home/gem/user-data")
    file_paths = {str(entry.get("path") or "") for entry in file_entries}
    assert SCRIPT_PATH in file_paths, sorted(file_paths)
    assert RESULT_PATH in file_paths, sorted(file_paths)

    script_content = await _read_thread_file(e2e_client, e2e_headers, thread_id, SCRIPT_PATH)
    assert "bubble" in script_content.lower() or "for" in script_content, script_content

    result_content = await _read_thread_file(e2e_client, e2e_headers, thread_id, RESULT_PATH)
    assert EXPECTED_OUTPUT in result_content, result_content
