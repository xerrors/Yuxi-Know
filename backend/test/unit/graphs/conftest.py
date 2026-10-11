from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from yuxi.modules.knowledge.graphs import milvus_graph_service
from yuxi.modules.knowledge.graphs.milvus_graph_service import MilvusGraphService


@pytest.fixture
def milvus_graph_projection_lock(monkeypatch):
    """图单测替换 PostgreSQL 投影锁，真实互斥由 integration 验证。"""

    @asynccontextmanager
    async def lock(*args, **kwargs):
        """满足异步上下文协议，不测试锁的并发语义。"""
        yield

    monkeypatch.setattr(milvus_graph_service, "knowledge_projection_lock", lock)
    monkeypatch.setattr(MilvusGraphService, "_filter_visible_subgraph", AsyncMock(side_effect=lambda kb_id, result: result))
