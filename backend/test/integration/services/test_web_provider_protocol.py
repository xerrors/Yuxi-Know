"""通过独立 HTTPS 协议重放进程验证生产供应商适配。"""

import asyncio
import socket
import subprocess
import sys

import httpx
import pytest

from yuxi.modules.extensions.web.schemas import FetchInput, SearchInput
from yuxi.modules.extensions.web.services import fetch_web, search_web

pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.self_managed_resources]


async def test_real_https_provider_protocol_in_separate_process(tmp_path, monkeypatch):
    """不改生产端点，通过 TLS 代理实际传输三家请求及两家正文。"""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "test.support.web_provider_replay",
            "--port",
            str(port),
            "--cert-dir",
            str(tmp_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            async with asyncio.timeout(20):
                while True:
                    if process.poll() is not None:
                        pytest.fail("供应商重放进程启动失败")
                    try:
                        response = await client.get(f"http://127.0.0.1:{port}/ready")
                        if response.status_code == 200:
                            break
                    except httpx.RequestError:
                        pass
                    await asyncio.sleep(0.1)
        monkeypatch.setenv("HTTPS_PROXY", f"http://127.0.0.1:{port}")
        monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "ca.pem"))
        monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1")
        monkeypatch.setenv("no_proxy", "localhost,127.0.0.1")
        for provider in ("tavily", "deepseek", "doubao"):
            result = await search_web(SearchInput(query="protocol"), provider=provider, api_key=f"replay-{provider}-key")
            assert result["provider"] == provider
            assert result["results"][0]["relevant_content"] == "REPLAY_RELEVANT"
        for provider in ("tavily", "deepseek"):
            result = await fetch_web(
                FetchInput(url="https://example.com/web-tools-replay"), provider=provider, api_key=f"replay-{provider}-key"
            )
            assert result["content"] == "# REPLAY_FETCH_BODY"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        if process.stderr:
            process.stderr.close()
