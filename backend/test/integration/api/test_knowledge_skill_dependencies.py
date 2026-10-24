"""正式 HTTP 发布知识 Skill 时只接受 MCP 依赖，并回读数据库与包内容。"""

from __future__ import annotations

import hashlib
import uuid
from io import BytesIO
from zipfile import ZipFile

import pytest
import yaml
from sqlalchemy import select

from yuxi.infrastructure.runtime_settings import get_skill_data_dir
from yuxi.modules.agents.models.definitions import Agent
from yuxi.modules.extensions.skills.models import Skill

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


def knowledge_skill_content(slug, *, local_dependency=False):
    """显式声明本例包内容，预期不由被测代码生成。"""
    dependencies = (
        "tool_dependencies: [query_kb]\nmcp_dependencies: []\n"
        if local_dependency
        else "tool_dependencies: []\nmcp_dependencies: [knowledge]\n"
    )
    return (
        f"---\nslug: {slug}\nname: Independent Knowledge Skill\n"
        f"description: Synthetic MCP dependency regression\n{dependencies}---\n"
        "# Guide\nRead knowledge through MCP.\n"
    )


def skill_zip(content):
    """使用真实 ZIP 经过专属 Skill 的正式导入入口。"""
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("bundle/SKILL.md", content)
    return buffer.getvalue()


async def read_published_facts(test_client, headers, postgres_sessions, slug):
    """独立回读 HTTP、数据库和当前包字节，避免仅信任发布响应。"""
    response = await test_client.get(f"/api/system/skills/{slug}/file", params={"path": "SKILL.md"}, headers=headers)
    assert response.status_code == 200, response.text
    http_fact = response.json()["data"]
    async with postgres_sessions() as db:
        row = await db.scalar(select(Skill).where(Skill.slug == slug))
        assert row is not None
        raw = (get_skill_data_dir() / row.dir_path / "SKILL.md").read_bytes()
        metadata = yaml.safe_load(raw.decode().split("---", 2)[1])
        assert http_fact["content"] == raw.decode()
        assert http_fact["revision"] == hashlib.sha256(raw).hexdigest()
        assert row.tool_dependencies == metadata.get("tool_dependencies", []) == http_fact["skill"]["tool_dependencies"]
        assert row.mcp_dependencies == metadata.get("mcp_dependencies", []) == http_fact["skill"]["mcp_dependencies"]
        return {
            "bytes": raw,
            "directory": row.dir_path,
            "tools": row.tool_dependencies,
            "mcps": row.mcp_dependencies,
            "revision": http_fact["revision"],
        }


