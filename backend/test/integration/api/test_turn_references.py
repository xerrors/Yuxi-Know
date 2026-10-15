"""真实 HTTP、模型协议与 PostgreSQL 下的按需来源标注。"""

import asyncio
import json
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from test.live_api_cleanup import make_test_session_title
from yuxi.modules.agents.models.messages import Message
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.modules.knowledge.models import KnowledgeBase

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

ANSWER = "# 结论\n\n知识库说明保留原文。\n\n网页说明链接可跳转。"
REPLAY_RESULT = {
    "citations": [
        {"answer_start_line": 3, "answer_end_line": 3, "source_id": "s1", "quote": "知识库证据"},
        {"answer_start_line": 5, "answer_end_line": 5, "source_id": "s2", "quote": "网页证据"},
    ]
}


@pytest.fixture
def reference_replay():
    """用真实 OpenAI wire 响应校验独立调用的数据边界。"""
    state = SimpleNamespace(result=REPLAY_RESULT, requests=[], started=threading.Event(), release=None)

    class Handler(BaseHTTPRequestHandler):
        """接收非流式模型调用并提供固定 oracle。"""

        def do_POST(self):
            """保留实际入站 JSON，输出独立固定引用结果。"""
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state.requests.append(request)
            state.started.set()
            if state.release:
                state.release.wait(10)
            body = json.dumps(
                {
                    "id": "chatcmpl-reference-replay",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "reference-replay",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": json.dumps(state.result, ensure_ascii=False)},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 30, "completion_tokens": 20, "total_tokens": 50},
                },
                ensure_ascii=False,
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            """测试服务不记录用户 payload。"""

    server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.port = server.server_port
    try:
        yield state
    finally:
        if state.release:
            state.release.set()
        server.shutdown()
        server.server_close()
        thread.join()


@pytest_asyncio.fixture
async def reference_turn(test_client, admin_headers, reference_replay):
    """创建独立资源与两轮快照，覆盖同轮恢复和相邻轮隔离。"""
    provider_id = f"pytest-refs-{uuid.uuid4().hex[:10]}"
    registered = await test_client.post(
        "/api/system/model-providers",
        headers=admin_headers,
        json={
            "provider_id": provider_id,
            "display_name": "Reference replay",
            "provider_type": "openai",
            "base_url": f"http://api:{reference_replay.port}/v1",
            "api_key": "test-reference-key",
            "capabilities": ["chat"],
            "enabled_models": [{"id": "reference-replay", "type": "chat", "source": "manual"}],
        },
    )
    assert registered.status_code == 200, registered.text
    model = f"{provider_id}:reference-replay"
    uid = str((await test_client.get("/api/auth/me", headers=admin_headers)).json()["uid"])
    agents = (await test_client.get("/api/agent", headers=admin_headers)).json()["agents"]
    agent = next(item for item in agents if item.get("is_default"))
    slug = agent.get("slug") or agent["agent_id"]
    created = await test_client.post(
        "/api/v1/agents/sessions",
        headers={
            **admin_headers,
            "Idempotency-Key": str(uuid.uuid4()),
        },
        json={"agent_id": slug, "agent": {"model": model}, "title": make_test_session_title("turn-references")},
    )
    assert created.status_code == 201, created.text
    thread_id = created.json()["id"]
    kb_id = f"pytest_kb_refs_{uuid.uuid4().hex[:10]}"
    turn_id, neighbor_id = str(uuid.uuid4()), str(uuid.uuid4())
    early_id, result_id, neighbor_run_id = (str(uuid.uuid4()) for _ in range(3))
    engine = create_async_engine(os.environ["POSTGRES_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as db:
            agent_session = await db.scalar(select(Session).where(Session.thread_id == thread_id))
            session_id = agent_session.id
            snapshot = agent_session.config_snapshot
            kb = KnowledgeBase(
                kb_id=kb_id,
                name=kb_id,
                kb_type="milvus",
                created_by=uid,
                share_config={
                    "version": 2,
                    "read_scope": {"access_level": "user", "user_uids": [uid], "department_ids": []},
                },
            )
            turns = [AgentTurn(id=identifier, thread_id=thread_id, uid=uid, status="completed") for identifier in [turn_id, neighbor_id]]
            db.add_all([kb, *turns])
            await db.flush()
            runs = [
                AgentRun(
                    id=identifier,
                    thread_id=thread_id,
                    runtime_scope_id=thread_id,
                    session_record_id=session_id,
                    agent_slug=slug,
                    uid=uid,
                    turn_id=owning_turn,
                    status="yielded" if identifier == early_id else "completed",
                    input_payload={"context_snapshot": snapshot},
                )
                for identifier, owning_turn in [
                    (early_id, turn_id),
                    (result_id, turn_id),
                    (neighbor_run_id, neighbor_id),
                ]
            ]
            db.add_all(runs)
            await db.flush()
            output = Message(
                session_record_id=session_id,
                role="assistant",
                content=ANSWER,
                run_id=result_id,
                turn_id=turn_id,
                extra_metadata={"keep": "unchanged"},
            )
            neighbor_output = Message(
                session_record_id=session_id,
                role="assistant",
                content="NEIGHBOR_ANSWER",
                run_id=neighbor_run_id,
                turn_id=neighbor_id,
            )
            db.add_all([output, neighbor_output])
            await db.flush()
            output.extra_metadata = {
                **output.extra_metadata,
                "public_items": {
                    "answer": {
                        "id": f"item_{output.id}",
                        "type": "message",
                        "turn_id": turn_id,
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": ANSWER}],
                        "status": "completed",
                        "yuxi": {"run_id": result_id, "message_id": output.id, "output_index": 0},
                    }
                },
            }
            neighbor_output.extra_metadata = {
                "public_items": {
                    "answer": {
                        "id": f"item_{neighbor_output.id}",
                        "type": "message",
                        "turn_id": neighbor_id,
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "NEIGHBOR_ANSWER"}],
                        "status": "completed",
                        "yuxi": {"run_id": neighbor_run_id, "message_id": neighbor_output.id, "output_index": 0},
                    }
                }
            }
            runs[1].output_message_id = output.id
            runs[2].output_message_id = neighbor_output.id
            turns[0].result_run_id = result_id
            turns[0].current_run_id = result_id
            turns[1].result_run_id = neighbor_run_id
            turns[1].current_run_id = neighbor_run_id
            payloads = [
                (
                    early_id,
                    turn_id,
                    "query_kb",
                    {
                        "results": [
                            {
                                "id": "chunk-original",
                                "file_id": "file-original",
                                "content": "知识库证据",
                                "metadata": {"source": "测试报告.md", "start_line": 8, "end_line": 12, "generation": 1},
                            }
                        ]
                    },
                    "completed",
                ),
                (
                    result_id,
                    turn_id,
                    "web_search",
                    {
                        "results": [
                            {
                                "title": "网页资料",
                                "url": "https://example.org/reference",
                                "content": "网页证据",
                            }
                        ]
                    },
                    "completed",
                ),
                (
                    result_id,
                    turn_id,
                    "web_search",
                    {
                        "results": [
                            {
                                "title": "失败资料",
                                "url": "https://example.org/failed",
                                "content": "FAILED_TOOL_EVIDENCE",
                            }
                        ]
                    },
                    "failed",
                ),
                (
                    neighbor_run_id,
                    neighbor_id,
                    "web_search",
                    {
                        "results": [
                            {
                                "title": "相邻资料",
                                "url": "https://example.org/neighbor",
                                "content": "NEIGHBOR_EVIDENCE",
                            }
                        ]
                    },
                    "completed",
                ),
            ]
            for run_id, owning_turn, name, payload, status in payloads:
                db.add(
                    Message(
                        session_record_id=session_id,
                        role="tool",
                        message_type="tool_audit",
                        run_id=run_id,
                        turn_id=owning_turn,
                        content="",
                        execution_status=status,
                        extra_metadata={"output": json.dumps(payload, ensure_ascii=False), "tool_name": name, "input": {"kb_id": kb_id}},
                    )
                )
            await db.commit()
        yield SimpleNamespace(
            path=f"/api/v1/agents/sessions/{thread_id}/turns/{turn_id}",
            references_path=f"/api/agent/threads/{thread_id}/turns/{turn_id}/references",
            sessions=sessions,
            message_id=output.id,
            turn_id=turn_id,
            neighbor_id=neighbor_id,
            result_id=result_id,
            kb_id=kb_id,
        )
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE agent_turns SET current_run_id=NULL, result_run_id=NULL WHERE thread_id=:id"),
                {"id": thread_id},
            )
            await conn.execute(text("UPDATE agent_runs SET output_message_id=NULL WHERE thread_id=:id"), {"id": thread_id})
            await conn.execute(text("DELETE FROM messages WHERE session_record_id=:id"), {"id": session_id})
            await conn.execute(text("DELETE FROM agent_runs WHERE thread_id=:id"), {"id": thread_id})
            await conn.execute(text("DELETE FROM agent_turns WHERE thread_id=:id"), {"id": thread_id})
            await conn.execute(text("DELETE FROM knowledge_bases WHERE kb_id=:id"), {"id": kb_id})
        await test_client.delete(f"/api/system/model-providers/{provider_id}", headers=admin_headers)
        await engine.dispose()


