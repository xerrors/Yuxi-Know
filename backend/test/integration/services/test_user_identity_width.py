"""真实 PostgreSQL 与 HTTP 验证企业 UID 的持久化和私有归属。"""

import pytest
from fastapi import FastAPI
from sqlalchemy import select, text

from test.integration.support.module_audit import isolated_audit_store, serve_http
from yuxi.api.dependencies.auth import get_db
from yuxi.api.errors import domain_error_handler
from yuxi.api.routers.agents.management import agent_router
from yuxi.modules.agents.models.definitions import Agent
from yuxi.modules.extensions.skills.models import Skill, SkillVersion
from yuxi.modules.identity.models import APIKey, Department, User
from yuxi.modules.identity.security import AuthUtils
from yuxi.modules.knowledge.models import EvaluationDataset, EvaluationRun, KnowledgeBase, KnowledgeFile
from yuxi.shared.errors import DomainError

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]

# 独立列清单核对当前基线，不从 ORM 生成预期。
OWNERSHIP_COLUMNS = {
    "agents": ("created_by", "updated_by"),
    "skills": ("created_by", "updated_by"),
    "skill_versions": ("created_by",),
    "api_keys": ("created_by",),
    "knowledge_bases": ("created_by",),
    "knowledge_files": ("created_by", "updated_by"),
    "evaluation_datasets": ("created_by",),
    "evaluation_runs": ("created_by",),
}


async def seed_owned_records(sessions, uid):
    """写入两域相互关联的归属记录及非归属业务哨兵。"""
    async with sessions() as db:
        user = User(uid=uid, username="fixture", role="user", password_hash="fixture")
        skill = Skill(slug="fixture", name="fixture", description="sentinel", dir_path="shared/fixture", share_config={})
        kb = KnowledgeBase(kb_id="fixture", name="fixture", kb_type="milvus", created_by=uid)
        db.add_all([user, skill, kb])
        skill.created_by = skill.updated_by = uid
        db.add(Agent(slug="fixture", name="sentinel", backend_id="ChatbotAgent", created_by=uid, updated_by=uid, share_config={}))
        await db.flush()
        db.add_all(
            [
                APIKey(key_hash="fixture", key_prefix="fixture", name="fixture", user_id=user.id, created_by=uid),
                SkillVersion(
                    skill_id=skill.id, version="1", dir_path="shared/fixture", metadata_json={}, content_hash="sentinel", created_by=uid
                ),
                KnowledgeFile(file_id="fixture", kb_id=kb.kb_id, filename="sentinel.txt", created_by=uid, updated_by=uid),
                EvaluationDataset(dataset_id="fixture", kb_id=kb.kb_id, name="sentinel", created_by=uid),
            ]
        )
        await db.flush()
        db.add(EvaluationRun(run_id="fixture", kb_id=kb.kb_id, dataset_id="fixture", name="sentinel", created_by=uid))
        await db.commit()


async def test_current_baseline_persists_full_uid_in_all_ownership_columns(monkeypatch):
    """当前基线全部归属列保存完整 128 位身份，跨域关联记录保持有效。"""
    async with isolated_audit_store(monkeypatch) as (manager, sessions):
        uid = "oidc:" + "a" * 123
        await seed_owned_records(sessions, uid)
        async with manager.async_engine.connect() as conn:
            for table, columns in OWNERSHIP_COLUMNS.items():
                for column in columns:
                    assert await conn.scalar(text(f"SELECT {column} FROM {table} LIMIT 1")) == uid
                    assert await conn.scalar(
                        text(
                            "SELECT character_maximum_length FROM information_schema.columns "
                            "WHERE table_schema=current_schema() AND table_name=:table AND column_name=:column"
                        ),
                        {"table": table, "column": column},
                    ) == 128


@pytest.mark.parametrize("width", [69, 128])
async def test_full_uid_creates_updates_private_agent_over_http(monkeypatch, width):
    """真实 JWT 身份写入完整归属，其他普通用户不能读取或更新私有智能体。"""
    async with isolated_audit_store(monkeypatch) as (_, sessions):
        async with sessions() as db:
            department = Department(name="fixture")
            db.add(department)
            await db.flush()
            owner = User(
                department_id=department.id, uid="oidc:" + "a" * (width - 5), username="owner", role="user", password_hash="fixture"
            )
            other = User(department_id=department.id, uid="other", username="other", role="user", password_hash="fixture")
            db.add_all([owner, other])
            await db.commit()
            headers = {"Authorization": "Bearer " + AuthUtils.create_access_token({"sub": str(owner.id), "auth_method": "password"})}
            outsider = {"Authorization": "Bearer " + AuthUtils.create_access_token({"sub": str(other.id), "auth_method": "password"})}
        app = FastAPI()
        app.include_router(agent_router, prefix="/api")
        app.add_exception_handler(DomainError, domain_error_handler)

        async def request_db():
            """请求 session 与独立持久回读使用同一隔离数据库。"""
            async with sessions() as db:
                yield db

        app.dependency_overrides[get_db] = request_db
        async with serve_http(app) as client:
            response = await client.post(
                "/api/agent", headers=headers, json={"slug": "owned", "name": "Original", "backend_id": "ChatbotAgent"}
            )
            assert response.status_code == 200, response.text
            changed = await client.put("/api/agent/owned", headers=headers, json={"name": "Updated"})
            assert changed.status_code == 200, changed.text
            assert (await client.get("/api/agent/owned", headers=outsider)).status_code == 404
            assert (await client.put("/api/agent/owned", headers=outsider, json={"name": "forbidden"})).status_code == 404
        async with sessions() as db:
            row = await db.scalar(select(Agent).where(Agent.slug == "owned"))
            assert (row.created_by, row.updated_by, row.visibility, row.name) == (owner.uid, owner.uid, "private", "Updated")
