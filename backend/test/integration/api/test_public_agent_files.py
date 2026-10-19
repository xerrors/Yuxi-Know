"""真实 HTTP 验证文件草稿、私有预处理与隔离。"""

import asyncio
import io
import os
import uuid

import asyncpg
import httpx
import pytest
from PIL import Image

from test.e2e.e2e_helpers import (
    DETERMINISTIC_OUTPUT,
    archive_public_thread,
    create_lifecycle_agent,
    delete_agent,
    public_message,
    register_replay_provider,
    wait_for_consumed_input,
    wait_for_terminal_turn,
)
from test.live_api_cleanup import make_test_session_title
from yuxi.infrastructure.minio import get_minio_client
from test.integration.api.helpers import delete_created_threads

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_submission_files_snapshot_idempotency_cancel_and_delete(test_client, standard_user, admin_headers):
    """真实 HTTP 回读提交级文件、原始引用和不可变取消回执。"""
    headers = standard_user["headers"]
    conn = await asyncpg.connect(os.environ["POSTGRES_URL"].replace("+asyncpg", ""))
    thread_id = None
    turn_id = input_id = slug = None
    gate = uuid.uuid4().hex
    replay = httpx.AsyncClient(base_url=os.environ["OPENAI_REPLAY_URL"].removesuffix("/v1"), timeout=5)
    files = []
    try:
        await register_replay_provider(test_client, admin_headers)
        slug = await create_lifecycle_agent(
            test_client,
            admin_headers,
            str(standard_user["user"]["uid"]),
            bound_skill=True,
        )
        for name in ("first.txt", "second.txt"):
            response = await test_client.post("/api/v1/agents/files", headers=headers, files={"file": (name, name.encode(), "text/plain")})
            assert response.status_code == 201, response.text
            files.append(response.json()["id"])
        invalid = await test_client.post(
            "/api/v1/agents/sessions",
            headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
            json={"agent_id": "default-chatbot", "yuxi": {"attachment_file_ids": files}},
        )
        assert invalid.status_code == 422, invalid.text
        assert await conn.fetchval("SELECT count(*) FROM agent_attachments WHERE id=ANY($1::text[]) AND input_id IS NOT NULL", files) == 0
        created = await test_client.post(
            "/api/v1/agents/sessions",
            headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
            json={
                "agent_id": slug,
                "title": make_test_session_title("file-snapshot"),
                "input": [public_message(f"{DETERMINISTIC_OUTPUT} DETERMINISTIC_BLOCK_BEFORE_RESPONSE:{gate}")],
            },
        )
        assert created.status_code == 201, created.text
        thread_id = created.json()["id"]
        consumed = await wait_for_consumed_input(test_client, headers, created.json()["yuxi"]["receipt"])
        turn_id = consumed["turn_id"]
        async with asyncio.timeout(30):
            while not (await replay.get("/blocking-started", params={"token": gate})).json()["started"]:
                await asyncio.sleep(0.1)
        url = f"/api/v1/agents/sessions/{thread_id}/events"
        key_headers = {**headers, "Idempotency-Key": uuid.uuid4().hex}
        messages = [{"role": "user", "content": [{"type": "input_text", "text": text}]} for text in ("one", "two")]
        event = {"type": "agent.session.input.message", "input": messages, "yuxi": {"mode": "follow_up", "attachment_file_ids": files}}
        old = await test_client.post(
            url, headers=key_headers, json={"events": [{**event, "input": [{**messages[0], "yuxi": {"attachment_file_ids": files}}]}]}
        )
        assert old.status_code == 422, old.text
        response = await test_client.post(url, headers=key_headers, json={"events": [event]})
        assert response.status_code == 202, response.text
        receipt = response.json()
        input_id = receipt["input_id"]
        assert receipt["turn_id"] is None and receipt["run_id"] is None
        repeated = await test_client.post(url, headers=key_headers, json={"events": [event]})
        assert repeated.json() == receipt
        changed = await test_client.post(
            url, headers=key_headers, json={"events": [{**event, "yuxi": {"mode": "follow_up", "attachment_file_ids": files[::-1]}}]}
        )
        assert changed.status_code == 409, changed.text
        input_url = f"/api/v1/agents/sessions/{thread_id}/inputs/{receipt['input_id']}"
        pending = (await test_client.get(input_url, headers=headers)).json()
        assert pending["items"] == [] and pending["status"] == "pending"
        assert pending["attachment_file_ids"] == files and len(pending["messages"]) == 2
        assert {item["file_id"] for item in pending["attachments"]} == set(files)
        assert all(item["message_id"] is None and "input_position" not in item for item in pending["attachments"])
        cancelled = await test_client.post(
            url,
            headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
            json={"events": [{"type": "yuxi.session.input.cancel_input", "input_id": receipt["input_id"]}]},
        )
        assert cancelled.status_code == 202, cancelled.text
        blocked = await test_client.delete(f"/api/v1/agents/sessions/{thread_id}/attachments/{files[0]}", headers=headers)
        assert blocked.status_code == 409, blocked.text
        await replay.get("/release-blocking", params={"token": gate})
        assert (await wait_for_terminal_turn(test_client, headers, thread_id, turn_id))["status"] == "completed"
        async with asyncio.timeout(30):
            while True:
                run = await conn.fetchrow("SELECT status, runtime_cleanup_pending FROM agent_runs WHERE id=$1", consumed["run_id"])
                assert run is not None and run["status"] == "completed"
                if not run["runtime_cleanup_pending"]:
                    break
                await asyncio.sleep(0.1)
        for file_id in files:
            deleted = await test_client.delete(f"/api/v1/agents/sessions/{thread_id}/attachments/{file_id}", headers=headers)
            assert deleted.status_code == 200, deleted.text
        snapshot = (await test_client.get(input_url, headers=headers)).json()
        assert snapshot["status"] == "cancelled" and snapshot["items"] == [] and snapshot["attachments"] == []
        assert snapshot["attachment_file_ids"] == files and snapshot["messages"] == pending["messages"]
        recovered = await test_client.get(
            f"/api/v1/agents/sessions/{thread_id}/receipt", headers=headers, params={"idempotency_key": key_headers["Idempotency-Key"]}
        )
        assert recovered.json() == receipt
        assert await conn.fetchval("SELECT count(*) FROM messages WHERE source_input_id=$1", receipt["input_id"]) == 0
    finally:
        if thread_id and input_id and await conn.fetchval("SELECT status FROM agent_inputs WHERE id=$1", input_id) == "pending":
            cancelled = await test_client.post(
                f"/api/v1/agents/sessions/{thread_id}/events",
                headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
                json={"events": [{"type": "yuxi.session.input.cancel_input", "input_id": input_id}]},
            )
            assert cancelled.status_code == 202, cancelled.text
        await replay.get("/release-blocking", params={"token": gate})
        if thread_id:
            await archive_public_thread(test_client, headers, thread_id, turn_id=turn_id)
            await delete_created_threads(thread_id)
        for file_id in files:
            await test_client.delete(f"/api/v1/agents/files/{file_id}", headers=headers)
        if slug:
            await delete_agent(test_client, admin_headers, slug)
        await replay.aclose()
        await conn.close()


