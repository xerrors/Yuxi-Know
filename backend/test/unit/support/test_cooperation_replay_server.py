"""协作重放器的摘要协议与普通请求拒绝边界。"""

import json
from http.server import ThreadingHTTPServer
from threading import Thread

import httpx
import pytest

from test.support.cooperation_replay_server import CooperationReplayHandler

pytestmark = pytest.mark.unit


@pytest.fixture()
def replay_url():
    """启动仅接受测试请求的本地 HTTP 重放器。"""
    server = ThreadingHTTPServer(("127.0.0.1", 0), CooperationReplayHandler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
    finally:
        server.shutdown()
        worker.join(timeout=2)
        server.server_close()


def test_summary_request_returns_nonstream_completion(replay_url):
    """主动压缩的明确摘要场景无需 tools，返回真实 JSON completion。"""
    response = httpx.post(
        replay_url,
        headers={"Authorization": "Bearer ci-replay-key"},
        json={
            "model": "deterministic-chat",
            "stream": False,
            "messages": [{"role": "user", "content": "COOPERATION_SUMMARY_FIXTURE\n<message>history</message>"}],
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "COOPERATION_SUMMARY_OK"
    assert body["choices"][0]["finish_reason"] == "stop"


@pytest.mark.parametrize(
    "authorization,stream,content,error",
    [
        ("Bearer wrong-key", False, "COOPERATION_SUMMARY_FIXTURE\nhistory", "authorization"),
        ("Bearer ci-replay-key", True, "COOPERATION_SUMMARY_FIXTURE\nhistory", "uniform tools missing"),
        ("Bearer ci-replay-key", False, "ordinary model request", "model contract"),
    ],
)
def test_summary_branch_does_not_accept_invalid_normal_requests(replay_url, authorization, stream, content, error):
    """摘要 fixture 不放宽鉴权或普通工具调用的契约。"""
    response = httpx.post(
        replay_url,
        headers={"Authorization": authorization},
        json={
            "model": "deterministic-chat",
            "stream": stream,
            "tools": [],
            "messages": [{"role": "user", "content": content}],
        },
    )
    assert response.status_code == 422
    assert response.json()["error"] == error


@pytest.mark.parametrize("role_prompt", ["", "COOP_PARENT_CONFIG", "COOP_TARGET_CONFIG COOP_PARENT_CONFIG"])
def test_selected_child_replay_rejects_wrong_agent_configuration(replay_url, role_prompt):
    """即使协作工具齐全，选择后仍继承父角色也必须让 E2E 重放失败。"""
    response = httpx.post(
        replay_url,
        headers={"Authorization": "Bearer ci-replay-key"},
        json={
            "model": "deterministic-chat",
            "stream": True,
            "tools": [
                {"type": "function", "function": {"name": name}}
                for name in (
                    "create_session",
                    "send_message",
                    "submit_input",
                    "cancel_turn",
                    "wait_sessions",
                    "wait_inputs",
                    "get_result",
                    "list_sessions",
                    "list_agents",
                )
            ],
            "messages": [
                {"role": "system", "content": role_prompt},
                {
                    "role": "user",
                    "content": "SELECTED_AGENT_CHILD COOPERATION_CHILD:/fixture.txt COOP_RUNTIME:/tmp/fixture",
                },
            ],
        },
    )
    assert response.status_code == 422
    assert response.json()["error"] == "selected agent configuration missing"


def test_replay_selects_agent_id_from_directory_result():
    """选择过程消费真实工具结果，不能把会话名称当成 Agent 身份。"""
    calls = CooperationReplayHandler.shared_sandbox_calls(
        None,
        "SELECT_AGENT:target-slug COOPERATION_ROOT:/fixture.txt COOP_RUNTIME:/tmp/fixture",
        False,
        {
            "root-prepare": "prepared",
            "agent-directory": json.dumps(
                {
                    "agents": [
                        {"id": "stale-target", "description": "COOP_TARGET_ROLE"},
                        {"id": "target-slug", "description": "COOP_TARGET_ROLE"},
                    ]
                }
            ),
        },
    )
    assert calls[0][1] == "create_session"
    assert calls[0][2]["name"] == "worker"
    assert calls[0][2]["agent_id"] == "target-slug"
    assert "SELECTED_AGENT_CHILD" in calls[0][2]["description"]
