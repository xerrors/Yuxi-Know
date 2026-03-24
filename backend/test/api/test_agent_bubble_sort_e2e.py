"""通过 Agent Runs API 验证文件创建与结果落盘的端到端脚本。

流程：
1. 使用环境变量中的管理员账号登录
2. 创建 thread
3. 调用 Agent，要求其创建冒泡排序脚本并执行
4. 通过线程文件 API 验证脚本文件与结果文件

运行：
    docker compose exec api uv run python test/api/test_agent_bubble_sort_e2e.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

load_dotenv(".env", override=False)
load_dotenv("test/.env.test", override=False)

API_BASE_URL = os.getenv("TEST_BASE_URL", os.getenv("API_BASE_URL", "http://localhost:5050")).rstrip("/")
USERNAME = os.getenv("TEST_USERNAME") or os.getenv("E2E_USERNAME")
PASSWORD = os.getenv("TEST_PASSWORD") or os.getenv("E2E_PASSWORD")
TIMEOUT = httpx.Timeout(300.0, connect=10.0)
POLL_INTERVAL_SECONDS = float(os.getenv("E2E_RUN_POLL_INTERVAL_SECONDS", "2"))
RUN_TIMEOUT_SECONDS = int(os.getenv("E2E_RUN_TIMEOUT_SECONDS", "240"))

SCRIPT_PATH = "/home/yuxi/user-data/workspace/bubble_sort.py"
RESULT_PATH = "/home/yuxi/user-data/outputs/bubble_sort_result.txt"
EXPECTED_OUTPUT = "[1, 2, 4, 5, 8]"


class AgentBubbleSortE2ETester:
    def __init__(self):
        if not USERNAME or not PASSWORD:
            raise RuntimeError("TEST_USERNAME / TEST_PASSWORD 未配置")

        self.client = httpx.AsyncClient(base_url=API_BASE_URL, timeout=TIMEOUT, follow_redirects=True)
        self.headers: dict[str, str] | None = None
        self.agent_id: str | None = None
        self.thread_id: str | None = None

    async def close(self):
        await self.client.aclose()

    async def login(self) -> None:
        response = await self.client.post("/api/auth/token", data={"username": USERNAME, "password": PASSWORD})
        if response.status_code != 200:
            raise RuntimeError(f"login failed: {response.status_code} {response.text}")
        token = response.json().get("access_token")
        if not token:
            raise RuntimeError("login succeeded but access_token is missing")
        self.headers = {"Authorization": f"Bearer {token}"}

    async def pick_agent(self) -> None:
        assert self.headers
        default_response = await self.client.get("/api/chat/default_agent", headers=self.headers)
        if default_response.status_code == 200:
            default_agent_id = default_response.json().get("default_agent_id")
            if default_agent_id:
                self.agent_id = str(default_agent_id)
                return

        response = await self.client.get("/api/chat/agent", headers=self.headers)
        if response.status_code != 200:
            raise RuntimeError(f"list agents failed: {response.status_code} {response.text}")
        agents = response.json().get("agents") or []
        if not agents:
            raise RuntimeError("no available agents")
        self.agent_id = str(agents[0]["id"])

    async def create_thread(self) -> None:
        assert self.headers and self.agent_id
        response = await self.client.post(
            "/api/chat/thread",
            json={
                "agent_id": self.agent_id,
                "title": f"agent-bubble-sort-e2e-{uuid.uuid4().hex[:8]}",
                "metadata": {},
            },
            headers=self.headers,
        )
        if response.status_code != 200:
            raise RuntimeError(f"create thread failed: {response.status_code} {response.text}")
        payload = response.json()
        self.thread_id = str(payload.get("thread_id") or payload.get("id"))
        if not self.thread_id:
            raise RuntimeError(f"thread id missing: {payload}")

    async def create_run(self, query: str) -> str:
        assert self.headers and self.agent_id and self.thread_id
        request_id = f"agent-bubble-sort-{uuid.uuid4()}"
        response = await self.client.post(
            f"/api/chat/agent/{self.agent_id}/runs",
            json={
                "query": query,
                "config": {"thread_id": self.thread_id, "request_id": request_id},
            },
            headers=self.headers,
        )
        if response.status_code != 200:
            raise RuntimeError(f"create run failed: {response.status_code} {response.text}")
        run_id = response.json().get("run_id")
        if not run_id:
            raise RuntimeError(f"run id missing: {response.text}")
        return str(run_id)

    async def wait_for_run(self, run_id: str) -> dict:
        assert self.headers
        deadline = asyncio.get_running_loop().time() + RUN_TIMEOUT_SECONDS
        last_payload: dict | None = None

        while asyncio.get_running_loop().time() < deadline:
            response = await self.client.get(f"/api/chat/runs/{run_id}", headers=self.headers)
            if response.status_code != 200:
                raise RuntimeError(f"get run failed: {response.status_code} {response.text}")

            last_payload = response.json().get("run") or {}
            status = str(last_payload.get("status") or "")
            if status in {"completed", "failed", "cancelled", "interrupted"}:
                return last_payload

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        raise RuntimeError("run timeout: " + json.dumps(last_payload or {}, ensure_ascii=False))

    async def list_thread_files(self, path: str) -> list[dict]:
        assert self.headers and self.thread_id
        response = await self.client.get(
            f"/api/chat/thread/{self.thread_id}/files",
            params={"path": path, "recursive": "true"},
            headers=self.headers,
        )
        if response.status_code != 200:
            raise RuntimeError(f"list thread files failed: {response.status_code} {response.text}")
        files = response.json().get("files")
        if not isinstance(files, list):
            raise RuntimeError(f"invalid files response: {response.text}")
        return files

    async def read_thread_file(self, path: str) -> str:
        assert self.headers and self.thread_id
        response = await self.client.get(
            f"/api/chat/thread/{self.thread_id}/files/content",
            params={"path": path},
            headers=self.headers,
        )
        if response.status_code != 200:
            raise RuntimeError(f"read thread file failed: {response.status_code} {response.text}")
        lines = response.json().get("content")
        if not isinstance(lines, list):
            raise RuntimeError(f"invalid file content response: {response.text}")
        return "\n".join(str(line) for line in lines)

    async def run_case(self) -> None:
        await self.login()
        await self.pick_agent()
        await self.create_thread()

        query = (
            "在工作区创建一个 Python 冒泡排序脚本，并执行它。"
            f"脚本必须保存到 {SCRIPT_PATH}。"
            "脚本内容要求：对列表 [5, 1, 4, 2, 8] 使用冒泡排序，并打印排序后的结果。"
            f"然后执行该脚本，并将标准输出保存到 {RESULT_PATH}。"
            "不要写入其他路径。完成后简单回复这两个文件路径。"
        )

        run_id = await self.create_run(query)
        run = await self.wait_for_run(run_id)

        if run.get("status") != "completed":
            raise RuntimeError("run did not complete successfully: " + json.dumps(run, ensure_ascii=False))

        file_entries = await self.list_thread_files("/home/yuxi/user-data")
        file_paths = {str(entry.get("path") or "") for entry in file_entries}

        if SCRIPT_PATH not in file_paths:
            raise RuntimeError("script file missing: " + json.dumps(sorted(file_paths), ensure_ascii=False))
        if RESULT_PATH not in file_paths:
            raise RuntimeError("result file missing: " + json.dumps(sorted(file_paths), ensure_ascii=False))

        script_content = await self.read_thread_file(SCRIPT_PATH)
        if "bubble" not in script_content.lower() and "for" not in script_content:
            raise RuntimeError(f"unexpected script content: {script_content}")

        result_content = await self.read_thread_file(RESULT_PATH)
        if EXPECTED_OUTPUT not in result_content:
            raise RuntimeError(f"unexpected result content: {result_content}")

        print("[PASS] Agent bubble sort E2E completed")
        print(f"thread_id={self.thread_id}")
        print(f"run_id={run_id}")
        print(f"script_path={SCRIPT_PATH}")
        print(f"result_path={RESULT_PATH}")
        print(f"result_content={result_content}")


async def main() -> None:
    tester = AgentBubbleSortE2ETester()
    try:
        await tester.run_case()
    finally:
        await tester.close()


if __name__ == "__main__":
    asyncio.run(main())
