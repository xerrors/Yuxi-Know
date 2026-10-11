from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from yuxi.api.dependencies.auth import get_db, get_required_user
from yuxi.api.routers.agents import mentions
from yuxi.modules.agents.services.mentions import InvalidMentionThreadError, MentionThreadNotFoundError


@pytest.mark.parametrize(
    ("error_type", "status_code", "detail"),
    [
        (MentionThreadNotFoundError, 404, "thread not found"),
        (InvalidMentionThreadError, 400, "invalid thread id"),
    ],
)
def test_mention_search_maps_domain_errors_to_http(error_type, status_code, detail, monkeypatch):
    """提及搜索必须把领域可见性与输入错误映射为稳定 HTTP 响应。"""
    monkeypatch.setattr(mentions, "search_mentions", AsyncMock(side_effect=error_type(detail)))
    app = FastAPI()
    app.include_router(mentions.mention_router, prefix="/api")
    app.dependency_overrides[get_required_user] = lambda: SimpleNamespace(uid="user-1")
    app.dependency_overrides[get_db] = lambda: None

    response = TestClient(app).get("/api/mention/search?thread_id=thread-1&query=report")

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
