from __future__ import annotations

import importlib
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from yuxi.api.dependencies.auth import get_admin_user, get_db, get_required_user

agent_router_module = importlib.import_module("yuxi.api.routers.agents.management")


def _user(role: str = "admin"):
    uid = "admin" if role in {"admin", "superadmin"} else "user"
    return SimpleNamespace(uid=uid, role=role, department_id=1)


def _agent(slug: str, *, backend_id: str = "ChatbotAgent"):
    return SimpleNamespace(
        id=slug,
        slug=slug,
        name=slug,
        backend_id=backend_id,
        description="",
        icon=None,
        pics=[],
        config_json={},
        share_config={"access_level": "user", "user_uids": ["admin"]},
        is_default=False,
        can_manage=True,
    )


class _ListRepo:
    items = [
        _agent("chatbot", backend_id="ChatbotAgent"),
        _agent("worker"),
    ]
    get_definition_calls: list[str] = []

    def __init__(self, _db):
        pass

    async def ensure_default_agent(self):
        return self.items[0]

    async def list_visible(self, *, user):
        return self.items

    async def get_visible_by_slug(self, *, slug, user, for_run=True):
        self.get_definition_calls.append(slug)
        return next((item for item in self.items if item.slug == slug), None)

    async def serialize(self, item, **_kwargs):
        return dict(item.__dict__)


class _CreateRepo(_ListRepo):
    created_payload = None

    async def create(self, **kwargs):
        type(self).created_payload = kwargs
        return _agent(kwargs["slug"], backend_id=kwargs["backend_id"])


def _build_app(monkeypatch, repo_cls, *, role: str = "admin") -> TestClient:
    monkeypatch.setattr(agent_router_module, "AgentRepository", repo_cls)

    async def fake_create_definition(db, *, operator, skill_upload=None, mcp_servers=None, **fields):
        """路由单测隔离创建用例；联合事务由真实 HTTP integration 验证。"""
        return await repo_cls(db).create(**fields, created_by=operator.uid)

    monkeypatch.setattr(agent_router_module, "create_agent_definition", fake_create_definition)

    async def fake_ensure_default(db):
        """默认定义事务由真实 HTTP 集成验证。"""
        return await repo_cls(db).ensure_default_agent()

    monkeypatch.setattr(agent_router_module, "ensure_default_agent_definition", fake_ensure_default)

    async def fake_serialize(db, item, **kwargs):
        """路由只装配协议，治理投影由真实 HTTP 集成验证。"""
        return dict(item.__dict__)

    monkeypatch.setattr(agent_router_module, "serialize_agent_definition", fake_serialize)

    app = FastAPI()
    app.include_router(agent_router_module.agent_router, prefix="/api")

    async def fake_db():
        return None

    async def fake_user():
        return _user(role)

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_required_user] = fake_user
    app.dependency_overrides[get_admin_user] = fake_user
    return TestClient(app)


def test_all_agents_are_ordinary_definitions(monkeypatch):
    client = _build_app(monkeypatch, _ListRepo)
    response = client.get("/api/agent")
    assert response.status_code == 200, response.text
    assert [item["slug"] for item in response.json()["agents"]] == ["chatbot", "worker"]
    assert all("is_subagent" not in item for item in response.json()["agents"])
    response = client.get("/api/agent/worker")
    assert response.status_code == 200, response.text
    assert response.json()["agent"]["slug"] == "worker"


def test_normal_user_can_create_agent(monkeypatch):
    _CreateRepo.created_payload = None
    client = _build_app(monkeypatch, _CreateRepo, role="user")

    response = client.post(
        "/api/agent",
        json={
            "name": "Personal Bot",
            "slug": "personal-bot",
            "backend_id": "ChatbotAgent",
            "share_config": {
                "version": 2,
                "read_scope": {"access_level": "global"},
                "manage_scope": None,
            },
        },
    )

    assert response.status_code == 200, response.text
    assert _CreateRepo.created_payload["created_by"] == "user"
    assert _CreateRepo.created_payload["share_config"] == {
        "version": 2,
        "read_scope": {"access_level": "global"},
        "manage_scope": None,
    }
