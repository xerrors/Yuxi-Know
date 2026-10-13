"""系统管理员转移共享资源所有权。"""

from sqlalchemy import select

from yuxi.modules.agents.models.definitions import Agent
from yuxi.modules.extensions.skills.models import Skill
from yuxi.modules.extensions.skills.projection import commit_skill_policy_and_refresh_projections
from yuxi.modules.identity.models import User
from yuxi.modules.identity.repositories.users import UserRepository
from yuxi.modules.knowledge.cache import delete_cached_kb_config
from yuxi.modules.knowledge.models import KnowledgeBase


async def transfer_shared_resource(db, *, kind: str, resource_id: str, owner_uid: str, actor: User) -> None:
    """锁定共享对象与有效接收者，保持私有与内置定义边界。"""
    if actor.role != "superadmin" or actor.is_deleted:
        raise PermissionError("只有系统管理员可以转移所有权")
    if kind == "agent":
        model, key = Agent, Agent.slug
    elif kind == "skill":
        model, key = Skill, Skill.slug
    elif kind == "knowledge":
        model, key = KnowledgeBase, KnowledgeBase.kb_id
    else:
        raise ValueError("未知资源类型")
    resource = await db.scalar(select(model).where(key == resource_id).with_for_update(of=model))
    if resource is None:
        raise LookupError("资源不存在")
    actor = await UserRepository(db).lock_active_human(actor.uid)
    if actor is None or actor.role != "superadmin":
        raise PermissionError("只有系统管理员可以转移所有权")
    if kind == "agent" and (resource.visibility != "shared" or resource.is_builtin):
        raise ValueError("私有或内置 Agent 不能转移所有权")
    if kind == "skill" and resource.bound_agent_id is not None:
        raise ValueError("专属 Skill 的所有权跟随智能体")
    if kind == "skill" and resource.source_type == "builtin":
        raise ValueError("内置 Skill 不能转移所有权")
    owner = await db.scalar(
        select(User)
        .where(
            User.uid == owner_uid,
            User.is_deleted == 0,
            User.role.in_(("admin", "superadmin")),
            User.user_kind == "human",
        )
        .with_for_update(read=True)
    )
    if owner is None:
        raise ValueError("接收者必须是有效管理员")
    resource.created_by = owner.uid
    if kind == "knowledge":
        await delete_cached_kb_config(resource_id)
    if kind == "skill":
        await commit_skill_policy_and_refresh_projections(db, resource_id)
    elif kind == "agent":
        from yuxi.modules.agents.services.definitions import commit_agent_definition

        await commit_agent_definition(db, resource, actor)
    else:
        await db.commit()