async def test_reference_round_trip_uses_final_answer_and_same_turn_sources(
    test_client,
    admin_headers,
    standard_user,
    reference_turn,
    reference_replay,
):
    """回读 PG、Turn 与引用接口，证实最终回答与同轮成功证据的唯一归属。"""
    target = reference_turn
    url = target.references_path
    before = await test_client.get(url, headers=admin_headers)
    assert before.status_code == 200, before.text
    sources = before.json()["sources"]
    assert [source["content"] for source in sources] == ["知识库证据", "网页证据"]
    assert sources[0]["supports_documents"] is True
    async with target.sessions() as db:
        run = await db.get(AgentRun, target.result_id)
        session = await db.get(Session, run.session_record_id)
        session.config_snapshot = {**session.config_snapshot, "model": "unconfigured:later-default"}
        await db.commit()
    result = await test_client.post(url, headers=admin_headers)
    assert result.status_code == 200, result.text
    saved = result.json()
    assert saved["output_message_id"] == target.message_id
    assert saved["result_run_id"] == target.result_id
    assert saved["citations"][0]["source_start_line"] == 8
    assert saved["citations"][0]["source_end_line"] == 12
    wire = reference_replay.requests[0]
    assert wire.get("tools") is None and wire.get("stream") is False
    prompt = json.loads(wire["messages"][-1]["content"])
    assert prompt["answer"][2] == {"line": 3, "text": "知识库说明保留原文。"}
    assert [source["content"] for source in prompt["sources"]] == ["知识库证据", "网页证据"]
    async with target.sessions() as db:
        message = await db.get(Message, target.message_id)
        assert message.content == ANSWER
        assert message.extra_metadata["keep"] == "unchanged"
        assert message.extra_metadata["references"] == saved
        assert (await db.get(AgentTurn, target.turn_id)).status == "completed"
    repeated = await test_client.post(url, headers=admin_headers)
    assert repeated.json() == saved
    assert len(reference_replay.requests) == 1
    reread = await test_client.get(url, headers=admin_headers)
    assert reread.json()["references"] == saved
    turn = await test_client.get(target.path, headers=admin_headers)
    assert "references" not in turn.json().get("metadata", {})
    assert turn.json()["yuxi"]["output"][0]["content"][0]["text"] == ANSWER
    neighbor = await test_client.get(target.path.replace(target.turn_id, target.neighbor_id), headers=admin_headers)
    assert neighbor.status_code == 200, neighbor.text
    assert neighbor.json()["yuxi"]["output"][0]["content"][0]["text"] == "NEIGHBOR_ANSWER"
    denied = await test_client.post(url, headers=standard_user["headers"])
    assert denied.status_code == 404


