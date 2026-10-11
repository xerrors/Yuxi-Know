"""官方输入默认优先级、幂等批次与公开 item 恢复的 assembled-path 证据。"""

import asyncio
import uuid

import asyncpg
import httpx
import pytest

from e2e_helpers import archive_public_thread, delete_agent, postgres_dsn
from test.e2e.e2e_helpers import (
    DETERMINISTIC_MODEL as MODEL,
    DETERMINISTIC_OUTPUT as OUTPUT,
    create_lifecycle_agent as _agent,
    public_message as _message,
    register_replay_provider as _provider,
    wait_for_terminal_turn as _turn,
)
from test.e2e.e2e_helpers import wait_for_consumed_input
from test.live_api_cleanup import make_test_session_title

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e, pytest.mark.slow, pytest.mark.timeout(180)]


async def test_default_message_keeps_batch_across_concurrent_steer_and_retry(e2e_client, e2e_headers):
    """运行中默认优先合批；终态后幂等重试仍返回同一已消费批次。"""
    await _provider(e2e_client, e2e_headers)
    uid = str((await e2e_client.get("/api/auth/me", headers=e2e_headers)).json()["uid"])
    slug = await _agent(e2e_client, e2e_headers, uid)
    gate = str(uuid.uuid4())
    thread_id = turn_id = None
    async with httpx.AsyncClient(base_url="http://api:8765", timeout=5) as replay:
        try:
            created = await e2e_client.post(
                "/api/v1/agents/sessions",
                headers={**e2e_headers, "Idempotency-Key": f"create-{gate}"},
                json={
                    "agent_id": slug,
                    "agent": {"model": MODEL},
                    "title": make_test_session_title("openai-default-mode"),
                },
            )
            assert created.status_code == 201, created.text
            thread_id = created.json()["id"]
            url = f"/api/v1/agents/sessions/{thread_id}/events"
            started = await e2e_client.post(
                url,
                headers={**e2e_headers, "Idempotency-Key": f"idle-{gate}"},
                json={
                    "events": [
                        {
                            "type": "agent.session.input.message",
                            "input": [_message(f"{OUTPUT} DETERMINISTIC_BLOCK_BEFORE_RESPONSE:{gate}")],
                        }
                    ]
                },
            )
            assert started.status_code == 202, started.text
            turn_id = (await wait_for_consumed_input(e2e_client, e2e_headers, started.json()))["turn_id"]
            async with asyncio.timeout(30):
                while not (await replay.get("/blocking-started", params={"token": gate})).json()["started"]:
                    await asyncio.sleep(0.1)
            requests = [
                (
                    {"events": [{"type": "agent.session.input.message", "input": [_message(f"steer {index}")]}]},
                    {**e2e_headers, "Idempotency-Key": f"steer-{gate}-{index}"},
                )
                for index in range(2)
            ]
            receipts = await asyncio.gather(*(e2e_client.post(url, headers=headers, json=body) for body, headers in requests))
            assert all(r.status_code == 202 for r in receipts), [r.text for r in receipts]
            assert receipts[0].json()["input_id"] != receipts[1].json()["input_id"]
            assert all(r.json()["turn_id"] is None and "mode" not in r.json() for r in receipts)
            queued = await e2e_client.post(
                url,
                headers={**e2e_headers, "Idempotency-Key": f"queue-{gate}"},
                json={
                    "events": [
                        {
                            "type": "agent.session.input.message",
                            "input": [_message(OUTPUT)],
                            "yuxi": {"mode": "follow_up"},
                        }
                    ]
                },
            )
            assert queued.status_code == 202 and queued.json()["run_id"] is None, queued.text
            unsupported = await e2e_client.post(
                url,
                headers={**e2e_headers, "Idempotency-Key": f"unsupported-{gate}"},
                json={"events": [{"type": "agent.session.input.function_call_output", "call_id": "fake", "output": "fake"}]},
            )
            assert unsupported.status_code == 422, unsupported.text
            await replay.get("/release-blocking", params={"token": gate})
            assert (await _turn(e2e_client, e2e_headers, thread_id, turn_id))["status"] == "completed"
            async with asyncio.timeout(45):
                while True:
                    input_result = (
                        await e2e_client.get(
                            f"/api/v1/agents/sessions/{thread_id}/inputs/{queued.json()['input_id']}",
                            headers=e2e_headers,
                        )
                    ).json()
                    if input_result["run_id"]:
                        break
                    await asyncio.sleep(0.2)
            assert input_result["turn_id"] != turn_id
            assert (await _turn(e2e_client, e2e_headers, thread_id, input_result["turn_id"]))["status"] == "completed"
            for (body, headers), receipt in zip(requests, receipts):
                retry = await e2e_client.post(url, headers=headers, json=body)
                assert retry.status_code == 202, retry.text
                assert retry.json() == receipt.json()
                assert retry.json()["turn_id"] is None and retry.json()["run_id"] is None
            changed = await e2e_client.post(
                url,
                headers=requests[0][1],
                json={"events": [{"type": "agent.session.input.message", "input": [_message("changed")]}]},
            )
            assert changed.status_code == 409
            conn = await asyncpg.connect(postgres_dsn())
            try:
                modes = await conn.fetch(
                    "SELECT i.kind, i.turn_id, r.turn_id AS receipt_turn FROM agent_input_receipts r "
                    "LEFT JOIN agent_inputs i ON i.id = r.input_id WHERE r.idempotency_key LIKE $1",
                    f"%{gate}%",
                )
                assert sum(row["kind"] == "steer" for row in modes) == 2
                assert all(row["turn_id"] == turn_id for row in modes if row["kind"] == "steer")
                assert all(row["receipt_turn"] is None for row in modes if row["kind"] == "steer")
            finally:
                await conn.close()
            # 每个公开 item 独立分页，不能按 Message ID 截断同消息的工具 item。
            history = (await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/items?order=asc&limit=100", headers=e2e_headers)).json()
            expected = [item for item in history["data"] if item["turn_id"] == turn_id]
            page_url = f"/api/v1/agents/sessions/{thread_id}/turns/{turn_id}/items"
            seen, after = [], None
            for _ in range(len(expected) + 1):
                response = await e2e_client.get(
                    page_url,
                    headers=e2e_headers,
                    params={"limit": 1, "order": "asc", **({"after": after} if after else {})},
                )
                assert response.status_code == 200, response.text
                values = response.json()["data"]
                if not values:
                    break
                seen.extend(values)
                after = values[-1]["id"]
            assert seen == expected
            assert (await e2e_client.get(page_url, headers=e2e_headers, params={"after": "unknown"})).status_code == 400
        finally:
            await replay.get("/release-blocking", params={"token": gate})
            if thread_id:
                await archive_public_thread(e2e_client, e2e_headers, thread_id, turn_id=turn_id)
            await delete_agent(e2e_client, e2e_headers, slug)


async def test_default_cancel_target_is_fixed_for_idempotent_retry(e2e_client, e2e_headers):
    """未带目标的取消在 owning transaction 固定 Turn，重试不取消相邻 Turn。"""
    await _provider(e2e_client, e2e_headers)
    uid = str((await e2e_client.get("/api/auth/me", headers=e2e_headers)).json()["uid"])
    slug = await _agent(e2e_client, e2e_headers, uid)
    gate = str(uuid.uuid4())
    thread_id = turn_id = None
    async with httpx.AsyncClient(base_url="http://api:8765", timeout=5) as replay:
        try:
            created = await e2e_client.post(
                "/api/v1/agents/sessions",
                headers={**e2e_headers, "Idempotency-Key": f"cancel-create-{gate}"},
                json={
                    "agent_id": slug,
                    "agent": {"model": MODEL},
                    "title": make_test_session_title("default-cancel"),
                    "input": [_message(f"{OUTPUT} DETERMINISTIC_BLOCK_BEFORE_RESPONSE:{gate}")],
                },
            )
            assert created.status_code == 201, created.text
            consumed = await wait_for_consumed_input(e2e_client, e2e_headers, created.json()["yuxi"]["receipt"])
            thread_id, turn_id = consumed["session_id"], consumed["turn_id"]
            async with asyncio.timeout(30):
                while not (await replay.get("/blocking-started", params={"token": gate})).json()["started"]:
                    await asyncio.sleep(0.1)
            url = f"/api/v1/agents/sessions/{thread_id}/events"
            headers = {**e2e_headers, "Idempotency-Key": f"cancel-{gate}"}
            body = {"events": [{"type": "agent.session.input.cancel"}]}
            cancelled = await e2e_client.post(url, headers=headers, json=body)
            assert cancelled.status_code == 202 and cancelled.json()["turn_id"] == turn_id, cancelled.text
            await replay.get("/release-blocking", params={"token": gate})
            assert (await _turn(e2e_client, e2e_headers, thread_id, turn_id))["status"] == "cancelled"
            continued = await e2e_client.post(
                url,
                headers={**e2e_headers, "Idempotency-Key": f"continue-{gate}"},
                json={"events": [{"type": "yuxi.session.input.continue"}]},
            )
            assert continued.status_code == 202, continued.text
            second = await e2e_client.post(
                url,
                headers={**e2e_headers, "Idempotency-Key": f"second-{gate}"},
                json={"events": [{"type": "agent.session.input.message", "input": [_message(OUTPUT)]}]},
            )
            assert second.status_code == 202, second.text
            second_input = await wait_for_consumed_input(e2e_client, e2e_headers, second.json())
            assert second_input["turn_id"] != turn_id
            retried = await e2e_client.post(url, headers=headers, json=body)
            assert retried.status_code == 202 and retried.json() == cancelled.json(), retried.text
            assert (await _turn(e2e_client, e2e_headers, thread_id, second_input["turn_id"]))["status"] == "completed"
        finally:
            await replay.get("/release-blocking", params={"token": gate})
            if thread_id:
                await archive_public_thread(e2e_client, e2e_headers, thread_id, turn_id=turn_id)
            await delete_agent(e2e_client, e2e_headers, slug)


async def test_cancel_preserves_displayed_partial_text_in_public_history(e2e_client, e2e_headers):
    """模型正文已展示但尚未 finish 时取消；持久 incomplete 快照保留同一正文。"""
    from test.support.public_events import read_events

    await _provider(e2e_client, e2e_headers)
    uid = str((await e2e_client.get("/api/auth/me", headers=e2e_headers)).json()["uid"])
    slug = await _agent(e2e_client, e2e_headers, uid)
    gate = str(uuid.uuid4())
    thread_id = turn_id = None
    async with httpx.AsyncClient(base_url="http://api:8765", timeout=5) as replay:
        try:
            created = await e2e_client.post(
                "/api/v1/agents/sessions",
                headers={**e2e_headers, "Idempotency-Key": str(uuid.uuid4())},
                json={
                    "agent_id": slug,
                    "agent": {"model": MODEL},
                    "title": make_test_session_title("cancel-partial"),
                    "input": [_message(f"{OUTPUT} DETERMINISTIC_CANCEL_FOLLOWUP DETERMINISTIC_BLOCK_BEFORE_RESPONSE:{gate}")],
                },
            )
            assert created.status_code == 201, created.text
            consumed = await wait_for_consumed_input(e2e_client, e2e_headers, created.json()["yuxi"]["receipt"])
            thread_id, turn_id = consumed["session_id"], consumed["turn_id"]
            async with asyncio.timeout(30):
                async with e2e_client.stream("GET", f"/api/v1/agents/sessions/{thread_id}/events", headers=e2e_headers) as stream:
                    async for _, event in read_events(stream):
                        if event["type"] == "agent.session.turn.output_text.delta":
                            shown, item_id = event["delta"], event["item_id"]
                            break
            assert shown == OUTPUT
            cancelled = await e2e_client.post(
                f"/api/v1/agents/sessions/{thread_id}/events",
                headers={**e2e_headers, "Idempotency-Key": str(uuid.uuid4())},
                json={"events": [{"type": "agent.session.input.cancel"}]},
            )
            assert cancelled.status_code == 202, cancelled.text
            await replay.get("/release-blocking", params={"token": gate})
            assert (await _turn(e2e_client, e2e_headers, thread_id, turn_id))["status"] == "cancelled"
            history = (await e2e_client.get(f"/api/v1/agents/sessions/{thread_id}/items?order=asc&limit=100", headers=e2e_headers)).json()
            item = next(item for item in history["data"] if item["id"] == item_id)
            assert item["status"] == "incomplete"
            assert item["content"] == [{"type": "output_text", "text": shown}]
        finally:
            await replay.get("/release-blocking", params={"token": gate})
            if thread_id:
                await archive_public_thread(e2e_client, e2e_headers, thread_id, turn_id=turn_id)
            await delete_agent(e2e_client, e2e_headers, slug)