async def test_draft_upload_does_not_create_session_and_deletes_original(test_client, standard_user, admin_headers):
    """上传无会话副作用，服务端引用守住所有用户读写入口。"""
    headers = standard_user["headers"]
    uid = str(standard_user["user"]["uid"])
    conn = await asyncpg.connect(os.environ["POSTGRES_URL"].replace("+asyncpg", ""))
    storage = get_minio_client()
    bucket = storage.KB_BUCKETS["documents"]
    file_id = None
    try:
        before = await conn.fetchval("SELECT count(*) FROM sessions WHERE uid=$1", uid)
        uploaded = await test_client.post(
            "/api/v1/agents/files", headers=headers, files={"file": ("draft.txt", b"draft bytes", "text/plain")}
        )
        assert uploaded.status_code == 201, uploaded.text
        file = uploaded.json()
        file_id = file["id"]
        assert file["object"] == "file" and file["status"] == "draft"
        assert file["filename"] == "draft.txt" and file["bytes"] == 11
        assert file["mime_type"] == "text/plain"
        assert not {"path", "object_name", "parsed_object_name", "session_id", "parse_methods"} & file.keys()
        assert await conn.fetchval("SELECT count(*) FROM sessions WHERE uid=$1", uid) == before
        record = await conn.fetchrow("SELECT * FROM agent_attachments WHERE id=$1", file_id)
        assert record["uid"] == uid and record["status"] == "draft"
        assert record["input_id"] is None and record["message_id"] is None
        assert record["filename"] == "draft.txt" and record["mime_type"] == "text/plain"
        assert record["size_bytes"] == 11
        assert "input_position" not in record
        assert await storage.adownload_file(bucket, record["object_name"]) == b"draft bytes"
        assert {item["object_name"] for item in await storage.alist_object_metadata(bucket, f"tmp/chat_attachments/{uid}/{file_id}/")} == {
            record["object_name"]
        }
        assert (await test_client.get(f"/api/v1/agents/files/{file_id}", headers=headers)).json() == file
        for method, path, kwargs in (
            ("GET", f"/api/v1/agents/files/{file_id}", {}),
            ("DELETE", f"/api/v1/agents/files/{file_id}", {}),
            ("POST", f"/api/agent/files/{file_id}/parse", {"json": {"parse_method": "disable"}}),
        ):
            response = await test_client.request(method, path, headers=admin_headers, **kwargs)
            assert response.status_code == 404, response.text
        deleted = await test_client.delete(f"/api/v1/agents/files/{file_id}", headers=headers)
        assert deleted.json() == {"id": file_id, "object": "file.deleted", "deleted": True}
        assert await conn.fetchrow("SELECT id FROM agent_attachments WHERE id=$1", file_id) is None
        assert await storage.alist_object_metadata(bucket, f"tmp/chat_attachments/{uid}/{file_id}/") == []
    finally:
        if file_id:
            await storage.adelete_objects_by_prefix(bucket, f"tmp/chat_attachments/{uid}/{file_id}/")
        await conn.close()