async def test_references_are_web_only_and_absent_from_public_protocol(
    test_client, admin_headers, standard_user, reference_turn, reference_replay, api_key_factory
):
    """真实凭据与协议回读拒绝外部入口、完整 Key 和跨用户读取。"""
    target = reference_turn
    public_url = target.path + "/references"
    for method in ("GET", "POST"):
        missing = await test_client.request(method, public_url, headers=admin_headers)
        assert missing.status_code == 404, missing.text
        anonymous = await test_client.request(method, target.references_path)
        assert anonymous.status_code == 401, anonymous.text
        other_user = await test_client.request(method, target.references_path, headers=standard_user["headers"])
        assert other_user.status_code == 404, other_user.text

    for access_level, app_id in (("full", None), ("full", "reference-app"), ("agents", "reference-app")):
        created = await api_key_factory(
            {
                "request_id": str(uuid.uuid4()),
                "name": "Web reference boundary",
                "access_level": access_level,
                "app_id": app_id,
            }
        )
        for method in ("GET", "POST"):
            denied = await test_client.request(method, target.references_path, headers=created.headers)
            assert denied.status_code == 403, denied.text
            if access_level == "full":
                assert denied.json()["detail"] == "来源标注仅支持 Web 登录用户"
            old_route = await test_client.request(method, public_url, headers=created.headers)
            assert old_route.status_code == 404, old_route.text

    assert reference_replay.requests == []
    async with target.sessions() as db:
        assert "references" not in (await db.get(Message, target.message_id)).extra_metadata

    saved = await test_client.post(target.references_path, headers=admin_headers)
    assert saved.status_code == 200, saved.text
    turn = await test_client.get(target.path, headers=admin_headers)
    assert turn.status_code == 200, turn.text
    assert "references" not in turn.json().get("metadata", {})
    restored = await test_client.get(target.references_path, headers=admin_headers)
    assert restored.json()["references"] == saved.json()

    schema = await test_client.get("/openapi.json")
    assert schema.status_code == 200, schema.text
    assert not any(path.endswith("/references") for path in schema.json()["paths"])


