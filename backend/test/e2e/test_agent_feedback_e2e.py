"""真实 worker 自动提供改进标记工具，并验证记录与最终输出。"""

import asyncio
import json
import uuid
from http.server import ThreadingHTTPServer
from threading import Thread

import asyncpg
import pytest

from test.e2e.e2e_helpers import archive_public_thread, delete_agent, postgres_dsn, wait_for_consumed_input, wait_model_provider_cache
from test.live_api_cleanup import make_test_session_title
from test.support.openai_replay_server import ReplayHandler

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e, pytest.mark.slow, pytest.mark.timeout(180)]


@pytest.fixture
def feedback_replay_url():
    """启动独立 HTTP 模型重放，避免改变共享模型服务。"""
    server = ThreadingHTTPServer(("0.0.0.0", 0), ReplayHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://api:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("invalid_reason", [False, True])
async def test_worker_marks_own_run_without_skill_and_survives_tool_error(e2e_client, e2e_headers, feedback_replay_url, invalid_reason):
    """未选工具和 Skill 的正常 Run 能采集，空原因返回工具错误且仍完成原任务。"""
    provider_id = f"ci-feedback-{uuid.uuid4().hex[:8]}"
    slug = f"ci-feedback-agent-{uuid.uuid4().hex[:8]}"
    uid = str((await e2e_client.get("/api/auth/me", headers=e2e_headers)).json()["uid"])
    session_id = turn_id = None
    provider = await e2e_client.post(
        "/api/system/model-providers",
        headers=e2e_headers,
        json={
            "provider_id": provider_id,
            "display_name": "Feedback deterministic replay",
            "provider_type": "openai",
            "base_url": feedback_replay_url,
            "api_key": "ci-replay-key",
            "capabilities": ["chat"],
            "enabled_models": [{"id": "deterministic-chat", "display_name": "Replay", "type": "chat", "source": "manual"}],
            "is_enabled": True,
        },
    )
    assert provider.status_code == 200, provider.text
    agent_created = False
    try:
        await wait_model_provider_cache()
        agent = await e2e_client.post(
            "/api/agent",
            headers=e2e_headers,
            json={
                "name": "Feedback E2E",
                "slug": slug,
                "backend_id": "ChatbotAgent",
                "visibility": "shared",
                "config_json": {
                    "context": {
                        "model": f"{provider_id}:deterministic-chat",
                        "tools": [],
                        "knowledges": [],
                        "mcps": [],
                        "skills": [],
                        "preload_skills": [],
                    }
                },
                "share_config": {
                    "version": 2,
                    "read_scope": {"access_level": "user", "department_ids": [], "user_uids": [uid]},
                    "manage_scope": None,
                },
            },
        )
        assert agent.status_code == 200, agent.text
        agent_created = True
        created = await e2e_client.post(
            "/api/v1/agents/sessions",
            headers={**e2e_headers, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "agent_id": slug,
                "input": "DETERMINISTIC_AGENT_E2E_OK DETERMINISTIC_FEEDBACK" + ("_INVALID" if invalid_reason else ""),
                "title": make_test_session_title("feedback-worker"),
            },
        )
        assert created.status_code == 201, created.text
        session_id = created.json()["id"]
        consumed = await wait_for_consumed_input(e2e_client, e2e_headers, created.json()["yuxi"]["receipt"])
        turn_id = consumed["turn_id"]
        async with asyncio.timeout(90):
            while True:
                turn_response = await e2e_client.get(f"/api/v1/agents/sessions/{session_id}/turns/{turn_id}", headers=e2e_headers)
                assert turn_response.status_code == 200, turn_response.text
                turn = turn_response.json()
                if turn["status"] in {"completed", "failed", "cancelled"}:
                    break
                await asyncio.sleep(0.2)
        assert turn["status"] == "completed", turn
        run_id = turn["yuxi"]["result_run_id"]
        assert "DETERMINISTIC_AGENT_E2E_OK" in json.dumps(turn["yuxi"]["output"])
        conn = await asyncpg.connect(postgres_dsn())
        try:
            records = await conn.fetch(
                "SELECT f.*, r.uid, r.thread_id, r.turn_id FROM agent_feedback_records f "
                "JOIN agent_runs r ON r.id=f.run_id WHERE f.run_id=$1",
                run_id,
            )
            assert len(records) == (0 if invalid_reason else 1)
            if not invalid_reason:
                row = records[0]
                assert (row["source"], row["rating"], row["tool_call_id"], row["uid"], row["thread_id"], row["turn_id"]) == (
                    "agent",
                    None,
                    "call-improvement",
                    uid,
                    session_id,
                    turn_id,
                )
                assert row["reason"] == "多次尝试后确认批量读取更可靠；依据是本轮工具记录。"
                manifest = await conn.fetchval("SELECT manifest FROM agent_runs WHERE id=$1", run_id)
                assert json.loads(manifest)["resources"]["skills"] == []
            tool_fact = await conn.fetchrow(
                "SELECT execution_status, content FROM messages WHERE run_id=$1 AND message_type='tool_audit'", run_id
            )
            assert tool_fact and tool_fact["execution_status"] == ("failed" if invalid_reason else "completed")
            if not invalid_reason:
                assert records[0]["id"] in tool_fact["content"]
            else:
                assert "未保存" in tool_fact["content"]
        finally:
            await conn.close()
        feedback_path = f"/api/v1/agents/sessions/{session_id}/turns/{turn_id}/feedback"
        saved = await e2e_client.put(
            feedback_path, json={"run_id": run_id, "rating": "like", "reason": "工具调用后仍完成任务"}, headers=e2e_headers
        )
        assert saved.status_code == 200, saved.text
        page = await e2e_client.get(f"/api/v1/agents/sessions/{session_id}/feedback", headers=e2e_headers)
        assert {item["source"] for item in page.json()["items"]} == ({"user"} if invalid_reason else {"user", "agent"})
    finally:
        if session_id:
            await archive_public_thread(e2e_client, e2e_headers, session_id, turn_id=turn_id)
        if agent_created:
            await delete_agent(e2e_client, e2e_headers, slug)
        deleted = await e2e_client.delete(f"/api/system/model-providers/{provider_id}", headers=e2e_headers)
        assert deleted.status_code in {200, 404}, deleted.text
