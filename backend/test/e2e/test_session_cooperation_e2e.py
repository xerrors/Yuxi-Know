"""真实 API、worker、checkpoint 和共享沙盒的 Session 协作链。"""

import asyncio
import json
import sys
import uuid

import asyncpg
import pytest
from test.e2e.e2e_helpers import wait_for_consumed_input
from langchain_core.messages import ToolMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from test.e2e.e2e_helpers import archive_public_thread, delete_agent, postgres_dsn
from test.e2e.e2e_helpers import (
    create_lifecycle_agent as _agent,
    output_text,
    public_message as _message,
    register_replay_provider as _provider,
)
from test.live_api_cleanup import make_test_session_title
from yuxi.modules.workspace.paths import user_workspace_dir
from yuxi.modules.agents.runtime.sandbox import get_sandbox_provider, ProvisionerSandboxBackend
from yuxi.modules.agents.services.leases import release_idle_sandboxes
from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.bootstrap.models import load_models

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e, pytest.mark.slow, pytest.mark.timeout(240)]
OUTPUT = "DETERMINISTIC_AGENT_E2E_OK"
MODEL = "cooperation-replay:deterministic-chat"
TARGET_MODEL = "cooperation-target-replay:deterministic-chat"
SUMMARY_PROMPT = "COOPERATION_SUMMARY_FIXTURE\n{messages}"


