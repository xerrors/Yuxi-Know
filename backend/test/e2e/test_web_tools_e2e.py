"""独立重放拓扑中的设置到真实 worker、消息与 SSE 链路。"""

import asyncio
import json
import os
import uuid

import asyncpg
import pytest

from test.e2e.e2e_helpers import (
    archive_public_thread,
    create_lifecycle_agent,
    delete_agent,
    postgres_dsn,
    register_replay_provider,
    wait_for_consumed_input,
    wait_for_terminal_turn,
)
from test.live_api_cleanup import make_test_session_title
from test.support.public_events import read_events

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e, pytest.mark.slow, pytest.mark.timeout(240)]


async def test_settings_switch_search_and_fetch_in_real_worker(e2e_client, e2e_headers):
    """不重启 API/worker，回读多次 Run 的供应商与正文持久事实。"""
    replay_url = os.getenv("WEB_TOOLS_REPLAY_URL")
    if not replay_url:
        pytest.skip("需要独立槽位叠加 backend/test/e2e/web-tools.compose.yml")
    client, headers = e2e_client, e2e_headers
    option_response = await client.get("/api/system/config/options", headers=headers)
    assert option_response.status_code == 200, option_response.text
    options = {option["key"]: option for option in option_response.json()["options"]}
    providers = ("tavily", "deepseek", "doubao")
    assert all(options[f"{provider}_search_opts"]["sensitive_state"]["api_key"]["source"] != "database" for provider in providers), (
        "请在没有已保存搜索 Key 的独立测试槽位执行"
    )
    defaults = (await client.get("/api/system/config", headers=headers)).json()
    uid = (await client.get("/api/auth/me", headers=headers)).json()["uid"]
    provider_id = f"ci-web-{uuid.uuid4().hex[:8]}"
    agent_slug = None
    threads = []
    try:
        await register_replay_provider(client, headers, base_url=replay_url, provider_id=provider_id)
        for provider in providers:
            saved = await client.put(
                f"/api/system/config/options/{provider}_search_opts", headers=headers, json={"value": {"api_key": f"replay-{provider}-key"}}
            )
            assert saved.status_code == 200, saved.text
        agent_slug = await create_lifecycle_agent(
            client, headers, uid, tools=["web_search", "web_fetch"], model_spec=f"{provider_id}:deterministic-chat"
        )
        for search_provider, fetch_provider in (("doubao", "deepseek"), ("deepseek", "tavily"), ("tavily", "deepseek")):
            saved = await client.post(
                "/api/system/config/update",
                headers=headers,
                json={"web_search_provider": search_provider, "web_fetch_provider": fetch_provider},
            )
            assert saved.status_code == 200, saved.text
            async with client.stream(
                "POST",
                "/api/v1/agents/sessions",
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                json={
                    "agent_id": agent_slug,
                    "title": make_test_session_title("web-tools"),
                    "input": f"EXPECT_SEARCH:{search_provider} EXPECT_FETCH:{fetch_provider}",
                    "stream": True,
                },
            ) as created:
                assert created.status_code == 201
                assert created.headers["content-type"].startswith("text/event-stream")
                events = read_events(created)
                _, first_event = await anext(events)
                assert first_event["type"] == "agent.session.created"
                session = first_event["session"]
                thread_id = session["id"]
                threads.append(thread_id)
                terminal = None
                async with asyncio.timeout(90):
                    async for _, event in events:
                        if event["type"] in {"agent.session.turn.completed", "agent.session.turn.failed", "agent.session.turn.cancelled"}:
                            terminal = event
                            break
                assert terminal and terminal["type"] == "agent.session.turn.completed", terminal
            consumed = await wait_for_consumed_input(client, headers, session["yuxi"]["receipt"])
            turn = await wait_for_terminal_turn(client, headers, thread_id, consumed["turn_id"])
            assert turn["status"] == "completed", turn
            assert "WEB_TOOLS_E2E_OK" in json.dumps(turn["yuxi"]["output"])
            run_id = turn["yuxi"]["result_run_id"]
            conn = await asyncpg.connect(postgres_dsn())
            try:
                records = await conn.fetch(
                    "SELECT extra_metadata->>'tool_name' AS tool_name, execution_status, "
                    "extra_metadata->'output'->>'content' AS output "
                    "FROM messages WHERE run_id=$1 AND message_type='tool_audit'",
                    run_id,
                )
                facts = {row["tool_name"]: json.loads(row["output"]) for row in records if row["tool_name"] in {"web_search", "web_fetch"}}
                assert all(row["execution_status"] == "completed" for row in records)
                assert facts["web_search"]["provider"] == search_provider
                assert facts["web_search"]["results"][0]["relevant_content"] == "REPLAY_RELEVANT"
                assert facts["web_fetch"]["provider"] == fetch_provider
                assert facts["web_fetch"]["content"] == "# REPLAY_FETCH_BODY"
            finally:
                await conn.close()
    finally:
        for thread in threads:
            await archive_public_thread(client, headers, thread)
        if agent_slug:
            await delete_agent(client, headers, agent_slug)
        await client.delete(f"/api/system/model-providers/{provider_id}", headers=headers)
        for provider in providers:
            restored = await client.put(
                f"/api/system/config/options/{provider}_search_opts", headers=headers, json={"value": {"api_key": ""}}
            )
            assert restored.status_code == 200, restored.text
        # 先清除选择，环境变量仍按正常优先级解析；有环境凭据的旧默认才可恢复。
        restored = await client.post(
            "/api/system/config/update", headers=headers, json={"web_search_provider": "", "web_fetch_provider": ""}
        )
        assert restored.status_code == 200, restored.text
        previous = {key: defaults[key] for key in ("web_search_provider", "web_fetch_provider") if defaults.get(key)}
        if previous:
            restored = await client.post("/api/system/config/update", headers=headers, json=previous)
            assert restored.status_code == 200, restored.text
