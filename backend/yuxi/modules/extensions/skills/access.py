"""共享与专属 Skill 的权限、依赖及带锁读取契约。"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.infrastructure.observability.logging import logger
from yuxi.infrastructure.runtime_settings import get_skill_data_dir
from yuxi.modules.extensions.skills.models import Skill
from yuxi.modules.extensions.skills.package import is_valid_skill_slug, normalize_string_list, validated_shared_skill_parts
from yuxi.modules.extensions.skills.repository import SkillRepository
from yuxi.modules.extensions.skills.resolved import ResolvedSkill
from yuxi.modules.identity.models import User
from yuxi.modules.identity.permissions import ResourcePermission, normalize_permission_config, resolve_skill_permission
from yuxi.modules.identity.permissions.resource_permission import ADMIN_ROLES

BUILTIN_SKILL_SHARE_CONFIG = {"access_level": "global", "department_ids": [], "user_uids": []}


async def lock_accessible_shared_skill_for_file(db: AsyncSession, user: User, slug: str) -> Skill | None:
    """在读取共享源文件期间锁定一行并重新检查权限。"""
    repo = SkillRepository(db)
    item = await repo.get_by_slug_for_read(slug)
    return item if item is not None and user_can_access_skill(user, item) else None


async def lock_accessible_shared_skills_for_runtime(
    db: AsyncSession,
    user: User,
    selected: list[str],
    *,
    shadowed_slugs: set[str] | None = None,
    bound_slug: str | None = None,
) -> list[Skill]:
    """只锁定已选共享 Skill 及其依赖，锁后重新检查权限。"""
    repo = SkillRepository(db)
    visible = {item.slug for item in await repo.list_enabled_readable(user)}
    if bound_slug:
        visible.add(bound_slug)
    shadowed = shadowed_slugs or set()
    pending = list(selected)
    locked: dict[str, Skill] = {}
    while pending:
        slug = pending.pop(0)
        if slug in shadowed or slug not in visible or slug in locked:
            continue
        item = await repo.get_by_slug_for_read(slug)
        if item is None or not user_can_access_skill(user, item):
            continue
        locked[slug] = item
        pending.extend(item.skill_dependencies or [])
    return list(locked.values())


async def validate_skill_dependencies(
    *,
    db: AsyncSession,
    parent: Skill,
    tool_dependencies: list[str],
    mcp_dependencies: list[str],
    skill_dependencies: list[str],
    available_skills: dict[str, Skill],
) -> tuple[list[str], list[str], list[str]]:
    """校验工具、MCP 和共享 Skill 依赖。"""
    tools = normalize_string_list(tool_dependencies)
    mcps = normalize_string_list(mcp_dependencies)
    skills = normalize_string_list(skill_dependencies)

    # 验证所有工具（不仅仅是 builtin）
    from yuxi.modules.extensions.mcp.service import get_enabled_mcp_server_slugs
    from yuxi.modules.extensions.tools.catalog import get_tool_metadata

    available_tools = {tool["slug"] for tool in get_tool_metadata()}
    invalid_tools = [name for name in tools if name not in available_tools]
    if invalid_tools:
        raise ValueError(f"存在无效工具依赖: {', '.join(invalid_tools)}")

    available_mcps = set(await get_enabled_mcp_server_slugs(db=db))
    invalid_mcps = [name for name in mcps if name not in available_mcps]
    if invalid_mcps:
        raise ValueError(f"存在无效 MCP 依赖: {', '.join(invalid_mcps)}")

    invalid_skills = [name for name in skills if name not in available_skills]
    if invalid_skills:
        raise ValueError(f"存在无效 skill 依赖: {', '.join(invalid_skills)}")

    if parent.slug in skills:
        raise ValueError("skill_dependencies 不允许包含自身")

    forbidden_skills = [name for name in skills if not can_skill_depend_on(parent, available_skills[name])]
    if forbidden_skills:
        raise ValueError(f"存在权限范围不匹配的 skill 依赖: {', '.join(forbidden_skills)}")

    return tools, mcps, skills


async def get_skill_or_raise(db: AsyncSession, slug: str, *, for_update: bool = False) -> Skill:
    """读取指定共享 Skill，必要时加独占行锁。"""
    slug = slug.strip() if isinstance(slug, str) else ""
    if not is_valid_skill_slug(slug):
        raise ValueError("无效 skill slug")

    repo = SkillRepository(db)
    item = await repo.get_by_slug(slug, for_update=True) if for_update else await repo.get_by_slug(slug)
    if not item:
        raise ValueError(f"技能 '{slug}' 不存在")
    return item


async def get_management_readable_skill_or_raise(db: AsyncSession, user: User, slug: str) -> Skill:
    """读取当前用户可查看的共享 Skill。"""
    item = await get_skill_or_raise(db, slug)
    if not user_can_manage_skill(user, item) and not user_can_access_skill(user, item):
        raise ValueError(f"技能 '{slug}' 不存在或无权访问")
    return item


async def get_manageable_skill_or_raise(db: AsyncSession, user: User, slug: str, *, for_update: bool = False) -> Skill:
    """读取当前用户可管理的共享 Skill。"""
    candidate = await get_skill_or_raise(db, slug)
    if candidate.bound_agent_id is not None:
        from sqlalchemy import select

        from yuxi.modules.agents.models.definitions import Agent
        from yuxi.modules.identity.repositories.users import UserRepository

        await db.scalar(select(Agent).where(Agent.id == candidate.bound_agent_id).with_for_update(read=True))
        user = await UserRepository(db).lock_active_human(user.uid)
        if user is None:
            raise ValueError(f"技能 '{slug}' 不存在或无权管理")
    item = await get_skill_or_raise(db, slug, for_update=for_update)
    if not user_can_manage_skill(user, item):
        raise ValueError(f"技能 '{slug}' 不存在或无权管理")
    return item


def resolved_shared_skill(item: Skill) -> ResolvedSkill:
    """将数据库 Skill 适配为统一的有效 Skill 描述。"""
    source_scope = "agent_bound" if item.bound_agent_id is not None else ("builtin" if is_builtin_skill(item) else "shared")
    try:
        share_config = {} if item.bound_agent_id is not None else normalize_permission_config(item.share_config)
    except (TypeError, ValueError) as exc:
        # 可见性仍由 repository/resolver 校验；保留坏配置供管理者修复。
        share_config = item.share_config
        logger.warning("Invalid skill share config exposed for repair: slug={}, error={}", item.slug, str(exc))
    return ResolvedSkill(
        id=item.id,
        slug=item.slug,
        name=item.name,
        description=item.description,
        source_type=item.source_type,
        source_scope=source_scope,
        bound_agent_id=item.bound_agent_id,
        bound_agent=item.bound_agent if item.bound_agent_id is not None else None,
        source_dir=_resolve_skill_dir(item),
        enabled=bool(item.enabled),
        created_by=item.created_by,
        share_config=share_config,
        tool_dependencies=normalize_string_list(item.tool_dependencies),
        mcp_dependencies=normalize_string_list(item.mcp_dependencies),
        skill_dependencies=normalize_string_list(item.skill_dependencies),
        version=item.version,
        content_hash=item.content_hash,
    )


def can_skill_depend_on(parent: Skill, dependency: Skill) -> bool:
    """检查两个共享 Skill 的依赖授权是否兼容。"""
    if not dependency.enabled or dependency.bound_agent_id is not None:
        return False
    if is_builtin_skill(dependency):
        return True

    dep_config = normalize_permission_config(dependency.share_config)
    if parent.bound_agent_id is not None:
        agent = parent.bound_agent
        if agent is None:
            return False
        parent_config = normalize_permission_config(
            {
                "version": 2,
                "read_scope": {"access_level": "user", "user_uids": [agent.created_by]},
                "manage_scope": None,
            }
            if agent.visibility == "private"
            else agent.share_config
        )
    else:
        parent_config = normalize_permission_config(parent.share_config)
    dependency_scopes = [scope for scope in (dep_config["read_scope"], dep_config["manage_scope"]) if scope]
    parent_scopes = [scope for scope in (parent_config["read_scope"], parent_config["manage_scope"]) if scope]
    if parent.bound_agent_id is not None and parent.bound_agent.visibility != "private":
        parent_scopes.append({"access_level": "user", "department_ids": [], "user_uids": [parent.bound_agent.created_by]})
    owner_scope = {"access_level": "user", "department_ids": [], "user_uids": []}
    if not dependency_scopes:
        dependency_scopes = [{**owner_scope, "user_uids": [str(dependency.created_by or "")]}]
    if not parent_scopes:
        parent_scopes = [{**owner_scope, "user_uids": [str(parent.created_by or "")]}]
    return all(
        any(_scope_contains(dependency_scope, parent_scope) for dependency_scope in dependency_scopes) for parent_scope in parent_scopes
    )


def normalize_skill_share_config(
    share_config: dict | None,
    *,
    operator_uid: str,
    source_type: str = "upload",
    allowed_access_levels: set[str] | None = None,
) -> dict:
    """校验并标准化共享 Skill 的授权配置。"""
    if source_type == "builtin":
        return {"version": 2, "read_scope": BUILTIN_SKILL_SHARE_CONFIG.copy(), "manage_scope": None}

    default_scope = {
        "access_level": "user",
        "department_ids": [],
        "user_uids": [operator_uid],
    }
    return normalize_permission_config(
        share_config or {"version": 2, "read_scope": default_scope, "manage_scope": None},
        allowed_access_levels=allowed_access_levels,
        unauthorized_access_level_message="当前用户无权使用该 Skill 共享范围",
        strict=True,
    )


def reject_bound_skill_policy_change(item: Skill) -> None:
    """绑定资产的授权、启停与生命周期只能由 Agent 管理。"""
    if item.bound_agent_id is not None:
        raise ValueError("专属 Skill 的权限和生命周期跟随智能体")


def get_allowed_skill_access_levels(user: User) -> list[str]:
    """返回操作人可设定的共享范围。"""
    if user.role in ADMIN_ROLES:
        return ["global", "department", "user"]
    return ["user"]


def user_can_access_skill(user: User, skill: Skill) -> bool:
    """检查用户是否可使用已启用的共享 Skill。"""
    if not skill.enabled:
        return False
    return resolve_skill_permission(user, skill) != ResourcePermission.NONE


def user_can_manage_skill(user: User, skill: Skill) -> bool:
    """检查用户是否可管理共享 Skill。"""
    return resolve_skill_permission(user, skill) == ResourcePermission.MANAGE


def is_builtin_skill(item: Skill | ResolvedSkill) -> bool:
    """判断共享 Skill 是否为内置来源。"""
    return item.source_type == "builtin"


def get_skills_root_dir() -> Path:
    """返回共享与内置 Skill 的持久源目录。"""
    root = get_skill_data_dir() / "shared"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _scope_contains(container: dict, target: dict) -> bool:
    """判断一个共享范围是否完整覆盖另一个范围。"""

    container_level = container.get("access_level")
    target_level = target.get("access_level")
    if container_level == "global":
        return True
    if target_level == "global" or container_level != target_level:
        return False
    if target_level == "department":
        container_ids = {int(value) for value in container.get("department_ids") or []}
        target_ids = {int(value) for value in target.get("department_ids") or []}
        return target_ids.issubset(container_ids)
    if target_level == "user":
        container_uids = {str(value) for value in container.get("user_uids") or []}
        target_uids = {str(value) for value in target.get("user_uids") or []}
        return target_uids.issubset(container_uids)
    return False


def _resolve_skill_dir(item: Skill) -> Path:
    """将共享 Skill 数据库路径解析到持久根下。"""
    return get_skill_data_dir().joinpath(*validated_shared_skill_parts(item.slug, item.dir_path))
