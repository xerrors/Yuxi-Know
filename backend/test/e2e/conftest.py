from __future__ import annotations

import os
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import anyio
import httpx
import pytest
import pytest_asyncio
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from test.live_api_cleanup import (  # noqa: E402
    cleanup_e2e_chat_resources,
    cleanup_pytest_knowledge_resources,
)

load_dotenv(PROJECT_ROOT / ".env", override=False)
load_dotenv(PROJECT_ROOT / "test/.env.test", override=False)

E2E_BASE_URL = os.getenv("TEST_BASE_URL", os.getenv("API_BASE_URL", "http://localhost:5050")).rstrip("/")
E2E_USERNAME = os.getenv("E2E_USERNAME") or os.getenv("TEST_USERNAME")
E2E_PASSWORD = os.getenv("E2E_PASSWORD") or os.getenv("TEST_PASSWORD")
CLEANUP_USERNAME = E2E_USERNAME or os.getenv("TEST_USERNAME")
CLEANUP_PASSWORD = E2E_PASSWORD or os.getenv("TEST_PASSWORD")
E2E_TIMEOUT = httpx.Timeout(300.0, connect=10.0)
LITE_MODE = os.getenv("LITE_MODE", "").lower() in {"true", "1"}


def _require_e2e_credentials() -> tuple[str, str]:
    if not E2E_USERNAME or not E2E_PASSWORD:
        pytest.skip(
            "E2E credentials are not configured via E2E_USERNAME / E2E_PASSWORD or TEST_USERNAME / TEST_PASSWORD."
        )
    return E2E_USERNAME, E2E_PASSWORD


@pytest.fixture(scope="session")
def e2e_base_url() -> str:
    return E2E_BASE_URL


@pytest.fixture(scope="session", autouse=True)
def cleanup_e2e_test_resources(e2e_base_url: str):
    """在 E2E 会话前后清理测试对话、临时智能体和知识库。"""

    if LITE_MODE or not CLEANUP_USERNAME or not CLEANUP_PASSWORD:
        yield
        return

    async def run_cleanup() -> None:
        async with httpx.AsyncClient(
            base_url=e2e_base_url,
            timeout=E2E_TIMEOUT,
            follow_redirects=True,
        ) as client:
            response = await client.post(
                "/api/auth/token",
                data={"username": CLEANUP_USERNAME, "password": CLEANUP_PASSWORD},
            )
            if response.status_code != 200:
                raise RuntimeError(f"E2E cleanup login failed (status={response.status_code}): {response.text}")

            access_token = response.json().get("access_token")
            if not access_token:
                raise RuntimeError("E2E cleanup login succeeded but no access token was returned")

            headers = {"Authorization": f"Bearer {access_token}"}
            current_user = await client.get("/api/auth/me", headers=headers)
            if current_user.status_code != 200:
                raise RuntimeError(f"E2E cleanup failed to read current user: {current_user.text}")
            if current_user.json().get("role") not in {"admin", "superadmin"}:
                raise RuntimeError("E2E cleanup credentials must belong to an admin or superadmin")

            cleanup_uid = str(current_user.json().get("uid") or "")
            if not cleanup_uid:
                raise RuntimeError("E2E cleanup current user payload is missing uid")

            await cleanup_e2e_chat_resources(client, headers, owner_uid=cleanup_uid)
            await cleanup_pytest_knowledge_resources(client, headers)

    anyio.run(run_cleanup)
    yield
    anyio.run(run_cleanup)


@pytest_asyncio.fixture(scope="function")
async def e2e_client(e2e_base_url: str) -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(base_url=e2e_base_url, timeout=E2E_TIMEOUT, follow_redirects=True) as client:
        yield client


@pytest_asyncio.fixture(scope="function")
async def e2e_headers(e2e_client: httpx.AsyncClient) -> dict[str, str]:
    username, password = _require_e2e_credentials()
    response = await e2e_client.post("/api/auth/token", data={"username": username, "password": password})
    if response.status_code != 200:
        pytest.fail(f"E2E login failed (status={response.status_code}): {response.text}")

    access_token = response.json().get("access_token")
    if not access_token:
        pytest.fail("E2E login succeeded but no access token was returned.")
    return {"Authorization": f"Bearer {access_token}"}


@pytest_asyncio.fixture(scope="function")
async def e2e_agent_context(e2e_client: httpx.AsyncClient, e2e_headers: dict[str, str]) -> dict[str, str]:
    me_response = await e2e_client.get("/api/auth/me", headers=e2e_headers)
    if me_response.status_code != 200:
        pytest.fail(
            f"Failed to fetch current user for E2E tests (status={me_response.status_code}): {me_response.text}"
        )
    uid = me_response.json().get("uid")
    if not uid:
        pytest.fail("Current user payload missing uid field for E2E tests.")

    default_response = await e2e_client.get("/api/agent/default", headers=e2e_headers)
    if default_response.status_code == 200:
        agent = default_response.json().get("agent") or {}
    else:
        response = await e2e_client.get("/api/agent", headers=e2e_headers)
        if response.status_code != 200:
            pytest.fail(f"Failed to list agents for E2E tests (status={response.status_code}): {response.text}")
        agents = response.json().get("agents") or []
        if not agents:
            pytest.fail("No agents are available for E2E tests.")
        agent = agents[0]

    agent_slug = agent.get("slug") or agent.get("agent_id")
    if not agent_slug:
        pytest.fail(f"Agent payload missing slug/agent_id field for E2E tests: {agent}")

    return {"agent_slug": str(agent_slug), "agent_id": str(agent_slug), "uid": str(uid)}
