"""真实 HTTP 撤权后，知识工具不能继续读取。"""

import uuid
from types import SimpleNamespace

import pytest

from yuxi.infrastructure.postgres.models import load_models
from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.modules.extensions.tools.knowledge import tools
from yuxi.modules.knowledge.repositories.bases import KnowledgeBaseRepository
from yuxi.modules.knowledge.services.tools import KnowledgeToolError

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_knowledge_tools_reject_access_after_http_revocation(test_client, admin_headers, standard_user):
    """回读 PostgreSQL 撤权结果，Agent 和 Public 工具同时拒绝。"""
    load_models()
    owner = await test_client.get("/api/auth/me", headers=admin_headers)
    assert owner.status_code == 200, owner.text
    owner_uid = owner.json()["uid"]
    uid = standard_user["user"]["uid"]
    kb_id = f"pytest_access_{uuid.uuid4().hex[:12]}"
    share_config = {
        "version": 2,
        "read_scope": {"access_level": "user", "department_ids": [], "user_uids": [uid]},
        "manage_scope": None,
    }
    repository = KnowledgeBaseRepository()
    pg_manager.initialize()
    try:
        await repository.create(
            {
                "kb_id": kb_id,
                "name": kb_id,
                "kb_type": "milvus",
                "created_by": owner_uid,
                "share_config": share_config,
            }
        )
        runtime = SimpleNamespace(context=SimpleNamespace(uid=uid, knowledges=[kb_id]))
        assert [kb["kb_id"] for kb in await tools.list_kbs.coroutine(dummy="", runtime=runtime)] == [kb_id]

        share_config["read_scope"]["user_uids"] = [owner_uid]
        changed = await test_client.put(
            f"/api/knowledge/knowledge-bases/{kb_id}",
            headers=admin_headers,
            json={"name": kb_id, "description": "", "share_config": share_config},
        )
        assert changed.status_code == 200, changed.text
        persisted = await repository.get_by_kb_id(kb_id)
        assert persisted is not None and persisted.share_config == share_config

        with pytest.raises(KnowledgeToolError, match="无法获取当前会话可访问的知识库") as rejected:
            await tools.query_kb.coroutine(kb_id=kb_id, query_text="private", runtime=runtime)
        assert rejected.value.not_found
        denied = await test_client.post(
            "/api/v1/knowledge/tools/query_kb",
            headers=standard_user["headers"],
            json={"kb_id": kb_id, "query_text": "private"},
        )
        assert denied.status_code == 404, denied.text
    finally:
        await repository.purge(kb_id)
        await pg_manager.close()
