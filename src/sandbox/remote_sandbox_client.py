from __future__ import annotations

import httpx


class RemoteSandboxClient:
    def __init__(self, base_url: str, timeout_seconds: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def execute_command(self, command: str, cwd: str = "/workspace") -> dict:
        return self._post("/exec", {"command": command, "cwd": cwd})

    def read_file(self, path: str) -> dict:
        return self._post("/files/read", {"path": path})

    def write_file(self, path: str, content: str, append: bool = False) -> dict:
        return self._post(
            "/files/write",
            {"path": path, "content": content, "append": append},
        )

    def list_dir(self, path: str) -> dict:
        return self._post("/files/list", {"path": path})

    def _post(self, path: str, payload: dict) -> dict:
        try:
            with httpx.Client(base_url=self._base_url, timeout=self._timeout) as client:
                response = client.post(path, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            raise RuntimeError(
                f"Remote sandbox request failed: {exc.response.status_code} {detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Remote sandbox request failed: {exc}") from exc

        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Remote sandbox returned invalid response")
        return data