async def test_web_references_cannot_read_app_owned_thread(test_client, admin_headers, reference_turn):
    """Web 身份固定 app_id=None，不接受 APP 归属的持久 Thread。"""
    target = reference_turn
    async with target.sessions() as db:
        session = await db.scalar(
            select(Session).join(AgentTurn, AgentTurn.thread_id == Session.thread_id).where(AgentTurn.id == target.turn_id)
        )
        session.app_id = "reference-app"
        await db.commit()
    try:
        for method in ("GET", "POST"):
            denied = await test_client.request(method, target.references_path, headers=admin_headers)
            assert denied.status_code == 404, denied.text
    finally:
        async with target.sessions() as db:
            session = await db.get(Session, session.id)
            session.app_id = None
            await db.commit()


async def test_readonly_connector_evidence_keeps_remote_file_id_without_document_preview(test_client, admin_headers, reference_turn):
    """Dify 的远端 file_id 不代表支持本地原文预览。"""
    target = reference_turn
    async with target.sessions() as db:
        kb = await db.scalar(select(KnowledgeBase).where(KnowledgeBase.kb_id == target.kb_id))
        kb.kb_type = "dify"
        kb.additional_params = {
            "dify_api_url": "https://example.org/dify/v1",
            "dify_token": "test-reference-token",
            "dify_dataset_id": "test-reference-dataset",
        }
        tools = list(await db.scalars(select(Message).where(Message.turn_id == target.turn_id, Message.role == "tool")))
        knowledge = next(message for message in tools if message.extra_metadata["tool_name"] == "query_kb")
        knowledge.extra_metadata = {**knowledge.extra_metadata, "output": json.dumps(
            {"results": [{"content": "知识库证据", "metadata": {"file_id": "remote-document", "source": "外部文档"}}]},
            ensure_ascii=False,
        )}
        await db.commit()
    before = await test_client.get(target.references_path, headers=admin_headers)
    assert [source["kind"] for source in before.json()["sources"]] == ["knowledge", "web"]
    result = await test_client.post(target.references_path, headers=admin_headers)
    assert result.status_code == 200, result.text
    source = result.json()["sources"][0]
    assert source["file_id"] == "remote-document"
    assert source["supports_documents"] is False
    assert result.json()["citations"][0]["source_start_line"] is None
    reread = await test_client.get(target.references_path, headers=admin_headers)
    assert reread.json()["references"]["sources"][0]["supports_documents"] is False


