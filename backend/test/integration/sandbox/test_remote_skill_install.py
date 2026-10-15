"""真实 Cube、npm 和 Git 来源的内置技能安装验收。"""

from types import SimpleNamespace

import pytest

from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.infrastructure.redis import close_async_redis_client
from yuxi.modules.extensions.skills.personal import list_personal_skills, read_personal_skill_file
from yuxi.modules.extensions.tools.builtin.install_skill import install_skill
from yuxi.modules.workspace.paths import user_workspace_dir

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.slow, pytest.mark.self_managed_resources]


@pytest.mark.asyncio
async def test_remote_install_publishes_personal_skill_and_cleans_cli_home(resources):
    """回读个人列表与文件，确认真实 CLI 缓存不再阻断安装和清理。"""
    uid, _, _, _ = resources
    root = user_workspace_dir(uid)
    (root / "keep.txt").write_text("keep", encoding="utf-8")
    runtime = SimpleNamespace(context=SimpleNamespace(uid=uid, thread_id="remote-skill-install-test"))
    try:
        result = await install_skill.coroutine(
            "mattpocock/skills",
            skill_names=["grill-me"],
            runtime=runtime,
            tool_call_id="remote-skill-install",
        )

        message = result.update["messages"][0].content
        assert "已安装 Skill: grill-me" in message, message
        assert "grill-me" in {item.slug for item in await list_personal_skills(uid)}
        content = (await read_personal_skill_file(uid, "grill-me", "SKILL.md"))["content"]
        installed = root / "agents/skills/grill-me/SKILL.md"
        assert installed.read_text(encoding="utf-8") == content
        assert "name: grill-me" in content
        assert list((root / ".remote-skills").iterdir()) == []
        assert (root / "keep.txt").read_text(encoding="utf-8") == "keep"
    finally:
        await pg_manager.close()
        await close_async_redis_client()