@pytest.mark.parametrize("source_kind", ["shared", "agent_bound"])
async def test_new_knowledge_skill_rejects_local_dependencies_and_publishes_mcp_contract(
    source_kind, test_client, admin_headers, postgres_sessions
):
    """新建和修改两种来源均拒绝旧本地依赖，失败不能改变已发布事实。"""
    suffix = uuid.uuid4().hex[:12]
    requested_slug = f"pytest-kb-contract-{suffix}"
    agent_slug = None
    published_slug = None
    drafts = []
    try:
        if source_kind == "agent_bound":
            agent_slug = f"pytest_kb_contract_{suffix}"
            created = await test_client.post(
                "/api/agent", headers=admin_headers, json={"name": "Knowledge contract regression", "slug": agent_slug}
            )
            assert created.status_code == 200, created.text

        for local_dependency in [True, False]:
            content = knowledge_skill_content(requested_slug, local_dependency=local_dependency)
            if source_kind == "shared":
                prepared = await test_client.post(
                    "/api/skills/import/prepare",
                    headers=admin_headers,
                    files={"file": ("SKILL.md", content.encode(), "text/markdown")},
                )
                assert prepared.status_code == 200, prepared.text
                draft_id = prepared.json()["data"]["draft_id"]
                drafts.append(draft_id)
                installed = await test_client.post(
                    f"/api/skills/install-drafts/{draft_id}/confirm",
                    headers=admin_headers,
                    json={"slugs": [requested_slug], "share_config": None},
                )
                assert installed.status_code == 200, installed.text
                result = installed.json()["data"][0]
                if local_dependency:
                    assert result["success"] is False
                    assert "无效工具依赖" in result["error"] and "query_kb" in result["error"]
                    async with postgres_sessions() as db:
                        assert await db.scalar(select(Skill).where(Skill.slug == requested_slug)) is None
                    assert not (get_skill_data_dir() / "packages" / requested_slug).exists()
                else:
                    assert result["success"] is True, result
                    published_slug = result["skill"]["slug"]
            else:
                installed = await test_client.post(
                    f"/api/agent/{agent_slug}/self-skill/upload",
                    headers=admin_headers,
                    files={"file": ("knowledge.zip", skill_zip(content), "application/zip")},
                )
                if local_dependency:
                    assert installed.status_code == 422, installed.text
                    assert "无效工具依赖" in installed.text and "query_kb" in installed.text
                    binding = await test_client.get(f"/api/agent/{agent_slug}/self-skill", headers=admin_headers)
                    assert binding.status_code == 200, binding.text
                    assert binding.json()["skill"] is None
                    async with postgres_sessions() as db:
                        agent_id = await db.scalar(select(Agent.id).where(Agent.slug == agent_slug))
                        assert await db.scalar(select(Skill).where(Skill.bound_agent_id == agent_id)) is None
                else:
                    assert installed.status_code == 200, installed.text
                    published_slug = installed.json()["skill"]["slug"]

        assert published_slug is not None
        original = await read_published_facts(test_client, admin_headers, postgres_sessions, published_slug)
        assert original["tools"] == [] and original["mcps"] == ["knowledge"]
        rejected = await test_client.put(
            f"/api/system/skills/{published_slug}/dependencies",
            headers=admin_headers,
            json={
                "tool_dependencies": ["query_kb"],
                "mcp_dependencies": [],
                "skill_dependencies": [],
                "expected_revision": original["revision"],
            },
        )
        assert rejected.status_code == 400, rejected.text
        assert "无效工具依赖" in rejected.text and "query_kb" in rejected.text
        unchanged = await read_published_facts(test_client, admin_headers, postgres_sessions, published_slug)
        assert unchanged == original, "拒绝本地知识依赖后包内容或持久元数据发生变化"

        removed = await test_client.put(
            f"/api/system/skills/{published_slug}/dependencies",
            headers=admin_headers,
            json={"tool_dependencies": [], "mcp_dependencies": [], "skill_dependencies": [], "expected_revision": original["revision"]},
        )
        assert removed.status_code == 200, removed.text
        empty = await read_published_facts(test_client, admin_headers, postgres_sessions, published_slug)
        assert empty["tools"] == [] and empty["mcps"] == []
        restored = await test_client.put(
            f"/api/system/skills/{published_slug}/dependencies",
            headers=admin_headers,
            json={
                "tool_dependencies": [],
                "mcp_dependencies": ["knowledge"],
                "skill_dependencies": [],
                "expected_revision": empty["revision"],
            },
        )
        assert restored.status_code == 200, restored.text
        final = await read_published_facts(test_client, admin_headers, postgres_sessions, published_slug)
        assert final["tools"] == [] and final["mcps"] == ["knowledge"]
    finally:
        if agent_slug:
            deleted = await test_client.delete(f"/api/agent/{agent_slug}", headers=admin_headers)
            assert deleted.status_code == 200, deleted.text
        elif published_slug:
            deleted = await test_client.delete(f"/api/system/skills/{published_slug}", headers=admin_headers)
            assert deleted.status_code == 200, deleted.text
        for draft_id in drafts:
            discarded = await test_client.delete(f"/api/skills/install-drafts/{draft_id}", headers=admin_headers)
            assert discarded.status_code in {200, 404}, discarded.text
