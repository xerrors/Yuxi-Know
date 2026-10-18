"""真实 HTTP、worker 与 PostgreSQL 验证畸形工具失败后的同会话继续。"""

import json
import uuid
from http.server import BaseHTTPRequestHandler

import asyncpg
import pytest

from test.e2e.e2e_helpers import (
    archive_public_thread,
    output_text,
    postgres_dsn,
    public_message,
    register_replay_provider,
    wait_for_consumed_input,
    wait_for_terminal_turn,
)
from test.live_api_cleanup import make_test_session_title
from test.support.openai_replay_server import send_openai_sse_response, serve_replay_handler

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio, pytest.mark.self_managed_resources, pytest.mark.timeout(180)]


async def test_malformed_tool_fails_and_same_session_can_continue(e2e_client, e2e_headers):
    """独立检查持久终态、checkpoint 原文和下一轮供应商实际接收的协议。"""
    suffix = uuid.uuid4().hex[:8]
    provider_id, slug = f"bad-tool-{suffix}", f"bad-tool-{suffix}"
    observed = []

    class Handler(BaseHTTPRequestHandler):
        """首次返回坏 JSON，第二轮拒绝任何不配对工具结果。"""

        def do_POST(self):
            """通过真实 OpenAI SSE 发送未经测试侧修补的模型响应。"""
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            observed.append(request["messages"])
            if len(observed) == 1:
                delta = {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "bad-json",
                            "type": "function",
                            "function": {"name": "write_file", "arguments": '{"path": invalid}'},
                        }
                    ],
                }
                finish = "tool_calls"
            else:
                if any(m.get("role") == "tool" for m in request["messages"]):
                    self.send_error(400, "orphan_tool_result")
                    return
                delta, finish = {"role": "assistant", "content": "SAME_SESSION_RECOVERED"}, "stop"
            common = {"id": "chatcmpl-malformed", "object": "chat.completion.chunk", "created": 1, "model": request["model"]}
            send_openai_sse_response(
                self,
                [
                    {**common, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                    {**common, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
                ],
            )

        def log_message(self, *_args):
            """请求内容不写日志。"""

    thread_id = turn_id = None
    with serve_replay_handler(Handler) as replay_url:
        try:
            await register_replay_provider(e2e_client, e2e_headers, base_url=replay_url, provider_id=provider_id)
            agent = await e2e_client.post(
                "/api/agent",
                headers=e2e_headers,
                json={
                    "name": slug,
                    "slug": slug,
                    "backend_id": "ChatbotAgent",
                    "visibility": "private",
                    "config_json": {
                        "context": {"model": f"{provider_id}:deterministic-chat", "tools": [], "knowledges": [], "mcps": [], "skills": []}
                    },
                },
            )
            assert agent.status_code == 200, agent.text
            created = await e2e_client.post(
                "/api/v1/agents/sessions",
                headers={**e2e_headers, "Idempotency-Key": str(uuid.uuid4())},
                json={
                    "agent_id": slug,
                    "input": "MALFORMED_TOOL_PROBE",
                    "title": make_test_session_title("malformed-tool"),
                },
            )
            assert created.status_code == 201, created.text
            thread_id = created.json()["id"]
            receipt = await wait_for_consumed_input(e2e_client, e2e_headers, created.json()["yuxi"]["receipt"])
            turn_id = receipt["turn_id"]
            failed = await wait_for_terminal_turn(e2e_client, e2e_headers, thread_id, turn_id)
            assert failed["status"] == "failed", failed
            assert "工具调用参数无效" in failed["error"]["message"]
            assert "write_file" in failed["error"]["message"]
            conn = await asyncpg.connect(postgres_dsn())
            try:
                run = await conn.fetchrow("SELECT status,error_message FROM agent_runs WHERE id=$1", receipt["run_id"])
                assert run["status"] == "failed" and "工具调用参数无效" in run["error_message"]
            finally:
                await conn.close()
            continued = await e2e_client.post(
                f"/api/v1/agents/sessions/{thread_id}/events",
                headers={**e2e_headers, "Idempotency-Key": str(uuid.uuid4())},
                json={
                    "events": [{"type": "agent.session.input.message", "input": [public_message("继续确认恢复")]}],
                },
            )
            assert continued.status_code == 202, continued.text
            receipt = await wait_for_consumed_input(e2e_client, e2e_headers, continued.json())
            turn_id = receipt["turn_id"]
            completed = await wait_for_terminal_turn(e2e_client, e2e_headers, thread_id, turn_id)
            assert completed["status"] == "completed", completed
            assert "SAME_SESSION_RECOVERED" in output_text(completed["yuxi"]["output"])
            assert len(observed) == 2
            assert "工具调用失败" in json.dumps(observed[1], ensure_ascii=False)
            assert not any(m.get("role") == "tool" for m in observed[1])
            from yuxi.infrastructure.postgres.checkpointer import get_langgraph_checkpointer
            from yuxi.infrastructure.postgres.manager import pg_manager

            pg_manager.initialize()
            saved = await get_langgraph_checkpointer(pg_manager).aget_tuple({"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}})
            messages = saved.checkpoint["channel_values"]["messages"]
            assert any(getattr(m, "invalid_tool_calls", []) for m in messages)
            assert any(getattr(m, "tool_call_id", None) == "bad-json" for m in messages)
        finally:
            if thread_id:
                await archive_public_thread(e2e_client, e2e_headers, thread_id, turn_id=turn_id)
            removed = await e2e_client.delete(f"/api/agent/{slug}", headers=e2e_headers)
            assert removed.status_code in {200, 404}, removed.text
            removed = await e2e_client.delete(f"/api/system/model-providers/{provider_id}", headers=e2e_headers)
            assert removed.status_code in {200, 404}, removed.text
