"""真实 worker 验证 Agents Key 的终端用户与 APP 执行边界。"""

from __future__ import annotations

import uuid

import asyncpg
import pytest

from e2e_helpers import delete_agent, postgres_dsn
from test.e2e.e2e_helpers import output_text
from test.e2e.e2e_helpers import wait_for_consumed_input
from test.live_api_cleanup import (
    delete_test_session_resources,
    make_test_session_title,
    validate_test_runs_terminal,
)
from test.e2e.e2e_helpers import (
    DETERMINISTIC_MODEL as MODEL,
    DETERMINISTIC_OUTPUT as OUTPUT,
    create_lifecycle_agent as _agent,
    public_message as _message,
    register_replay_provider as _provider,
    wait_for_terminal_turn as _turn,
)
from yuxi.modules.workspace.paths import user_workspace_dir

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e, pytest.mark.slow, pytest.mark.timeout(240)]


async def _delete_key_thread(thread_id: str, *, app_id: str, end_user_id: str, other_end_user_id: str) -> None:
    """仅清理本测试创建的终端用户 Thread、隐式 Project 和无引用身份。"""
    await validate_test_runs_terminal({thread_id})
    conn = await asyncpg.connect(postgres_dsn())
    try:
        row = await conn.fetchrow(
            "SELECT c.uid, c.project_id, p.workdir_path, p.directory_mode, p.selection_status, "
            "u.user_kind, u.end_user_id, u.app_id, u.owner_user_id "
            "FROM sessions c JOIN projects p ON p.id = c.project_id AND p.uid = c.uid "
            "JOIN users u ON u.uid = c.uid WHERE c.thread_id = $1",
            thread_id,
        )
    finally:
        await conn.close()
    if row is None or (
        row["user_kind"] != "end_user"
        or row["end_user_id"] != end_user_id
        or row["app_id"] != app_id
        or row["directory_mode"] != "managed"
        or row["selection_status"] != "implicit"
    ):
        raise RuntimeError("终端用户测试清理拒绝非本测试的 Thread 或 Project")
    await delete_test_session_resources(
        {(row["uid"], row["workdir_path"]): {row["project_id"]}},
        {thread_id},
        {row["project_id"]},
    )
    conn = await asyncpg.connect(postgres_dsn())
    try:
        await conn.execute(
            "DELETE FROM users WHERE owner_user_id = $1 AND user_kind = 'end_user' "
            "AND end_user_id = ANY($2::text[]) AND app_id = $3 "
            "AND NOT EXISTS (SELECT 1 FROM sessions WHERE sessions.uid = users.uid) "
            "AND NOT EXISTS (SELECT 1 FROM projects WHERE projects.uid = users.uid)",
            row["owner_user_id"],
            [end_user_id, other_end_user_id, "__default__"],
            app_id,
        )
    finally:
        await conn.close()


