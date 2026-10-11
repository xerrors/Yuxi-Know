from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import asyncpg
import httpx
import pytest

from test.e2e.e2e_helpers import output_text

from e2e_helpers import (
    RUN_TIMEOUT_SECONDS,
    archive_public_thread,
    iter_public_thread_events,
    postgres_dsn,
    skip_if_external_quota,
    wait_for_consumed_input,
)
from test.live_api_cleanup import (
    make_test_session_title,
    remove_e2e_thread_storage,
)
from yuxi.modules.extensions.skills.projection import get_user_skills_root_dir
from yuxi.modules.workspace.paths import user_workspace_dir

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e, pytest.mark.slow]


async def test_main_agent_reads_personal_skill_directly_from_user_workspace(
    e2e_client: httpx.AsyncClient,
    e2e_headers: dict[str, str],
    e2e_agent_context: dict[str, str],
):
    """共享选择为空时，真实主 Agent 仍发现并读取个人 SKILL.md。"""
    uid = e2e_agent_context["uid"]
    marker = f"PERSONAL_SKILL_E2E_{uuid.uuid4().hex[:10].upper()}"
    slug = f"pytest-personal-agent-{uuid.uuid4().hex[:8]}"
    agent_slug = f"e2e-personal-skill-{uuid.uuid4().hex[:8]}"
    skill_md = (
        f"---\nname: {slug}\ndescription: Return the verification marker when explicitly requested.\n---\n"
        f"# Verification\nWhen the user asks for the personal Skill marker, reply with exactly `{marker}`.\n"
    )
    run_id: str | None = None
    turn_id: str | None = None
    thread_id: str | None = None
    agent_created = False

    prepare_response = await e2e_client.post(
        "/api/skills/import/prepare",
        headers=e2e_headers,
        files={"file": ("SKILL.md", skill_md.encode(), "text/markdown")},
    )
    assert prepare_response.status_code == 200, prepare_response.text
    draft = prepare_response.json()["data"]
    confirm_response = await e2e_client.post(
        f"/api/skills/personal/install-drafts/{draft['draft_id']}/confirm",
        headers=e2e_headers,
        json={"slugs": [draft["items"][0]["slug"]]},
    )
    assert confirm_response.status_code == 200, confirm_response.text

    try:
        default_response = await e2e_client.get("/api/agent/default", headers=e2e_headers)
        assert default_response.status_code == 200, default_response.text
        default_context = ((default_response.json().get("agent") or {}).get("config_json") or {}).get("context") or {}
        context: dict[str, Any] = {
            "system_prompt": (
                f"收到请求后从可用 Skills 中找到 {slug} 并读取其 SKILL.md，然后严格遵循其中的 Verification 指令，不要添加解释。"
            ),
            "tools": [],
            "knowledges": [],
            "mcps": [],
            "skills": [],
        }
        if default_context.get("model"):
            context["model"] = default_context["model"]

        agent_response = await e2e_client.post(
            "/api/agent",
            headers=e2e_headers,
            json={
                "name": f"E2E Personal Skill {slug[-8:]}",
                "slug": agent_slug,
                "backend_id": "ChatbotAgent",
                "visibility": "shared",
                "description": "真实个人 Skill Agent E2E 临时智能体",
                "config_json": {"context": context},
                "share_config": {
                    "version": 2,
                    "read_scope": {"access_level": "user", "department_ids": [], "user_uids": [uid]},
                    "manage_scope": None,
                },
            },
        )
        assert agent_response.status_code == 200, agent_response.text
        agent_created = True

        thread_response = await e2e_client.post(
            "/api/v1/agents/sessions",
            headers={**e2e_headers, "Idempotency-Key": f"personal-skill-create-{uuid.uuid4().hex}"},
            json={
                "agent_id": agent_slug,
                "title": make_test_session_title("personal-skill-e2e"),
            },
        )
        assert thread_response.status_code == 201, thread_response.text
        thread_id = str(thread_response.json()["id"])

        run_response = await e2e_client.post(
            f"/api/v1/agents/sessions/{thread_id}/events",
            headers={**e2e_headers, "Idempotency-Key": f"personal-skill-input-{uuid.uuid4().hex}"},
            json={
                "events": [
                    {
                        "type": "agent.session.input.message",
                        "input": [
                            {
                                "role": "user",
                                "content": [{"type": "input_text", "text": "请读取并返回 personal Skill marker。"}],
                            }
                        ],
                        "yuxi": {"mode": "follow_up"},
                    }
                ],
            },
        )
        assert run_response.status_code == 202, run_response.text
        consumed = await wait_for_consumed_input(e2e_client, e2e_headers, run_response.json())
        run_id, turn_id = consumed["run_id"], consumed["turn_id"]

        async def consume_output() -> int:
            """观察本 Run 的模型增量直到同一 Turn 终态。"""
            message_events = 0
            async for event in iter_public_thread_events(e2e_client, e2e_headers, thread_id):
                if event.get("yuxi", {}).get("run_id") == run_id and event["type"] == "agent.session.turn.output_text.delta":
                    message_events += 1
                if event.get("turn_id") == turn_id and event["type"] in {
                    "agent.session.turn.completed",
                    "agent.session.turn.failed",
                    "agent.session.turn.cancelled",
                }:
                    return message_events
            pytest.fail("个人 Skill 的 Thread SSE 在终态前断开")

        event_count = await asyncio.wait_for(consume_output(), timeout=RUN_TIMEOUT_SECONDS)
        assert event_count > 0, event_count
        turn_response = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/turns/{turn_id}", headers=e2e_headers)
        assert turn_response.status_code == 200, turn_response.text
        turn = turn_response.json()
        if turn["status"] != "completed":
            skip_if_external_quota((turn.get("error") or {}).get("message"))
        assert turn["status"] == "completed", turn
        assert turn["yuxi"]["result_run_id"] == run_id, turn

        assert marker in output_text(turn["yuxi"]["output"] or []), turn

        conn = await asyncpg.connect(postgres_dsn())
        try:
            raw_manifest = await conn.fetchval("SELECT manifest FROM agent_runs WHERE id = $1", run_id)
            manifest = json.loads(raw_manifest) if isinstance(raw_manifest, str) else raw_manifest
            assert slug in {item["slug"] for item in manifest["resources"]["skills"]}
        finally:
            await conn.close()

        personal_skill = user_workspace_dir(uid) / "agents" / "skills" / slug / "SKILL.md"
        assert personal_skill.read_text(encoding="utf-8") == skill_md
        projected_skill = get_user_skills_root_dir(uid) / slug / "SKILL.md"
        assert not projected_skill.exists()
    finally:
        if thread_id:
            await archive_public_thread(e2e_client, e2e_headers, thread_id, turn_id=turn_id)
            remove_e2e_thread_storage(thread_id)
        if agent_created:
            agent_delete = await e2e_client.delete(f"/api/agent/{agent_slug}", headers=e2e_headers)
            assert agent_delete.status_code in {200, 404}, agent_delete.text
        skill_delete = await e2e_client.delete(f"/api/skills/personal/{slug}", headers=e2e_headers)
        assert skill_delete.status_code in {200, 404}, skill_delete.text
