"""协作重放器的摘要协议与普通请求拒绝边界。"""

import json
import shlex
import subprocess
from http.server import ThreadingHTTPServer
from threading import Thread

import httpx
import pytest

from test.support.cooperation_replay_server import CooperationReplayHandler, parallel_wait_completion

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


@pytest.mark.parametrize("path", ["/tmp/fixture", "/home/user/workspace/projects/fixture/shared-probe"])
def test_cooperation_probe_uses_submitted_shared_path(path):
    """父子执行探针使用提交路径，不假定跨 Run 一定共享 VM 临时目录。"""
    serialized = f"COOPERATION_ROOT:/fixture.txt COOP_RUNTIME:{path}"
    parent = CooperationReplayHandler.shared_sandbox_calls(None, serialized, False, {})
    child = CooperationReplayHandler.shared_sandbox_calls(None, f"COOPERATION_CHILD:/fixture.txt COOP_RUNTIME:{path}", True, {})

    assert parent == [("root-prepare", "execute", {"command": f"printf shared > {path}"})]
    assert child[0] == ("child-probe", "execute", {"command": f"test -f {path} && printf shared_runtime_verified"})
    with pytest.raises(AssertionError, match="did not read"):
        CooperationReplayHandler.shared_sandbox_calls(None, serialized, True, {"child-write": "written", "child-probe": "missing"})


def test_parallel_wait_replay_emits_both_wait_calls_in_one_response(replay_url):
    """重放响应包含两个等待调用，不能退化成串行单等待而掩盖执行缺陷。"""
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
                {"role": "user", "content": "COOP_PARALLEL_WAIT_ROOT WAIT_GATE:/fixture-gate"},
                {"role": "tool", "tool_call_id": "parallel-create-0", "content": '{"input_id":"input-0"}'},
                {"role": "tool", "tool_call_id": "parallel-create-1", "content": '{"input_id":"input-1"}'},
            ],
        },
    )
    assert response.status_code == 200
    chunks = [json.loads(line.removeprefix("data: ")) for line in response.text.splitlines() if line.startswith("data: {")]
    calls = chunks[0]["choices"][0]["delta"]["tool_calls"]
    assert [(call["id"], call["function"]["name"], json.loads(call["function"]["arguments"])) for call in calls] == [
        ("parallel-wait-0", "wait_inputs", {"input_ids": ["input-0"], "timeout_seconds": 180}),
        ("parallel-wait-1", "wait_inputs", {"input_ids": ["input-1"], "timeout_seconds": 180}),
    ]


@pytest.mark.parametrize("mutation", ["input_id", "output", "terminal", "wait_timed_out"])
def test_parallel_wait_replay_rejects_wrong_or_unfinished_results(mutation):
    """精确结果 oracle 拒绝串任务、未完成和超时结果。"""
    messages = [{"role": "user", "content": "COOP_PARALLEL_WAIT_ROOT WAIT_GATE:/fixture-gate"}]
    results = {}
    for index in range(2):
        results[f"parallel-create-{index}"] = json.dumps({"input_id": f"input-{index}"})
        results[f"parallel-wait-{index}"] = json.dumps(
            {
                "results": [{"input_id": f"input-{index}", "output": f"PARALLEL_CHILD_RESULT_{index}", "terminal": True}],
                "wait_timed_out": False,
            }
        )
    assert parallel_wait_completion(messages, results)[0] == []
    changed = json.loads(results["parallel-wait-1"])
    if mutation == "wait_timed_out":
        changed["wait_timed_out"] = True
    else:
        changed["results"][0][mutation] = {"input_id": "input-0", "output": "PARALLEL_CHILD_RESULT_0", "terminal": False}[mutation]
    results["parallel-wait-1"] = json.dumps(changed)
    with pytest.raises(AssertionError):
        parallel_wait_completion(messages, results)


@pytest.mark.parametrize("index", [0, 1])
def test_parallel_child_gate_publishes_started_and_preserves_own_result(tmp_path, index):
    """子任务实际命令使用自己的 gate、原子 started 文件和独立结果。"""
    gate = tmp_path / "parallel-gate"
    gate.with_name(f"{gate.name}-{index}").write_text("released")
    messages = [{"role": "user", "content": f"COOP_PARALLEL_WAIT_CHILD:{index} WAIT_GATE:{gate}"}]
    calls, output = parallel_wait_completion(messages, {})
    completed = subprocess.run(shlex.split(calls[0][2]["command"]), check=True, capture_output=True, text=True, timeout=5)
    assert (tmp_path / f"parallel-gate-{index}-started").read_text() == "started"
    assert completed.stdout.strip() == output == f"PARALLEL_CHILD_RESULT_{index}"
    assert parallel_wait_completion(messages, {"parallel-delay": completed.stdout}) == ([], output)