@pytest.mark.parametrize(
    "parallel_question,select_agent,cancel_wait",
    [(False, False, False), (True, False, False), (False, True, False), (True, False, True), (False, False, True)],
)
async def test_sessions_use_public_state_and_shared_sandbox(e2e_client, e2e_headers, parallel_question, select_agent, cancel_wait):
    """根工具创建普通会话，结果通过持久等待返回，文件在同一 Project 中。"""
    me = await e2e_client.get("/api/auth/me", headers=e2e_headers)
    uid = me.json()["uid"]
    await _provider(e2e_client, e2e_headers, base_url="http://api:8766/v1", provider_id="cooperation-replay")
    slug = await _agent(
        e2e_client,
        e2e_headers,
        uid,
        model_spec=MODEL,
        tools=["ask_user_question"] if parallel_question else [],
        system_prompt_suffix="COOP_PARENT_CONFIG",
        summary_prompt=SUMMARY_PROMPT,
    )
    target_slug = None
    if select_agent:
        await _provider(e2e_client, e2e_headers, base_url="http://api:8766/v1", provider_id="cooperation-target-replay")
        target_slug = await _agent(
            e2e_client,
            e2e_headers,
            uid,
            model_spec=TARGET_MODEL,
            tools=["ask_user_question"],
            system_prompt_suffix="COOP_TARGET_CONFIG",
            summary_prompt=SUMMARY_PROMPT,
        )
        updated = await e2e_client.put(f"/api/agent/{target_slug}", headers=e2e_headers, json={"description": "COOP_TARGET_ROLE"})
        assert updated.status_code == 200, updated.text
    thread_id = turn_id = workdir = None
    conn = await asyncpg.connect(postgres_dsn())
    try:
        created = await e2e_client.post(
            "/api/v1/agents/sessions",
            headers={**e2e_headers, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "agent_id": slug,
                "title": make_test_session_title("session-cooperation"),
                "agent": {"model": MODEL},
                "tool_approval_mode": "always_trust",
            },
        )
        assert created.status_code == 201, created.text
        thread_id = created.json()["id"]
        root = await conn.fetchrow(
            "SELECT s.project_id, p.workdir_path FROM sessions s JOIN projects p ON p.id=s.project_id WHERE s.thread_id=$1",
            thread_id,
        )
        workdir = root["workdir_path"]
        path = f"/home/gem/user-data/{workdir}/cooperation.txt"
        runtime_probe = f"/tmp/cooperation-shared-{uuid.uuid4().hex}"
        question_marker = " PARALLEL_QUESTION" if parallel_question else ""
        selection_marker = f" SELECT_AGENT:{target_slug}" if select_agent else ""
        accepted = await e2e_client.post(
            f"/api/v1/agents/sessions/{thread_id}/events",
            headers={**e2e_headers, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "events": [
                    {
                        "type": "agent.session.input.message",
                        "input": [
                            _message(
                                f"{OUTPUT} PRIVATE_ROOT_HISTORY COOPERATION_ROOT:{path} "
                                f"COOP_RUNTIME:{runtime_probe}{question_marker}{selection_marker}"
                            )
                        ],
                        "yuxi": {"mode": "follow_up", "tool_approval_mode": "always_trust"},
                    }
                ]
            },
        )
        assert accepted.status_code == 202, accepted.text
        turn_id = (await wait_for_consumed_input(e2e_client, e2e_headers, accepted.json()))["turn_id"]
        # 包含父子执行与周期协作恢复，恢复相位可额外等待一分钟。
        async with asyncio.timeout(180):
            while True:
                response = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/turns/{turn_id}", headers=e2e_headers)
                assert response.status_code == 200, response.text
                turn = response.json()
                if (
                    (parallel_question or cancel_wait)
                    and turn["status"] == ("requires_action" if parallel_question else "in_progress")
                    and (turn["yuxi"]["waitpoint"] or {}).get("kind") == ("answer" if parallel_question else "cooperation")
                ):
                    await _assert_thread_activity(
                        e2e_client,
                        e2e_headers,
                        thread_id,
                        "requires_action" if parallel_question else "in_progress",
                    )
                    if cancel_wait:
                        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
                        async with AsyncPostgresSaver.from_conn_string(postgres_dsn()) as saver:
                            before = await saver.aget_tuple(config)
                            prior_messages = list(before.checkpoint["channel_values"]["messages"])
                            for _, channel, values in before.pending_writes or []:
                                if channel == "messages":
                                    prior_messages.extend(values if isinstance(values, list) else [values])
                            completed = [message for message in prior_messages if isinstance(message, ToolMessage)]
                            assert any(message.tool_call_id == "create-worker" for message in completed)
                            cancelled = await e2e_client.post(
                                f"/api/v1/agents/sessions/{thread_id}/events",
                                headers={**e2e_headers, "Idempotency-Key": str(uuid.uuid4())},
                                json={"events": [{"type": "agent.session.input.cancel", "yuxi": {"turn_id": turn_id}}]},
                            )
                            assert cancelled.status_code == 202, cancelled.text
                            snapshot = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/turns/{turn_id}", headers=e2e_headers)
                            assert snapshot.json()["status"] == "cancelled", snapshot.text
                            after = await saver.aget_tuple(config)
                            messages = after.checkpoint["channel_values"]["messages"]
                            assert all(message in messages for message in completed)
                            assert any(
                                isinstance(message, ToolMessage)
                                and message.tool_call_id == ("parallel-question" if parallel_question else "wait-worker")
                                and message.content == "[已取消]"
                                for message in messages
                            )
                            assert not any(channel == "__interrupt__" for _, channel, _ in after.pending_writes or [])
                        assert await conn.fetchval("SELECT result_run_id FROM agent_turns WHERE id=$1", turn_id) is None
                        return
                    resumed = await e2e_client.post(
                        f"/api/v1/agents/sessions/{thread_id}/events",
                        headers={**e2e_headers, "Idempotency-Key": str(uuid.uuid4())},
                        json={
                            "events": [
                                {
                                    "type": "yuxi.session.input.resume",
                                    "turn_id": turn_id,
                                    "waitpoint_id": turn["yuxi"]["waitpoint"]["id"],
                                    "response": {
                                        "type": "answer",
                                        "answers": [{"question_id": "confirm", "answer": "继续"}],
                                    },
                                }
                            ]
                        },
                    )
                    assert resumed.status_code == 202, resumed.text
                if turn["status"] in {"completed", "failed", "cancelled"}:
                    break
                await asyncio.sleep(0.2)
        assert turn["status"] == "completed", turn
        assert output_text(turn["yuxi"]["output"]) == OUTPUT
        assert await conn.fetchval("SELECT count(*) FROM sessions WHERE parent_thread_id=$1", thread_id) == 1
        child = await conn.fetchrow("SELECT * FROM sessions WHERE parent_thread_id=$1", thread_id)
        assert child and child["status"] == "active"
        assert child["tree_root_thread_id"] == thread_id and child["project_id"] == root["project_id"]
        run = await conn.fetchrow("SELECT * FROM agent_runs WHERE thread_id=$1 ORDER BY created_at DESC LIMIT 1", child["thread_id"])
        assert run["run_type"] == "chat" and run["runtime_scope_id"] == thread_id and run["status"] == "completed"
        snapshot = json.loads(child["config_snapshot"])
        payload = json.loads(run["input_payload"])
        assert json.loads(run["manifest"])["model"]["spec"] == (TARGET_MODEL if select_agent else MODEL)
        assert child["agent_id"] == run["agent_slug"] == (target_slug if select_agent else slug)
        assert payload["context_snapshot"]["model"] == (TARGET_MODEL if select_agent else MODEL)
        assert payload["context_snapshot"]["tool_approval_mode"] == "always_trust"
        assert "model_spec" not in payload and "tool_approval_mode" not in payload
        if select_agent:
            assert "COOP_TARGET_CONFIG" in snapshot["system_prompt"]
            assert "COOP_PARENT_CONFIG" not in snapshot["system_prompt"]
            assert snapshot["tools"] == ["ask_user_question"]
        else:
            assert "COOP_PARENT_CONFIG" in snapshot["system_prompt"]
        state = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/state", headers=e2e_headers)
        assert state.status_code == 200, state.text
        member = next(s for s in state.json()["agent_state"]["cooperation"]["sessions"] if s["session_id"] == child["thread_id"])
        assert "output" not in member and member["result_run_id"] == run["id"]
        assert (user_workspace_dir(uid) / root["workdir_path"] / "cooperation.txt").read_text() == "cooperation verified"
        child_turn = await e2e_client.get(f"/api/v1/agents/sessions/{child['thread_id']}/turns/{run['turn_id']}", headers=e2e_headers)
        assert child_turn.status_code == 200 and output_text(child_turn.json()["yuxi"]["output"]) == OUTPUT
        assert json.loads(child["config_snapshot"])["system_prompt"].count("用户工作区 agents/AGENTS.md") == 0
        provider = get_sandbox_provider()
        connection = await asyncio.to_thread(provider.get, thread_id, uid=uid, workdir_path=root["workdir_path"])
        assert connection is not None
        assert await asyncio.to_thread(provider.get, child["thread_id"], uid=uid, workdir_path=root["workdir_path"]) is None
        backend = ProvisionerSandboxBackend(thread_id=thread_id, uid=uid, workdir_path=root["workdir_path"])
        missing_path = path + ".missing.txt"
        for read_result in [await asyncio.to_thread(backend.read, missing_path), await backend.aread(missing_path)]:
            assert read_result.error == f"File '{missing_path}' not found"
            assert "ResponseFileReadResult" not in read_result.error and "validation errors" not in read_result.error
        assert (await asyncio.to_thread(backend.write, missing_path, "write then read verified")).error is None
        for read_result in [await asyncio.to_thread(backend.read, missing_path), await backend.aread(missing_path)]:
            assert read_result.error is None and read_result.file_data["content"] == "write then read verified"
        temporary = f"/tmp/cooperation-{uuid.uuid4().hex}"
        assert (await asyncio.to_thread(backend.execute, f"printf transient > {temporary}")).exit_code == 0
        # 压缩维护不能释放共享环境；根与成员均保留同一 /tmp 事实。
        for target in (thread_id, child["thread_id"]):
            compressed = await e2e_client.post(f"/api/v1/agents/sessions/{target}/compress", headers=e2e_headers)
            assert compressed.status_code == 200, compressed.text
            preserved = await asyncio.to_thread(backend.execute, f"cat {temporary}")
            assert preserved.exit_code == 0 and preserved.output == "transient"
            assert await asyncio.to_thread(provider.get, child["thread_id"], uid=uid, workdir_path=root["workdir_path"]) is None
        await conn.execute(
            "UPDATE session_cooperation_runtimes SET idle_since=now()-interval '6 minutes' WHERE tree_root_thread_id=$1",
            thread_id,
        )
        load_models()
        pg_manager.initialize()
        try:
            await release_idle_sandboxes()
        finally:
            await pg_manager.close()
        assert await conn.fetchval("SELECT released FROM session_cooperation_runtimes WHERE tree_root_thread_id=$1", thread_id)
        assert await asyncio.to_thread(provider.get, thread_id, uid=uid, workdir_path=root["workdir_path"]) is None
        rebuilt = await asyncio.to_thread(backend.execute, f"cat {path} && test ! -e {temporary}")
        assert rebuilt.exit_code == 0 and rebuilt.output == "cooperation verified"

    finally:
        await conn.close()
        if thread_id:
            members = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/state", headers=e2e_headers)
            assert members.status_code == 200, members.text
            for member in members.json()["agent_state"]["cooperation"]["sessions"]:
                if member["session_id"] != thread_id:
                    await archive_public_thread(e2e_client, e2e_headers, member["session_id"], turn_id=member["turn_id"])
            await archive_public_thread(e2e_client, e2e_headers, thread_id, turn_id=turn_id)
            if workdir is not None:
                await asyncio.to_thread(
                    get_sandbox_provider().release,
                    thread_id,
                    uid=uid,
                    workdir_path=workdir,
                    clear_cache_on_delete_failure=True,
                )
        await delete_agent(e2e_client, e2e_headers, slug)
        if target_slug is not None:
            await delete_agent(e2e_client, e2e_headers, target_slug)