async def test_private_agent_key_run_uses_end_user_workspace_and_app_scope(e2e_client, e2e_headers):
    """Key 执行的 Input、Turn、Run、输出与 Workdir 属于同一显式终端用户。"""
    me = await e2e_client.get("/api/auth/me", headers=e2e_headers)
    assert me.status_code == 200, me.text
    owner_uid = str(me.json()["uid"])
    await _provider(e2e_client, e2e_headers)
    slug = await _agent(e2e_client, e2e_headers, owner_uid, bound_skill=True)
    app_id = f"ci-key-{uuid.uuid4().hex[:12]}"
    end_user_id = f"visitor-{uuid.uuid4().hex}"
    other_end_user_id = f"other-{uuid.uuid4().hex}"
    key_id = thread_id = None
    public_headers = None
    try:
        key = await e2e_client.post(
            "/api/user/apikey/",
            headers=e2e_headers,
            json={
                "request_id": str(uuid.uuid4()),
                "name": "Lifecycle Key E2E",
                "access_level": "agents",
                "app_id": app_id,
            },
        )
        assert key.status_code == 200, key.text
        key_id = key.json()["api_key"]["id"]
        public_headers = {
            "Authorization": f"Bearer {key.json()['secret']}",
            "X-End-User-Id": end_user_id,
            "X-App-Id": "forged-app",
            "Idempotency-Key": f"key-run-{uuid.uuid4().hex}",
        }
        body = {
            "agent_id": slug,
            "title": make_test_session_title("lifecycle-key-worker"),
            "agent": {"model": MODEL},
            "input": [_message(OUTPUT)],
        }
        accepted = await e2e_client.post("/api/v1/agents/sessions", headers=public_headers, json=body)
        assert accepted.status_code == 201, accepted.text
        assert accepted.headers["X-App-Id"] == app_id
        receipt = await wait_for_consumed_input(e2e_client, public_headers, accepted.json()["yuxi"]["receipt"])
        thread_id = receipt["session_id"]
        replay = await e2e_client.post("/api/v1/agents/sessions", headers=public_headers, json=body)
        assert replay.status_code == 201, replay.text
        assert replay.json()["id"] == thread_id

        for headers in (
            {"Authorization": public_headers["Authorization"]},
            {**public_headers, "X-End-User-Id": other_end_user_id},
        ):
            hidden = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}", headers=headers)
            assert hidden.status_code == 404, hidden.text
            hidden_turn = await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/turns/{receipt['turn_id']}", headers=headers)
            assert hidden_turn.status_code == 404, hidden_turn.text

        completed = await _turn(e2e_client, public_headers, thread_id, receipt["turn_id"])
        assert completed["status"] == "completed", completed
        assert completed["yuxi"]["result_run_id"] == receipt["run_id"]
        assert OUTPUT in output_text(completed["yuxi"]["output"])
        conn = await asyncpg.connect(postgres_dsn())
        try:
            persisted = await conn.fetchrow(
                "SELECT u.uid, u.user_kind, u.end_user_id, c.uid AS thread_uid, "
                "p.uid AS project_uid, p.workdir_path, i.uid AS input_uid, i.app_id AS input_app_id, "
                "t.uid AS turn_uid, t.app_id AS turn_app_id, r.uid AS run_uid, "
                "r.app_id AS run_app_id, r.api_key_id, m.run_id AS output_run_id, "
                "m.turn_id AS output_turn_id, m.content AS output_content "
                "FROM sessions c JOIN users u ON u.uid = c.uid "
                "JOIN projects p ON p.id = c.project_id "
                "JOIN agent_inputs i ON i.thread_id = c.thread_id "
                "JOIN agent_turns t ON t.id = i.turn_id "
                "JOIN agent_runs r ON r.id = i.consumed_run_id "
                "JOIN messages m ON m.id = r.output_message_id "
                "WHERE c.thread_id = $1 AND i.id = $2 AND t.id = $3 AND r.id = $4",
                thread_id,
                receipt["input_id"],
                receipt["turn_id"],
                receipt["run_id"],
            )
        finally:
            await conn.close()
        assert persisted and persisted["user_kind"] == "end_user"
        assert persisted["end_user_id"] == end_user_id and persisted["uid"] != owner_uid
        assert len({persisted[key] for key in ("uid", "thread_uid", "project_uid", "input_uid", "turn_uid", "run_uid")}) == 1
        assert {persisted[key] for key in ("input_app_id", "turn_app_id", "run_app_id")} == {app_id}
        assert persisted["api_key_id"] == key_id
        assert persisted["output_run_id"] == receipt["run_id"]
        assert persisted["output_turn_id"] == receipt["turn_id"]
        assert OUTPUT in persisted["output_content"]
        workdir = user_workspace_dir(persisted["uid"]) / persisted["workdir_path"]
        assert workdir.is_dir()
        assert not (user_workspace_dir(owner_uid) / persisted["workdir_path"]).exists()
    finally:
        if thread_id and public_headers:
            archived = await e2e_client.post(f"/api/v1/agents/sessions/{thread_id}/archive", headers=public_headers)
            assert archived.status_code == 200, archived.text
            await _delete_key_thread(
                thread_id,
                app_id=app_id,
                end_user_id=end_user_id,
                other_end_user_id=other_end_user_id,
            )
        if key_id is not None:
            deleted = await e2e_client.delete(f"/api/user/apikey/{key_id}", headers=e2e_headers)
            assert deleted.status_code == 200, deleted.text
        await delete_agent(e2e_client, e2e_headers, slug)
        provider = await e2e_client.delete("/api/system/model-providers/ci-replay", headers=e2e_headers)
        assert provider.status_code in {200, 404}, provider.text
