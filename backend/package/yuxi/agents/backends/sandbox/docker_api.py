from __future__ import annotations

import json
import subprocess


def docker_api_call(
    *,
    base_url: str,
    socket_path: str,
    method: str,
    path: str,
    payload: dict | None = None,
    timeout: int | None = None,
) -> tuple[int, str, str]:
    cmd = [
        "curl",
        "-sS",
        "--unix-socket",
        socket_path,
        "-X",
        method,
        f"{base_url}{path}",
    ]
    if payload is not None:
        cmd.extend(["-H", "Content-Type: application/json", "-d", json.dumps(payload, ensure_ascii=False)])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=False,
        timeout=timeout,
        check=False,
    )
    stdout = (result.stdout or b"").decode("utf-8", errors="ignore")
    stderr = (result.stderr or b"").decode("utf-8", errors="ignore")
    return result.returncode, stdout, stderr


def docker_api_request(
    *,
    base_url: str,
    socket_path: str,
    method: str,
    path: str,
    payload: dict | None = None,
    timeout: int = 15,
) -> dict:
    rc, stdout, stderr = docker_api_call(
        base_url=base_url,
        socket_path=socket_path,
        method=method,
        path=path,
        payload=payload,
        timeout=timeout,
    )
    if rc != 0:
        raise RuntimeError(stderr.strip() or "Docker API request failed")

    text = stdout.strip()
    if not text:
        return {}

    data = json.loads(text)
    if isinstance(data, dict) and data.get("message"):
        raise RuntimeError(str(data["message"]))
    return data if isinstance(data, dict) else {}
