from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from server.routers import knowledge_eval_router
from server.utils.auth_middleware import get_required_user
from server.utils import knowledge_permissions
from yuxi.permissions import ResourcePermission


@pytest.mark.asyncio
async def test_dataset_only_manage_route_checks_the_dataset_knowledge_base(monkeypatch):
    calls = []

    async def fake_get_dataset(_repository, _dataset_id):
        return SimpleNamespace(kb_id="kb-1")

    async def fake_ensure_permission(kb_id, current_user, required):
        calls.append((kb_id, current_user, required))
        return {}

    monkeypatch.setattr(knowledge_eval_router.EvaluationRepository, "get_dataset", fake_get_dataset)
    monkeypatch.setattr(knowledge_eval_router, "ensure_knowledge_base_permission", fake_ensure_permission)
    admin = SimpleNamespace(uid="admin-1", role="admin", department_id=1)

    result = await knowledge_eval_router.require_evaluation_dataset_manage("dataset-1", admin)

    assert result is admin
    assert calls == [("kb-1", admin, ResourcePermission.MANAGE)]


@pytest.mark.asyncio
async def test_dataset_manage_route_rejects_admin_without_manage_permission(monkeypatch):
    async def fake_get_dataset(_repository, _dataset_id):
        return SimpleNamespace(kb_id="kb-1")

    async def fake_get_database_info(_kb_id):
        return {
            "created_by": "owner",
            "share_config": {
                "version": 2,
                "read_scope": {"access_level": "global"},
                "manage_scope": None,
            },
        }

    monkeypatch.setattr(knowledge_eval_router.EvaluationRepository, "get_dataset", fake_get_dataset)
    monkeypatch.setattr(knowledge_permissions.knowledge_base, "get_database_info", fake_get_database_info)
    admin = SimpleNamespace(uid="other-admin", role="admin", department_id=1)

    with pytest.raises(HTTPException) as exc_info:
        await knowledge_eval_router.require_evaluation_dataset_manage("dataset-1", admin)

    assert exc_info.value.status_code == 403


def test_evaluation_routes_require_admin_role():
    app = FastAPI()
    app.include_router(knowledge_eval_router.evaluation)

    async def fake_required_user():
        return SimpleNamespace(uid="user-1", role="user", department_id=1)

    app.dependency_overrides[get_required_user] = fake_required_user

    response = TestClient(app).get("/evaluation/databases/kb-1/datasets")

    assert response.status_code == 403
    assert response.json()["detail"] == "需要管理员权限"