async def test_invalid_model_output_does_not_save_success_and_can_retry(
    test_client,
    admin_headers,
    reference_turn,
    reference_replay,
):
    """虚构摘录失败后，回答和 metadata 保持原样，后续合法请求可完成。"""
    reference_replay.result = {"citations": [{**REPLAY_RESULT["citations"][0], "quote": "不存在的原文"}]}
    url = reference_turn.references_path
    failed = await test_client.post(url, headers=admin_headers)
    assert failed.status_code == 502, failed.text
    assert failed.json()["detail"]["code"] == "references_invalid"
    async with reference_turn.sessions() as db:
        message = await db.get(Message, reference_turn.message_id)
        assert "references" not in message.extra_metadata
        assert message.content == ANSWER
    reference_replay.result = REPLAY_RESULT
    retried = await test_client.post(url, headers=admin_headers)
    assert retried.status_code == 200, retried.text
    assert len(retried.json()["citations"]) == 2


async def test_concurrent_annotation_rejects_duplicate_call(test_client, admin_headers, reference_turn, reference_replay):
    """真实 PG 锁在独立模型请求等待期间拒绝第二个请求。"""
    reference_replay.release = threading.Event()
    url = reference_turn.references_path
    first = asyncio.create_task(test_client.post(url, headers=admin_headers))
    try:
        assert await asyncio.to_thread(reference_replay.started.wait, 10)
        duplicate = await test_client.post(url, headers=admin_headers)
        assert duplicate.status_code == 409, duplicate.text
        assert duplicate.json()["detail"]["code"] == "references_busy"
    finally:
        reference_replay.release.set()
    completed = await first
    assert completed.status_code == 200, completed.text
    async with reference_turn.sessions() as db:
        assert (await db.get(Message, reference_turn.message_id)).extra_metadata["references"]["citations"]


async def test_removed_knowledge_is_excluded_from_model_and_saved_reference_reads(
    test_client,
    admin_headers,
    reference_turn,
    reference_replay,
):
    """权限集合失去知识库后，历史片段不能进入新调用或从标注继续显示。"""
    target = reference_turn
    url = target.references_path
    saved = await test_client.post(url, headers=admin_headers)
    assert saved.status_code == 200, saved.text
    async with target.sessions() as db:
        await db.execute(text("UPDATE knowledge_bases SET deleted_at=NOW() WHERE kb_id=:id"), {"id": target.kb_id})
        await db.commit()
    reread = await test_client.get(url, headers=admin_headers)
    assert reread.status_code == 200, reread.text
    assert [source["kind"] for source in reread.json()["sources"]] == ["web"]
    assert [source["id"] for source in reread.json()["references"]["sources"]] == ["s2"]
    assert [item["source_id"] for item in reread.json()["references"]["citations"]] == ["s2"]
    turn = await test_client.get(target.path, headers=admin_headers)
    assert "references" not in turn.json().get("metadata", {})

    async with target.sessions() as db:
        output = await db.get(Message, target.message_id)
        output.extra_metadata = {key: value for key, value in output.extra_metadata.items() if key != "references"}
        await db.commit()
    reference_replay.result = {
        "citations": [
            {
                "answer_start_line": 5,
                "answer_end_line": 5,
                "source_id": "s1",
                "quote": "网页证据",
            }
        ]
    }
    fresh = await test_client.post(url, headers=admin_headers)
    assert fresh.status_code == 200, fresh.text
    prompt = json.loads(reference_replay.requests[-1]["messages"][-1]["content"])
    assert prompt["sources"] == [{"id": "s1", "content": "网页证据"}]