@pytest.mark.parametrize("stop_tree", [False, True])
async def test_full_tree_capacity_control_and_sibling_tools(e2e_client, e2e_headers, stop_tree):
    """真实 worker 满槽等待推进；兄弟工具与持久整树控制不串轮次。"""
    from yuxi.modules.agents.services.cooperation import reconcile_stopped_trees

    me = await e2e_client.get("/api/auth/me", headers=e2e_headers)
    await _provider(e2e_client, e2e_headers, base_url="http://api:8766/v1", provider_id="cooperation-replay")
    slug = await _agent(e2e_client, e2e_headers, me.json()["uid"], model_spec=MODEL, summary_prompt=SUMMARY_PROMPT)
    conn = await asyncpg.connect(postgres_dsn())
    root_id = root_turn = gate_file = workdir = None

    async def event(thread_id, payload):
        """通过真实公开入口提交独立输入或控制。"""
        result = await e2e_client.post(
            f"/api/v1/agents/sessions/{thread_id}/events",
            headers={**e2e_headers, "Idempotency-Key": str(uuid.uuid4())},
            json={"events": [payload]},
        )
        assert result.status_code == 202, result.text
        return result.json()

    try:
        created = await e2e_client.post(
            "/api/v1/agents/sessions",
            headers={**e2e_headers, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "agent_id": slug,
                "title": make_test_session_title("cooperation-capacity"),
                "agent": {"model": MODEL},
                "tool_approval_mode": "always_trust",
            },
        )
        assert created.status_code == 201, created.text
        root_id = created.json()["id"]
        workdir = await conn.fetchval(
            "SELECT p.workdir_path FROM sessions s JOIN projects p ON p.id=s.project_id WHERE s.thread_id=$1", root_id
        )
        gate_file = user_workspace_dir(me.json()["uid"]) / workdir / "capacity-release"
        gate_path = f"/home/gem/user-data/{workdir}/capacity-release"
        accepted = await event(
            root_id,
            {
                "type": "agent.session.input.message",
                "input": [_message(f"COOP_CAPACITY_ROOT PRIVATE_ROOT_HISTORY CAP_GATE:{gate_path}")],
                "yuxi": {"mode": "follow_up", "tool_approval_mode": "always_trust"},
            },
        )
        root_turn = (await wait_for_consumed_input(e2e_client, e2e_headers, accepted))["turn_id"]
        async with asyncio.timeout(90):
            while True:
                observed = await conn.fetchrow(
                    "SELECT (SELECT count(*) FROM agent_runs WHERE runtime_scope_id=$1 "
                    "AND status IN ('running','cancel_requested') AND worker_id IS NOT NULL) AS active, "
                    "(SELECT status='waiting' FROM agent_turns WHERE id=$2) AS waiting, "
                    "(SELECT count(*) FROM agent_runs WHERE runtime_scope_id=$1 AND thread_id<>$1 "
                    "AND status='running' AND worker_id IS NOT NULL) AS children",
                    root_id,
                    root_turn,
                )
                assert observed["active"] <= 4
                if observed["children"] == 4 and observed["waiting"]:
                    break
                await asyncio.sleep(0.05)
        await _assert_thread_activity(e2e_client, e2e_headers, root_id, "in_progress")
        members = await conn.fetch(
            "SELECT thread_id,cooperation_path FROM sessions WHERE tree_root_thread_id=$1 ORDER BY cooperation_path",
            root_id,
        )
        assert len(members) == 6
        ready_file = gate_file.with_name(gate_file.name + "-ready")
        if not stop_tree:
            ready_file.write_text("released")
        queued = None
        if stop_tree:
            queued = await event(
                root_id,
                {
                    "type": "agent.session.input.message",
                    "input": [_message("COOP_CAPACITY_FOLLOWUP")],
                    "yuxi": {"mode": "follow_up", "tool_approval_mode": "always_trust"},
                },
            )
            assert queued["turn_id"] is None
            await event(root_id, {"type": "yuxi.session.tree.stop"})
            # 独立测试进程重读持久停止意图，与真实 worker 同时重复执行恢复。
            load_models()
            pg_manager.initialize()
            try:
                await reconcile_stopped_trees()
                await reconcile_stopped_trees()
            finally:
                await pg_manager.close()
            gate_file.write_text("released")
            ready_file.write_text("released")
        async with asyncio.timeout(90):
            while True:
                active = await conn.fetchval(
                    "SELECT count(*) FROM agent_runs WHERE runtime_scope_id=$1 "
                    "AND status IN ('running','cancel_requested') AND worker_id IS NOT NULL",
                    root_id,
                )
                assert active <= 4
                turns = await conn.fetch(
                    "SELECT id,status,thread_id FROM agent_turns WHERE thread_id=ANY($1::varchar[])",
                    [m["thread_id"] for m in members],
                )
                if turns and all(t["status"] in {"completed", "failed", "cancelled"} for t in turns):
                    break
                await asyncio.sleep(0.1)
        assert not any(t["status"] == "failed" for t in turns), turns
        if stop_tree:
            assert all(t["status"] == "cancelled" for t in turns)
            assert await conn.fetchval("SELECT stopped FROM session_cooperation_runtimes WHERE tree_root_thread_id=$1", root_id)
            assert await conn.fetchval("SELECT bool_and(queue_paused) FROM sessions WHERE tree_root_thread_id=$1", root_id)
            assert await conn.fetchval("SELECT status FROM agent_inputs WHERE id=$1", queued["input_id"]) == "pending"
            await _assert_thread_activity(e2e_client, e2e_headers, root_id, "cancelled")
            await event(root_id, {"type": "yuxi.session.tree.continue"})
            async with asyncio.timeout(60):
                while True:
                    resumed = await conn.fetchrow("SELECT turn_id,status FROM agent_inputs WHERE id=$1", queued["input_id"])
                    if (
                        resumed["turn_id"]
                        and await conn.fetchval("SELECT status FROM agent_turns WHERE id=$1", resumed["turn_id"]) == "completed"
                    ):
                        break
                    await asyncio.sleep(0.1)
            assert resumed["turn_id"] != root_turn
            assert await conn.fetchval("SELECT status FROM agent_turns WHERE id=$1", root_turn) == "cancelled"
        else:
            victim = next(m for m in members if m["cooperation_path"] == "/root/worker4")
            recipient = next(m for m in members if m["cooperation_path"] == "/root/worker1")
            assert next(t for t in turns if t["thread_id"] == victim["thread_id"])["status"] == "cancelled"
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM session_cooperation_events WHERE recipient_thread_id=$1 "
                    "AND kind='message' AND content='SIBLING_INFORMATION'",
                    recipient["thread_id"],
                )
                == 1
            )
            assert await conn.fetchval("SELECT count(*) FROM agent_inputs WHERE thread_id=$1", recipient["thread_id"]) == 2
            assert all(t["status"] == "completed" for t in turns if t["thread_id"] != victim["thread_id"])
    finally:
        body_error = sys.exception()
        if gate_file is not None:
            gate_file.write_text("released")
            gate_file.with_name(gate_file.name + "-ready").write_text("released")
        await conn.close()
        try:
            if root_id:
                state = await e2e_client.get(f"/api/v1/agents/sessions/{root_id}/state", headers=e2e_headers)
                assert state.status_code == 200, state.text
                for member in reversed(state.json()["agent_state"]["cooperation"]["sessions"]):
                    queue = await e2e_client.get(f"/api/v1/agents/sessions/{member['session_id']}/queue", headers=e2e_headers)
                    assert queue.status_code == 200, queue.text
                    for pending in queue.json()["inputs"]:
                        await event(
                            member["session_id"],
                            {"type": "yuxi.session.input.cancel_input", "input_id": pending["input_id"]},
                        )
                    try:
                        await archive_public_thread(e2e_client, e2e_headers, member["session_id"], turn_id=member["turn_id"])
                    except TimeoutError as error:
                        diagnostic = await asyncpg.connect(postgres_dsn())
                        try:
                            blockers = await diagnostic.fetch(
                                "SELECT id,status,worker_id,runtime_cleanup_pending FROM agent_runs "
                                "WHERE thread_id=$1 AND (status NOT IN "
                                "('completed','failed','cancelled','interrupted') "
                                "OR runtime_cleanup_pending)",
                                member["session_id"],
                            )
                            pending = await diagnostic.fetch(
                                "SELECT id,status,turn_id FROM agent_inputs WHERE thread_id=$1 AND status='pending'",
                                member["session_id"],
                            )
                        finally:
                            await diagnostic.close()
                        error.add_note(f"Archive blockers: session={member['session_id']}, runs={blockers}, pending={pending}")
                        raise
            if root_id and workdir is not None:
                await asyncio.to_thread(
                    get_sandbox_provider().release,
                    root_id,
                    uid=me.json()["uid"],
                    workdir_path=workdir,
                    clear_cache_on_delete_failure=True,
                )
            await delete_agent(e2e_client, e2e_headers, slug)
        except Exception as cleanup_error:
            if body_error is not None:
                body_error.add_note(f"测试清理另有失败: {cleanup_error}")
                raise body_error from cleanup_error
            raise


