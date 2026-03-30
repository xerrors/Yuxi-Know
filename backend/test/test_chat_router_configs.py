from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.routers.chat_router import chat
from server.utils.auth_middleware import get_db, get_required_user
from yuxi.storage.postgres.models_business import User


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(chat, prefix="/api")

    async def fake_db():
        return None

    async def fake_required_user():
        return User(
            username="admin",
            user_id="admin",
            password_hash="x",
            role="admin",
            department_id=1,
            id=1,
        )

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_required_user] = fake_required_user
    return app


def test_list_agent_configs_creates_default_with_agent_id(monkeypatch):
    agent_id = "demo-agent"
    captured: dict[str, object] = {}

    class DummyConfig:
        id = 1
        name = "初始配置"
        description = None
        icon = None
        pics = []
        examples = []
        is_default = True

    class DummyRepo:
        def __init__(self, _db):
            self.calls = 0

        async def list_by_department_agent(self, *, department_id, agent_id):
            self.calls += 1
            if self.calls == 1:
                return []
            return [DummyConfig()]

        async def get_or_create_default(self, *, department_id, agent_id, created_by=None):
            captured["department_id"] = department_id
            captured["agent_id"] = agent_id
            captured["created_by"] = created_by
            return None

    monkeypatch.setattr("server.routers.chat_router.agent_manager.get_agent", lambda _agent_id: object())
    monkeypatch.setattr("server.routers.chat_router.AgentConfigRepository", DummyRepo)

    client = TestClient(_build_app())
    resp = client.get(f"/api/chat/agent/{agent_id}/configs")
    assert resp.status_code == 200, resp.text
    assert captured["agent_id"] == agent_id
    assert captured["department_id"] == 1
    assert captured["created_by"] == "1"