@pytest.mark.parametrize("level", ["full", "agents"])
async def test_public_keys_cannot_use_private_preprocessing_or_cross_app_drafts(test_client, admin_headers, api_key_factory, level):
    """Full Key 也不能绕过产品 JWT 边界；可信 APP 前缀隔离文件。"""
    files = []
    try:
        keys = []
        for index in range(2):
            body = {"request_id": str(uuid.uuid4()), "name": "Draft boundary", "access_level": level}
            if level == "agents":
                body["app_id"] = f"draft-app-{uuid.uuid4().hex[:8]}-{index}"
            created = await api_key_factory(body)
            keys.append(created.headers)
        source = io.BytesIO()
        Image.new("RGB", (2, 2), "red").save(source, format="PNG")
        uploaded = await test_client.post(
            "/api/v1/agents/files", headers=keys[0], files={"file": ("image.png", source.getvalue(), "image/png")}
        )
        assert uploaded.status_code == 201, uploaded.text
        file_id = uploaded.json()["id"]
        files.append((keys[0], file_id))
        for path, kwargs in (
            ("/api/agent/images", {"files": {"file": ("image.png", source.getvalue(), "image/png")}}),
            (f"/api/agent/files/{file_id}/parse", {"json": {"parse_method": "rapid_ocr"}}),
        ):
            denied = await test_client.post(path, headers=keys[0], **kwargs)
            assert denied.status_code == 403, denied.text
        if level == "agents":
            for headers in (keys[1], admin_headers):
                hidden = await test_client.get(f"/api/v1/agents/files/{file_id}", headers=headers)
                assert hidden.status_code == 404, hidden.text
    finally:
        for headers, file_id in files:
            response = await test_client.delete(f"/api/v1/agents/files/{file_id}", headers=headers)
            assert response.status_code in {200, 404}, response.text


