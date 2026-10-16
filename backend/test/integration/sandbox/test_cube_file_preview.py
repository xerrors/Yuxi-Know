"""真实 VM、文件工具与 HTTP 预览读取同一用户投影。"""

import base64
import shutil
import uuid

import pytest
from sqlalchemy import delete, update

from test.integration.api.helpers import create_default_agent_thread, delete_created_threads
from yuxi.modules.extensions.skills.access import get_skills_root_dir
from yuxi.modules.extensions.skills.models import Skill
from yuxi.modules.extensions.skills.projection import sync_user_accessible_skills

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


async def test_skill_projection_bytes_match_vm_tools_and_http(resources, test_client, postgres_sessions):
    """来源变化、投影缺失、符号链接和撤权均不能改变实际挂载的读取边界。"""
    uid, password, provider, backend = resources
    slug = f"pytest-preview-{uuid.uuid4().hex}"
    source = get_skills_root_dir() / slug
    source.mkdir()
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j4AAAAABJRU5ErkJggg==")
    (source / "image.png").write_bytes(png)
    thread_id = None
    try:
        async with postgres_sessions() as db:
            db.add(
                Skill(
                    slug=slug,
                    name=slug,
                    description="用户投影读取集成测试",
                    source_type="upload",
                    dir_path=f"shared/{slug}",
                    share_config={
                        "version": 2,
                        "read_scope": {"access_level": "user", "department_ids": [], "user_uids": [uid]},
                        "manage_scope": None,
                    },
                    enabled=True,
                )
            )
            await db.commit()
        projection = sync_user_accessible_skills(uid, {slug: source}) / slug
        (source / "image.png").write_bytes(png + b"new-source-version")
        path = f"/home/user/skills/{slug}/image.png"

        guest = backend.execute(f"base64 -w0 {path}")
        assert guest.exit_code == 0, guest.output
        assert base64.b64decode(guest.output) == png
        assert base64.b64decode(backend.read(path).file_data["content"]) == png
        readonly = backend.execute(f"printf forbidden > {path}")
        assert readonly.exit_code != 0
        assert (projection / "image.png").read_bytes() == png

        login = await test_client.post("/api/auth/token", data={"username": uid, "password": password})
        assert login.status_code == 200, login.text
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        thread_id = await create_default_agent_thread(test_client, headers, title_prefix="skill-projection-preview")
        url = f"/api/v1/agents/sessions/{thread_id}/artifacts/{path.lstrip('/')}"
        for params in ({"preview": "true"}, {"download": "true"}):
            response = await test_client.get(url, params=params, headers=headers)
            assert response.status_code == 200, response.text
            assert response.headers["content-type"].startswith("image/png")
            assert response.content == png
        saved = await test_client.post(f"/api/v1/agents/sessions/{thread_id}/artifacts/save", json={"path": path}, headers=headers)
        assert saved.status_code == 200, saved.text
        assert base64.b64decode(backend.read(saved.json()["saved_path"]).file_data["content"]) == png

        environment = provider.get(uid)
        provider.adapter.pause(environment)
        paused = await test_client.get(url, params={"preview": "true"}, headers=headers)
        assert paused.status_code == 200, paused.text
        assert paused.content == png
        assert provider.adapter.state(environment).lower() == "paused"

        (projection / "image.png").unlink()
        missing = await test_client.get(url, headers=headers)
        assert missing.status_code == 404, missing.text
        (projection / "image.png").symlink_to(source / "image.png")
        linked = await test_client.get(url, headers=headers)
        assert linked.status_code == 403, linked.text
        (projection / "image.png").unlink()
        (projection / "image.png").write_bytes(png)

        async with postgres_sessions() as db:
            await db.execute(
                update(Skill)
                .where(Skill.slug == slug)
                .values(
                    share_config={
                        "version": 2,
                        "read_scope": {"access_level": "user", "department_ids": [], "user_uids": ["another-user"]},
                        "manage_scope": None,
                    }
                )
            )
            await db.commit()
        revoked = await test_client.get(url, headers=headers)
        assert revoked.status_code == 403, revoked.text
        assert (projection / "image.png").read_bytes() == png
    finally:
        await delete_created_threads(thread_id)
        async with postgres_sessions() as db:
            await db.execute(delete(Skill).where(Skill.slug == slug))
            await db.commit()
        shutil.rmtree(source)
