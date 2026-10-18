"""真实 HTTP 与 PostgreSQL 验证线程快照读取和用户隔离。"""

import os
import uuid
from typing import TypedDict

import pytest
from langchain.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

from test.live_api_cleanup import delete_test_session_rows, make_test_session_title

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


class DisplayState(TypedDict):
    """面板业务字段及旧 checkpoint 的文件镜像。"""

    messages: list
    todos: list
    files: dict
    artifacts: list
    cooperation: dict
    token_usage: dict


@pytest.mark.parametrize(
    "artifact_payload", [["result.txt"], [{"path": "screenshot.png", "type": "image"}, {"path": "result.txt", "type": "file"}]]
)
async def test_state_view_reads_postgres_snapshot_and_rejects_other_users(test_client, admin_headers, standard_user, artifact_payload):
    """无模型配置也可读快照，未知和其他用户线程拒绝读取。"""
    slug = f"pytest-checkpoint-{uuid.uuid4().hex[:8]}"
    created = await test_client.post(
        "/api/agent",
        json={"name": slug, "slug": slug, "backend_id": "ChatbotAgent", "config_json": {"context": {}}},
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    thread_id = None
    dsn = os.environ["POSTGRES_URL"].replace("+asyncpg", "").replace("+psycopg", "")
    async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
        try:
            created_thread = await test_client.post(
                "/api/v1/agents/sessions",
                json={
                    "agent_id": slug,
                    "title": make_test_session_title("checkpoint"),
                },
                headers={**admin_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
            assert created_thread.status_code == 201, created_thread.text
            thread_id = created_thread.json()["id"]
            url = f"/api/v1/agents/sessions/{thread_id}/state"
            empty = await test_client.get(url, headers=admin_headers)
            assert empty.status_code == 200, empty.text
            state = empty.json()["agent_state"]
            assert len(state.pop("cooperation")["sessions"]) == 1
            assert state == {
                "artifacts": [],
                "token_usage": None,
            }

            payload = {
                "messages": [HumanMessage(content="persisted checkpoint message")],
                "todos": [{"content": "persisted todo", "status": "completed"}],
                "files": {"legacy.txt": {"content": ["old checkpoint content"]}},
                "artifacts": artifact_payload,
                "cooperation": {"sessions": [{"session_id": "forged-child"}]},
                "token_usage": {"total": 17},
            }
            graph = StateGraph(DisplayState)
            graph.add_node("done", lambda state: {})
            graph.add_edge(START, "done")
            graph.add_edge("done", END)
            await graph.compile(checkpointer=saver).ainvoke(payload, {"configurable": {"thread_id": thread_id}})

            response = await test_client.get(url, headers=admin_headers)
            assert response.status_code == 200, response.text
            state = response.json()["agent_state"]
            assert [member["session_id"] for member in state.pop("cooperation")["sessions"]] == [thread_id]
            assert state == {key: payload[key] for key in ("artifacts", "token_usage")}
            assert "items" not in response.json()  # 可见消息来自持久Message，不能从checkpoint伪造。
            assert "interrupt" not in response.json()
            assert (await test_client.get(url)).status_code == 401
            assert (await test_client.get(url, headers=standard_user["headers"])).status_code == 404
            assert (await test_client.get(f"/api/v1/agents/sessions/{uuid.uuid4()}/state", headers=admin_headers)).status_code == 404
            archived = await test_client.post(f"/api/v1/agents/sessions/{thread_id}/archive", headers=admin_headers)
            assert archived.status_code == 200, archived.text
            preserved = await test_client.get(url, headers=admin_headers)
            assert preserved.status_code == 200, preserved.text
            assert preserved.json()["agent_state"]["artifacts"] == payload["artifacts"]
            assert "todos" not in preserved.json()["agent_state"]
        finally:
            if thread_id:
                await saver.adelete_thread(thread_id)
                archived = await test_client.post(f"/api/v1/agents/sessions/{thread_id}/archive", headers=admin_headers)
                assert archived.status_code in (200, 404), archived.text
                # 空会话未执行工具或写入文件；共享 Workspace 的目录仍由用户 Project 持有。
                await delete_test_session_rows({thread_id})
            deleted_agent = await test_client.delete(f"/api/agent/{slug}", headers=admin_headers)
            assert deleted_agent.status_code in (200, 404), deleted_agent.text