async def test_public_preprocessing_and_confirm_routes_are_removed(test_client, admin_headers):
    """旧入口确实不可调用，OpenAPI 不再公开预处理协议。"""
    for path in (
        "/api/v1/agents/images",
        "/api/v1/agents/attachments/tmp",
        "/api/v1/agents/attachments/tmp/parse",
        f"/api/v1/agents/sessions/{uuid.uuid4()}/attachments/confirm",
    ):
        response = await test_client.post(path, headers=admin_headers, json={})
        assert response.status_code in {404, 405}, response.text
    paths = (await test_client.get("/openapi.json")).json()["paths"]
    assert "/api/v1/agents/files" in paths
    assert "/api/agent/images" in paths
    assert "/api/agent/files/{file_id}/parse" in paths
    assert not any("/attachments/tmp" in path or path.endswith("/attachments/confirm") for path in paths)
    assert "/api/v1/agents/images" not in paths


async def test_expired_draft_cleanup_is_bounded_and_keeps_live_drafts(test_client, admin_headers, api_key_factory):
    """行状态决定清理范围，32 行之后的过期草稿下一次继续清理。"""
    from yuxi.modules.agents.services.attachments import _tmp_attachment_owner

    app_id = f"cleanup-{uuid.uuid4().hex}"
    issued = await api_key_factory(
        {"request_id": str(uuid.uuid4()), "name": "Draft row cleanup", "access_level": "agents", "app_id": app_id}
    )
    headers = issued.headers
    conn = await asyncpg.connect(os.environ["POSTGRES_URL"].replace("+asyncpg", ""))
    storage = get_minio_client()
    bucket = storage.KB_BUCKETS["documents"]
    ids = []
    prefix = None
    try:
        anchor = await test_client.post("/api/v1/agents/files", headers=headers, files={"file": ("anchor.txt", b"live", "text/plain")})
        assert anchor.status_code == 201, anchor.text
        ids.append(anchor.json()["id"])
        row = await conn.fetchrow("SELECT uid,app_id FROM agent_attachments WHERE id=$1", anchor.json()["id"])
        uid = row["uid"]
        assert row["app_id"] == app_id
        prefix = f"tmp/chat_attachments/{_tmp_attachment_owner(uid, app_id)}/"
        for index in range(33):
            file_id = uuid.uuid4().hex
            ids.append(file_id)
            object_name = f"{prefix}{file_id}/original.txt"
            await storage.aupload_file(bucket, object_name, b"expired", content_type="text/plain")
            await conn.execute(
                "INSERT INTO agent_attachments "
                "(id,uid,app_id,filename,mime_type,size_bytes,created_at,expires_at,status,object_name) "
                "VALUES ($1,$2,$3,'expired.txt','text/plain',7,now(),now()-interval '1 day','draft',$4)",
                file_id,
                uid,
                app_id,
                object_name,
            )
        for remaining in [1, 0]:
            uploaded = await test_client.post("/api/v1/agents/files", headers=headers, files={"file": ("live.txt", b"live", "text/plain")})
            assert uploaded.status_code == 201, uploaded.text
            ids.append(uploaded.json()["id"])
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM agent_attachments WHERE uid=$1 AND app_id=$2 AND expires_at < now()",
                    uid,
                    app_id,
                )
                == remaining
            )
        assert await conn.fetchval("SELECT count(*) FROM agent_attachments WHERE uid=$1 AND app_id=$2 AND status='draft'", uid, app_id) == 3
        names = {item["object_name"] for item in await storage.alist_object_metadata(bucket, prefix)}
        assert len(names) == 3 and all("manifest" not in name for name in names)
    finally:
        if prefix:
            await storage.adelete_objects_by_prefix(bucket, prefix)
        if ids:
            await conn.execute("DELETE FROM agent_attachments WHERE id=ANY($1::varchar[])", ids)
        await conn.close()
