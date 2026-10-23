"""展示名 Skill 包经过真实 HTTP、数据库和文件安装边界的结果。"""

from __future__ import annotations

import io
import uuid
import zipfile

import pytest
import yaml
from sqlalchemy import select

from yuxi.infrastructure.runtime_settings import get_skill_data_dir
from yuxi.modules.extensions.skills.models import Skill
from yuxi.modules.workspace.paths import user_workspace_dir

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


@pytest.mark.parametrize("scope", ["shared", "personal"])
@pytest.mark.parametrize(("display_name", "base_slug"), [("周易智慧", "zhouyizhihui"), ("PRD to Prototype", "prd-to-prototype")])
async def test_display_name_zip_install_preserves_name_and_persists_slug(
    test_client, admin_headers, postgres_sessions, scope, display_name, base_slug
):
    """共享同名分配后缀，个人安装不建共享索引，文件均保留名称和最终标识。"""
    suffix = uuid.uuid4().hex[:10]
    name = f"{display_name} {suffix}"
    slug = f"{base_slug}-{suffix}"
    content = f"---\nname: {name}\ndescription: pytest display name import\n---\n# Verification\n{suffix}\n"
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("unrelated-archive-name/SKILL.md", content)
        package.writestr("unrelated-archive-name/notes.md", suffix)
    profile = await test_client.get("/api/auth/me", headers=admin_headers)
    assert profile.status_code == 200, profile.text
    uid = profile.json()["uid"]
    installed = []
    drafts = []
    try:
        for index in range(2 if scope == "shared" else 1):
            prepared = await test_client.post(
                "/api/skills/import/prepare",
                headers=admin_headers,
                files={"file": ("community.zip", archive.getvalue(), "application/zip")},
            )
            assert prepared.status_code == 200, prepared.text
            draft = prepared.json()["data"]
            drafts.append(draft["draft_id"])
            assert draft["items"][0]["slug"] == slug
            assert draft["items"][0]["name"] == name
            prefix = "/api/skills" if scope == "shared" else "/api/skills/personal"
            confirmed = await test_client.post(
                f"{prefix}/install-drafts/{draft['draft_id']}/confirm",
                headers=admin_headers,
                json={"slugs": [slug], **({"share_config": None} if scope == "shared" else {})},
            )
            assert confirmed.status_code == 200, confirmed.text
            result = confirmed.json()["data"][0]
            assert result["success"] is True, result
            installed.append(result["slug"])
            expected_slug = slug if index == 0 else f"{slug}-v2"
            assert result["slug"] == expected_slug
            assert result["skill"]["name"] == name

            async with postgres_sessions() as db:
                row = (await db.execute(select(Skill).where(Skill.slug == expected_slug))).scalar_one_or_none()
                if scope == "shared":
                    assert row is not None
                    assert (row.slug, row.name) == (expected_slug, name)
                    root = get_skill_data_dir() / row.dir_path
                else:
                    assert row is None
                    root = user_workspace_dir(uid) / "agents" / "skills" / expected_slug
            saved = (root / "SKILL.md").read_text(encoding="utf-8")
            metadata = yaml.safe_load(saved.split("---", 2)[1])
            assert metadata["name"] == name
            assert metadata["slug"] == expected_slug
            assert saved.endswith(f"# Verification\n{suffix}\n")
            assert (root / "notes.md").read_text() == suffix

            file_prefix = "/api/system/skills" if scope == "shared" else "/api/skills/personal"
            preview = await test_client.get(f"{file_prefix}/{expected_slug}/file", params={"path": "SKILL.md"}, headers=admin_headers)
            assert preview.status_code == 200, preview.text
            assert preview.json()["data"]["content"] == saved
    finally:
        for installed_slug in reversed(installed):
            prefix = "/api/system/skills" if scope == "shared" else "/api/skills/personal"
            deleted = await test_client.delete(f"{prefix}/{installed_slug}", headers=admin_headers)
            assert deleted.status_code == 200, deleted.text
        for draft_id in drafts:
            discarded = await test_client.delete(f"/api/skills/install-drafts/{draft_id}", headers=admin_headers)
            assert discarded.status_code in {200, 404}, discarded.text


