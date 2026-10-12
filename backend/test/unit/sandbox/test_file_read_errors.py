"""通过真实 SDK 解析坏响应，验证模型侧的文件错误语义。"""

from types import SimpleNamespace

import httpx
import pytest
from agent_sandbox import AsyncSandbox, Sandbox

import yuxi.modules.agents.runtime.sandbox.backend as sandbox_module


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["sync", "async"])
@pytest.mark.parametrize("failure", ["missing", "missing_current", "malformed"])
async def test_sdk_error_response_has_clean_sync_and_async_file_semantics(monkeypatch, entry, failure):
    """缺失文件只报告不存在，未知校验错误不泄露模型和响应输入。"""
    path = "/home/gem/user-data/regression.txt"
    payload = {
        "success": False,
        "message": "PRIVATE_RESPONSE_VALUE",
        "data": {"path": path, "error": "FileNotFoundError" if failure == "missing" else "PRIVATE_RESPONSE_VALUE"},
    }
    if failure == "missing_current":
        payload["data"] = {"path": path, "operation": "read", "error_type": "not_found", "message": "PRIVATE_RESPONSE_VALUE", "errno": 2}
    monkeypatch.setattr(sandbox_module, "get_sandbox_provider", lambda: object())
    backend = sandbox_module.ProvisionerSandboxBackend(thread_id="fixture", uid="fixture")
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
    if entry == "sync":
        with httpx.Client(transport=transport) as wire:
            sdk = Sandbox(base_url="http://sandbox.example", httpx_client=wire)
            monkeypatch.setattr(backend, "_get_client", lambda: sdk)
            result = backend.read(path)
    else:
        async with httpx.AsyncClient(transport=transport) as wire:
            sdk = AsyncSandbox(base_url="http://sandbox.example", httpx_client=wire)
            monkeypatch.setattr(backend, "_get_connection", lambda: SimpleNamespace(sandbox_url="http://sandbox.example"))
            monkeypatch.setattr(backend, "_build_async_client", lambda _url, _client: sdk)
            result = await backend.aread(path)
    expected = f"File '{path}' not found" if failure.startswith("missing") else f"Failed to read '{path}': invalid sandbox response"
    assert result.error == expected
    internal_details = ["ResponseFileReadResult", "validation errors", "data.content", "PRIVATE_RESPONSE_VALUE"]
    assert not any(detail in result.error for detail in internal_details)
