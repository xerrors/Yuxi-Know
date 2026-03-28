"""lite 模式下 viewer-oriented filesystem 端到端验证。"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import httpx

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from yuxi.agents.backends.sandbox import (  # noqa: E402
    ensure_thread_dirs,
    sandbox_outputs_dir,
    sandbox_uploads_dir,
    sandbox_user_data_dir,
    sandbox_workspace_dir,
)


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:5050").rstrip("/")
USERNAME = os.getenv("E2E_USERNAME", "zwj")
PASSWORD = os.getenv("E2E_PASSWORD", "zwj12138")
TIMEOUT = httpx.Timeout(180.0, connect=10.0)


class ViewerFilesystemE2ETester:
    def __init__(self):
        self.client = httpx.AsyncClient(base_url=API_BASE_URL, timeout=TIMEOUT, follow_redirects=True)
        self.headers: dict[str, str] | None = None
        self.agent_id: str | None = None
        self.thread_id: str | None = None
        self.other_thread_id: str | None = None

    async def close(self):
        await self.client.aclose()

    async def login(self) -> None:
        resp = await self.client.post("/api/auth/token", data={"username": USERNAME, "password": PASSWORD})
        if resp.status_code != 200:
            raise RuntimeError(f"login failed: {resp.status_code} {resp.text}")
        self.headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    async def pick_agent(self) -> None:
        assert self.headers
        default_resp = await self.client.get("/api/chat/default_agent", headers=self.headers)
        if default_resp.status_code == 200 and default_resp.json().get("default_agent_id"):
            self.agent_id = str(default_resp.json()["default_agent_id"])
            return
        agents_resp = await self.client.get("/api/chat/agent", headers=self.headers)
        if agents_resp.status_code != 200:
            raise RuntimeError(f"failed to list agents: {agents_resp.status_code} {agents_resp.text}")
        agents = agents_resp.json().get("agents", [])
        if not agents:
            raise RuntimeError("no available agents")
        self.agent_id = str(agents[0]["id"])

    async def create_thread(self) -> None:
        assert self.headers and self.agent_id
        resp = await self.client.post(
            "/api/chat/thread",
            json={"agent_id": self.agent_id, "title": f"viewer-fs-e2e-{uuid.uuid4().hex[:8]}", "metadata": {}},
            headers=self.headers,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"create thread failed: {resp.status_code} {resp.text}")
        payload = resp.json()
        self.thread_id = str(payload.get("thread_id") or payload.get("id"))

    async def create_other_thread(self) -> None:
        assert self.headers and self.agent_id
        resp = await self.client.post(
            "/api/chat/thread",
            json={"agent_id": self.agent_id, "title": f"viewer-fs-e2e-{uuid.uuid4().hex[:8]}", "metadata": {}},
            headers=self.headers,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"create second thread failed: {resp.status_code} {resp.text}")
        payload = resp.json()
        self.other_thread_id = str(payload.get("thread_id") or payload.get("id"))

    async def tree(self, path: str, *, thread_id: str | None = None) -> list[dict]:
        assert self.headers and self.thread_id and self.agent_id
        target_thread_id = thread_id or self.thread_id
        resp = await self.client.get(
            "/api/viewer/filesystem/tree",
            params={"thread_id": target_thread_id, "path": path, "agent_id": self.agent_id},
            headers=self.headers,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"viewer tree failed on {path}: {resp.status_code} {resp.text}")
        return list(resp.json().get("entries") or [])

    async def file(self, path: str, *, thread_id: str | None = None) -> dict:
        assert self.headers and self.thread_id and self.agent_id
        target_thread_id = thread_id or self.thread_id
        resp = await self.client.get(
            "/api/viewer/filesystem/file",
            params={"thread_id": target_thread_id, "path": path, "agent_id": self.agent_id},
            headers=self.headers,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"viewer file failed on {path}: {resp.status_code} {resp.text}")
        return dict(resp.json())

    async def download(self, path: str, *, thread_id: str | None = None) -> tuple[str, bytes]:
        assert self.headers and self.thread_id and self.agent_id
        target_thread_id = thread_id or self.thread_id
        resp = await self.client.get(
            "/api/viewer/filesystem/download",
            params={"thread_id": target_thread_id, "path": path, "agent_id": self.agent_id},
            headers=self.headers,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"viewer download failed on {path}: {resp.status_code} {resp.text}")
        return resp.headers.get("content-disposition", ""), resp.content

    async def run_case(self) -> None:
        await self.login()
        await self.pick_agent()
        await self.create_thread()
        await self.create_other_thread()

        assert self.thread_id and self.other_thread_id
        ensure_thread_dirs(self.thread_id)
        ensure_thread_dirs(self.other_thread_id)
        (sandbox_user_data_dir(self.thread_id) / "root-note.txt").write_text("root-visible\n", encoding="utf-8")
        (sandbox_workspace_dir(self.thread_id) / "demo.py").write_text("print(42)\n", encoding="utf-8")
        uploads_dir = sandbox_uploads_dir(self.thread_id) / "attachments"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        (uploads_dir / "thread1.txt").write_text("thread-one-upload\n", encoding="utf-8")
        (sandbox_outputs_dir(self.thread_id) / "result.txt").write_text("viewer-output\n", encoding="utf-8")

        root_paths = {str(e.get("path", "")) for e in await self.tree("/")}
        if "/home/gem/user-data/" not in root_paths:
            raise RuntimeError(f"viewer root missing user-data: {sorted(root_paths)}")

        user_data_paths = {str(e.get("path", "")) for e in await self.tree("/home/gem/user-data")}
        expected_root_paths = {
            "/home/gem/user-data/workspace/",
            "/home/gem/user-data/uploads/",
            "/home/gem/user-data/outputs/",
            "/home/gem/user-data/root-note.txt",
        }
        if not expected_root_paths.issubset(user_data_paths):
            raise RuntimeError(f"viewer user-data root mismatch: {sorted(user_data_paths)}")

        workspace_paths = {str(e.get("path", "")) for e in await self.tree("/home/gem/user-data/workspace")}
        if "/home/gem/user-data/workspace/demo.py" not in workspace_paths:
            raise RuntimeError(f"viewer workspace missing demo.py: {sorted(workspace_paths)}")

        other_workspace_paths = {
            str(e.get("path", ""))
            for e in await self.tree(
                "/home/gem/user-data/workspace",
                thread_id=self.other_thread_id,
            )
        }
        if "/home/gem/user-data/workspace/demo.py" not in other_workspace_paths:
            raise RuntimeError(f"shared workspace missing in second thread: {sorted(other_workspace_paths)}")

        other_upload_paths = {
            str(e.get("path", ""))
            for e in await self.tree(
                "/home/gem/user-data/uploads",
                thread_id=self.other_thread_id,
            )
        }
        if "/home/gem/user-data/uploads/attachments/" in other_upload_paths:
            raise RuntimeError(f"thread-local uploads leaked to second thread: {sorted(other_upload_paths)}")

        file_payload = await self.file("/home/gem/user-data/workspace/demo.py")
        if file_payload.get("content") != "print(42)\n":
            raise RuntimeError(f"unexpected viewer file content: {file_payload!r}")
        if file_payload.get("preview_type") != "text" or file_payload.get("supported") is not True:
            raise RuntimeError(f"unexpected viewer file preview metadata: {file_payload!r}")

        other_file_payload = await self.file("/home/gem/user-data/workspace/demo.py", thread_id=self.other_thread_id)
        if other_file_payload.get("content") != "print(42)\n":
            raise RuntimeError(f"unexpected shared workspace content: {other_file_payload!r}")

        content_disposition, payload = await self.download("/home/gem/user-data/outputs/result.txt")
        if "result.txt" not in content_disposition:
            raise RuntimeError(f"unexpected content-disposition: {content_disposition}")
        if payload != b"viewer-output\n":
            raise RuntimeError(f"unexpected download payload: {payload!r}")

        print("[PASS] Viewer filesystem E2E completed")
        print(f"thread_id={self.thread_id}")


async def main() -> None:
    tester = ViewerFilesystemE2ETester()
    try:
        await tester.run_case()
    finally:
        await tester.close()


if __name__ == "__main__":
    asyncio.run(main())