@pytest.mark.parametrize(
    ("metadata", "reason"),
    [
        ("name: 展示名\nslug: Invalid_Slug\ndescription: demo", "frontmatter.slug 必须是小写字母/数字/短横线"),
        ('name: demo\ndescription: "PRIVATE_YAML_MARKER', "frontmatter YAML 解析失败"),
    ],
)
async def test_skill_import_rejects_invalid_metadata_with_safe_business_detail(test_client, admin_headers, metadata, reason):
    """真实协议保留校验原因，同时拒绝回显 YAML 输入。"""
    response = await test_client.post(
        "/api/skills/import/prepare",
        headers=admin_headers,
        files={"file": ("SKILL.md", f"---\n{metadata}\n---\n".encode(), "text/markdown")},
    )
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "skill_request_invalid"
    assert reason in detail["message"]
    assert "PRIVATE_YAML_MARKER" not in response.text


@pytest.mark.parametrize("explicit_slug", [False, True])
async def test_skill_import_with_unchanged_identity_preserves_file_revision(test_client, admin_headers, explicit_slug):
    """已有相同显式标识时，安装保留注释和 CRLF 对应的正文及文件修订。"""
    import hashlib

    slug = f"pytest-format-{uuid.uuid4().hex[:10]}"
    identity = f"name: 展示名\r\nslug: {slug}" if explicit_slug else f"name: {slug}"
    content = f"---\r\n# preserve comment\r\n{identity}\r\ndescription: demo\r\n---\r\n# Body\r\n"
    prepared = await test_client.post(
        "/api/skills/import/prepare",
        headers=admin_headers,
        files={"file": ("SKILL.md", content.encode(), "text/markdown")},
    )
    assert prepared.status_code == 200, prepared.text
    draft_id = prepared.json()["data"]["draft_id"]
    installed = False
    try:
        confirmed = await test_client.post(
            f"/api/skills/install-drafts/{draft_id}/confirm",
            headers=admin_headers,
            json={"slugs": [slug], "share_config": None},
        )
        assert confirmed.status_code == 200, confirmed.text
        result = confirmed.json()["data"][0]
        assert result["success"] is True, result
        installed = True
        preview = await test_client.get(f"/api/system/skills/{slug}/file", params={"path": "SKILL.md"}, headers=admin_headers)
        assert preview.status_code == 200, preview.text
        assert preview.json()["data"]["content"] == content
        assert preview.json()["data"]["revision"] == hashlib.sha256(content.encode()).hexdigest()
        root = get_skill_data_dir() / result["skill"]["dir_path"]
        assert (root / "SKILL.md").read_bytes() == content.encode()
        package = await test_client.get(f"/api/system/skills/{slug}/content", headers=admin_headers)
        assert package.status_code == 200, package.text
        saved = await test_client.put(
            f"/api/system/skills/{slug}/content",
            headers=admin_headers,
            json={
                "expected_revision": package.json()["data"]["revision"],
                "changes": [{"action": "create", "path": "notes.md", "content": "only notes changed"}],
            },
        )
        assert saved.status_code == 200, saved.text
        root = get_skill_data_dir() / saved.json()["data"]["skill"]["dir_path"]
        assert (root / "SKILL.md").read_bytes() == content.encode()
        assert (root / "notes.md").read_text() == "only notes changed"
    finally:
        if installed:
            deleted = await test_client.delete(f"/api/system/skills/{slug}", headers=admin_headers)
            assert deleted.status_code == 200, deleted.text
        discarded = await test_client.delete(f"/api/skills/install-drafts/{draft_id}", headers=admin_headers)
        assert discarded.status_code in {200, 404}, discarded.text
