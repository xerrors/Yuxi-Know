"""Agent 专属 Skill 的绑定、整包发布与权限用例。"""

import asyncio
import shutil
import uuid
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.modules.agents.models.definitions import Agent
from yuxi.modules.agents.permissions import user_can_access_agent, user_can_manage_agent
from yuxi.modules.extensions.skills.content import commit_skill_content, content_path
from yuxi.modules.extensions.skills.install_draft import prepared_uploaded_skill
from yuxi.modules.extensions.skills.models import Skill
from yuxi.modules.extensions.skills.package import SkillEditConflict, parse_skill_dir_metadata
from yuxi.modules.extensions.skills.projection import (
    compute_skill_directory_hash,
)
from yuxi.modules.extensions.skills.repository import SkillRepository
from yuxi.modules.extensions.skills.access import get_skills_root_dir
from yuxi.modules.identity.models import User
from yuxi.modules.identity.permissions import resolve_agent_permission
from yuxi.modules.identity.repositories.users import UserRepository


async def get_agent_bound_skill(db: AsyncSession, *, agent_slug: str, operator: User) -> dict:
    """返回绑定与同一次读取的整包修订值，不暴露独立共享配置。"""
    agent = await db.scalar(select(Agent).where(Agent.slug == agent_slug))
    if agent is None or not user_can_access_agent(operator, agent):
        raise PermissionError("智能体不存在或无权限访问")
    item = await SkillRepository(db).get_by_bound_agent_id(agent.id)
    if item is None:
        return {"skill": None, "revision": None, "can_manage": user_can_manage_agent(operator, agent)}
    item = await SkillRepository(db).get_by_slug_for_read(item.slug)
    if item is None or not user_can_access_agent(operator, item.bound_agent):
        raise PermissionError("智能体不存在或无权限访问")
    return await describe_bound_skill(item, operator)


async def create_agent_bound_skill(db: AsyncSession, *, agent_slug: str, operator: User) -> dict:
    """幂等创建最小操作指南，Agent 行锁串行化绑定写入。"""
    agent, operator = await lock_manageable_agent(db, agent_slug, operator)
    existing = await SkillRepository(db).get_by_bound_agent_id(agent.id, for_update=True)
    if existing is not None:
        return await describe_bound_skill(existing, operator)
    slug = "agent-guide"
    root = get_skills_root_dir()
    staging = root / f".bound-{uuid.uuid4().hex}.tmp"
    staging.mkdir()
    try:
        content = (
            "---\n"
            + yaml.safe_dump(
                {"slug": slug, "name": f"{agent.name} 操作指南", "description": "智能体专属操作指南与资源"},
                allow_unicode=True,
                sort_keys=False,
            )
            + "---\n\n# 操作指南\n\n在此记录操作流程；角色与回答风格在系统提示词中配置。\n"
        )
        (staging / "SKILL.md").write_text(content, encoding="utf-8")
        return await publish_bound_skill(db, agent=agent, operator=operator, source=staging, source_slug=slug)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


async def upload_agent_bound_skill(
    db: AsyncSession,
    *,
    agent_slug: str,
    filename: str,
    file_bytes: bytes,
    operator: User,
) -> dict:
    """仅为尚未绑定 Skill 的 Agent 导入 ZIP，持锁拒绝覆盖已有内容。"""
    agent, operator = await lock_manageable_agent(db, agent_slug, operator)
    with prepared_uploaded_skill(filename=filename, file_bytes=file_bytes) as source:
        return await publish_bound_skill(
            db,
            agent=agent,
            operator=operator,
            source=source,
            source_slug=parse_skill_dir_metadata(source)["slug"],
        )


async def lock_manageable_agent(db: AsyncSession, slug: str, operator: User) -> tuple[Agent, User]:
    """先锁 Agent，再刷新实际操作者，绑定写入沿用同一授权。"""
    agent = await db.scalar(select(Agent).where(Agent.slug == slug).with_for_update().execution_options(populate_existing=True))
    operator = await UserRepository(db).lock_active_human(operator.uid)
    if agent is None or operator is None or not user_can_manage_agent(operator, agent):
        raise PermissionError("智能体不存在或无权管理")
    return agent, operator


async def describe_bound_skill(item: Skill, operator: User, revision: str | None = None) -> dict:
    """绑定元数据与目录字节同受 Skill 行锁保护。"""
    path = content_path(item)
    if revision is None:
        revision = (await asyncio.to_thread(compute_skill_directory_hash, path)).hex()
    skill = item.to_dict()
    skill.pop("share_config", None)
    skill["can_manage"] = user_can_manage_agent(operator, item.bound_agent)
    skill["effective_permission"] = resolve_agent_permission(operator, item.bound_agent).value
    return {"skill": skill, "revision": revision, "can_manage": skill["can_manage"]}


async def publish_bound_skill(
    db: AsyncSession,
    *,
    agent: Agent,
    operator: User,
    source: Path,
    source_slug: str,
) -> dict:
    """首次发布专属包，已有绑定只能通过统一内容编辑入口修改。"""
    if await SkillRepository(db).get_by_bound_agent_id(agent.id, for_update=True) is not None:
        raise SkillEditConflict("已存在专属 Skill，请通过编辑入口修改内容")
    item = Skill(
        slug=f"self-{uuid.uuid4().hex[:8]}",
        bound_agent_id=agent.id,
        bound_agent=agent,
        source_type="upload",
        share_config={},
        enabled=True,
        created_by=operator.uid,
    )
    result = await commit_skill_content(
        db,
        item=item,
        operator=operator,
        expected_revision=None,
        source=source,
        source_slug=source_slug,
    )
    return await describe_bound_skill(result.skill, operator, result.revision)
