"""API 集成测试的跨用例 fixture。"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest_asyncio


@dataclass(frozen=True)
class ApiKeyIssue:
    """保存签发响应及后续认证信息。"""

    response: httpx.Response
    key_id: int
    headers: dict[str, str]


@pytest_asyncio.fixture
async def api_key_factory(test_client, admin_headers):
    """签发临时 API Key，并在用例结束时回收仍有效的 Key。"""
    issued: list[tuple[int, dict[str, str]]] = []

    async def issue(payload: dict, *, owner_headers=None, cleanup_headers=None) -> ApiKeyIssue:
        """创建一个临时 Key，并记录其回收身份。"""
        request_headers = owner_headers or admin_headers
        response = await test_client.post("/api/user/apikey/", json=payload, headers=request_headers)
        assert response.status_code == 200, response.text
        data = response.json()
        key_id = data["api_key"]["id"]
        secret = data["secret"]
        deletion_headers = cleanup_headers or request_headers
        if not any(issued_id == key_id for issued_id, _ in issued):
            issued.append((key_id, deletion_headers))
        return ApiKeyIssue(
            response=response,
            key_id=key_id,
            headers={"Authorization": f"Bearer {secret}"},
        )

    yield issue

    for key_id, headers in reversed(issued):
        response = await test_client.delete(f"/api/user/apikey/{key_id}", headers=headers)
        assert response.status_code in {200, 404}, response.text