async def _assert_thread_activity(client, headers, thread_id, expected):
    """真实 HTTP 查看不改变 Turn 等待，列表与快照保持同一活动投影。"""
    detail = await client.get(f"/api/v1/agents/sessions/{thread_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    viewed = await client.post(f"/api/v1/agents/sessions/{thread_id}/viewed", headers=headers)
    assert viewed.status_code == 200, viewed.text
    for snapshot in (detail.json(), viewed.json()):
        assert snapshot["status"] == expected, snapshot
    listed = await client.get("/api/v1/agents/sessions", headers=headers, params={"limit": 100})
    assert listed.status_code == 200, listed.text
    thread = next(item for item in listed.json()["data"] if item["id"] == thread_id)
    assert thread["status"] == expected, thread


@pytest.fixture
async def cooperation_depth_two(e2e_client, e2e_headers):
    """显式设置测试深度并恢复原值，不依赖管理员当前配置。"""
    current = await e2e_client.get("/api/system/config", headers=e2e_headers)
    assert current.status_code == 200, current.text
    previous = current.json()["max_cooperation_depth"]
    try:
        changed = await e2e_client.post("/api/system/config/update", headers=e2e_headers, json={"max_cooperation_depth": 2})
        assert changed.status_code == 200, changed.text
        yield
    finally:
        restored = await e2e_client.post("/api/system/config/update", headers=e2e_headers, json={"max_cooperation_depth": previous})
        assert restored.status_code == 200, restored.text


async def test_worker_rejects_third_cooperation_depth_and_commits_only_allowed_members(e2e_client, e2e_headers, cooperation_depth_two):
    """真实 API、worker 与工具执行拒绝第三层，回读会话和输入确认无副作用。"""
    me = (await e2e_client.get("/api/auth/me", headers=e2e_headers)).json()
    await _provider(e2e_client, e2e_headers, base_url="http://api:8766/v1", provider_id="cooperation-replay")
    slug = await _agent(e2e_client, e2e_headers, me["uid"], model_spec=MODEL, tools=[])
    thread_id = turn_id = None
    conn = await asyncpg.connect(postgres_dsn())
    try:
        created = await e2e_client.post(
            "/api/v1/agents/sessions",
            headers={**e2e_headers, "Idempotency-Key": str(uuid.uuid4())},
            json={"agent_id": slug, "title": make_test_session_title("cooperation-depth"), "tool_approval_mode": "always_trust"},
        )
        assert created.status_code == 201, created.text
        thread_id = created.json()["id"]
        accepted = await e2e_client.post(
            f"/api/v1/agents/sessions/{thread_id}/events",
            headers={**e2e_headers, "Idempotency-Key": str(uuid.uuid4())},
            json={"events": [{"type": "agent.session.input.message", "input": [_message(f"{OUTPUT} COOP_DEPTH:0")]}]},
        )
        assert accepted.status_code == 202, accepted.text
        turn_id = (await wait_for_consumed_input(e2e_client, e2e_headers, accepted.json()))["turn_id"]
        async with asyncio.timeout(180):
            while True:
                turn = (await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/turns/{turn_id}", headers=e2e_headers)).json()
                if turn["status"] in {"completed", "failed", "cancelled"}:
                    break
                await asyncio.sleep(0.5)
        assert turn["status"] == "completed", turn
        assert output_text(turn["yuxi"]["output"]) == OUTPUT
        rows = await conn.fetch("SELECT thread_id, cooperation_path FROM sessions WHERE tree_root_thread_id=$1", thread_id)
        assert {row["cooperation_path"] for row in rows} == {"/root", "/root/depth-1", "/root/depth-1/depth-2"}
        count = await conn.fetchval("SELECT count(*) FROM agent_inputs WHERE thread_id=ANY($1::text[])", [row["thread_id"] for row in rows])
        assert count == 3
        statuses = await conn.fetch("SELECT status FROM agent_turns WHERE thread_id=ANY($1::text[])", [row["thread_id"] for row in rows])
        assert {row["status"] for row in statuses} == {"completed"}
        denied = await conn.fetchval(
            "SELECT count(*) FROM tool_calls t JOIN messages m ON m.id=t.message_id "
            "JOIN sessions s ON s.id=m.session_record_id WHERE s.tree_root_thread_id=$1 AND t.tool_name='create_session' "
            "AND t.status='error' AND coalesce(t.error_message,t.tool_output,'') LIKE '%协作深度 3%'",
            thread_id,
        )
        assert denied == 1
    finally:
        await conn.close()
        if thread_id:
            state = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/state", headers=e2e_headers)
            for member in state.json()["agent_state"]["cooperation"]["sessions"]:
                if member["session_id"] != thread_id:
                    await archive_public_thread(e2e_client, e2e_headers, member["session_id"], turn_id=member["turn_id"])
            await archive_public_thread(e2e_client, e2e_headers, thread_id, turn_id=turn_id)
        await delete_agent(e2e_client, e2e_headers, slug)