async def test_incomplete_turn_and_oversize_sources_do_not_call_model(
    test_client,
    admin_headers,
    reference_turn,
    reference_replay,
):
    """非完成回答与超预算输入在模型副作用发生前拒绝。"""
    target = reference_turn
    url = target.references_path
    async with target.sessions() as db:
        turn = await db.get(AgentTurn, target.turn_id)
        turn.status = "running"
        await db.commit()
    unavailable = await test_client.get(url, headers=admin_headers)
    assert unavailable.json()["available"] is False
    incomplete = await test_client.post(url, headers=admin_headers)
    assert incomplete.status_code == 409
    assert incomplete.json()["detail"]["code"] == "answer_not_completed"
    async with target.sessions() as db:
        turn = await db.get(AgentTurn, target.turn_id)
        turn.status = "completed"
        tools = list(await db.scalars(select(Message).where(Message.turn_id == target.turn_id, Message.role == "tool")))
        knowledge = next(message for message in tools if message.extra_metadata["tool_name"] == "query_kb")
        knowledge.extra_metadata = {**knowledge.extra_metadata, "output": json.dumps({"results": [{"content": "证据" * 40000}]})}
        await db.commit()
    oversize = await test_client.post(url, headers=admin_headers)
    assert oversize.status_code == 413
    assert oversize.json()["detail"]["code"] == "references_input_too_large"
    assert reference_replay.requests == []
    async with target.sessions() as db:
        assert "references" not in (await db.get(Message, target.message_id)).extra_metadata


@pytest.mark.parametrize("snapshot", [None, {}, {"model": ""}])
async def test_missing_run_model_snapshot_does_not_fall_back_or_call_model(
    test_client, admin_headers, reference_turn, reference_replay, snapshot
):
    """缺失执行快照不能借用 Session 或系统默认模型并伪装成功。"""
    target = reference_turn
    async with target.sessions() as db:
        run = await db.get(AgentRun, target.result_id)
        run.input_payload = {"context_snapshot": snapshot}
        await db.commit()

    response = await test_client.post(target.references_path, headers=admin_headers)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "references_config_missing"
    assert reference_replay.requests == []
    async with target.sessions() as db:
        assert "references" not in (await db.get(Message, target.message_id)).extra_metadata


@pytest.mark.slow
async def test_real_model_matches_supported_answer_ranges(test_client, admin_headers, reference_turn):
    """用调用方明确指定的真实模型校准 JSON 输出与证据匹配。"""
    model_spec = os.getenv("REFERENCE_PROBE_MODEL")
    if not model_spec:
        pytest.skip("真实模型探针需要 REFERENCE_PROBE_MODEL 指定已配置的聊天模型")
    target = reference_turn
    async with target.sessions() as db:
        run = await db.get(AgentRun, target.result_id)
        run.input_payload = {"context_snapshot": {**run.input_payload["context_snapshot"], "model": model_spec}}
        tools = list(
            await db.scalars(
                select(Message)
                .where(
                    Message.turn_id == target.turn_id,
                    Message.role == "tool",
                    Message.execution_status == "completed",
                )
                .order_by(Message.id)
            )
        )
        for message in tools:
            payload = json.loads(message.content)
            payload["results"][0]["content"] = (
                "知识库说明保留原文。知识库证据。"
                if message.extra_metadata["tool_name"] == "query_kb"
                else "网页说明链接可跳转。网页证据。"
            )
            message.content = json.dumps(payload, ensure_ascii=False)
        await db.commit()
    response = await test_client.post(target.references_path, headers=admin_headers, timeout=100)
    assert response.status_code == 200, response.text
    references = response.json()
    assert references["model_spec"] == model_spec
    assert {(citation["answer_start_line"], citation["answer_end_line"]) for citation in references["citations"]} == {
        (3, 3),
        (5, 5),
    }
    assert references["usage"]["input_tokens"] > 0
    async with target.sessions() as db:
        output = await db.get(Message, target.message_id)
        assert output.content == ANSWER
        assert output.extra_metadata["references"] == references
