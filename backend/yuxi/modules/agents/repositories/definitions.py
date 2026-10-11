from __future__ import annotations

import copy
import re
import uuid
from collections.abc import Collection
from types import SimpleNamespace
from typing import Any, Literal

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.infrastructure.observability.logging import logger
from yuxi.modules.agents.models.definitions import Agent
from yuxi.modules.agents.models.inputs import AgentInput
from yuxi.modules.agents.models.runs import AGENT_RUN_TERMINAL_STATUSES, AgentRun
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.agents.models.turns import AgentTurn
from yuxi.modules.agents.presets import AgentPreset
from yuxi.modules.agents.presets.default_chatbot import PRESET as DEFAULT_AGENT
from yuxi.modules.agents.runtime.context import BaseContext, validate_resource_selection
from yuxi.modules.identity.models import User
from yuxi.modules.identity.permissions import ResourcePermission, normalize_permission_config, resolve_agent_permission
from yuxi.modules.identity.repositories.users import UserRepository
from yuxi.modules.identity.services.resource_grants import validate_shared_grants
from yuxi.shared.datetime import utc_now

DEFAULT_AGENT_SLUG = DEFAULT_AGENT.slug
DEFAULT_AGENT_NAME = DEFAULT_AGENT.name
DEFAULT_AGENT_BACKEND_ID = DEFAULT_AGENT.backend_id
DEFAULT_AGENT_DESCRIPTION = DEFAULT_AGENT.description
DEFAULT_SHARE_CONFIG = {
    "version": 2,
    "read_scope": {"access_level": "global", "department_ids": [], "user_uids": []},
    "manage_scope": None,
}

ADMIN_ROLES = {"admin", "superadmin"}


def is_builtin_agent(agent: Agent) -> bool:
    return bool(getattr(agent, "is_builtin", False)) or agent.slug == DEFAULT_AGENT_SLUG


def user_can_access_agent(user: User, agent: Agent) -> bool:
    return resolve_agent_permission(user, agent) != ResourcePermission.NONE


def user_can_manage_agent(user: User, agent: Agent) -> bool:
    if is_builtin_agent(agent):
        return user.role == "superadmin"
    return resolve_agent_permission(user, agent) == ResourcePermission.MANAGE


def user_can_run_agent(user: User, agent: Agent) -> bool:
    """私有治理权限不赋予冒用所有者运行的能力。"""
    if agent.visibility == "private":
        return not user.is_deleted and user.user_kind != "end_user" and user.uid == agent.created_by
    return user_can_access_agent(user, agent)


def _slugify(value: str | None) -> str:
    base = re.sub(r"[^a-zA-Z0-9_-]+", "-", (value or "").strip().lower()).strip("-")
    return base[:56] or f"agent-{uuid.uuid4().hex[:12]}"


class AgentRepository:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def ensure_default_agent(self, *, created_by: str | None = None) -> Agent:
        agent = await self.get_by_slug(DEFAULT_AGENT_SLUG)
        if agent:
            needs_update = False
            if agent.share_config != DEFAULT_SHARE_CONFIG:
                agent.share_config = DEFAULT_SHARE_CONFIG.copy()
                needs_update = True
            if not agent.description:
                agent.description = DEFAULT_AGENT_DESCRIPTION
                needs_update = True
            if not agent.is_default:
                return await self.set_default(agent=agent, updated_by=created_by)
            if needs_update:
                agent.updated_by = created_by
                agent.updated_at = utc_now()
                await self.db.commit()
                await self.db.refresh(agent)
            return agent

        agent = Agent(
            slug=DEFAULT_AGENT_SLUG,
            backend_id=DEFAULT_AGENT_BACKEND_ID,
            name=DEFAULT_AGENT_NAME,
            description=DEFAULT_AGENT_DESCRIPTION,
            icon=None,
            pics=[],
            config_json={"context": copy.deepcopy(DEFAULT_AGENT.context)},
            share_config=DEFAULT_SHARE_CONFIG.copy(),
            visibility="shared",
            is_builtin=True,
            is_default=True,
            created_by=created_by,
            updated_by=created_by,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def ensure_preset(self, preset: AgentPreset, *, created_by: str | None = None) -> Agent:
        """首次落库预置角色，保留已存在的用户配置。"""
        if preset.slug == DEFAULT_AGENT_SLUG:
            return await self.ensure_default_agent(created_by=created_by)
        agent = await self.get_by_slug(preset.slug)
        if agent:
            return agent

        agent = Agent(
            slug=preset.slug,
            backend_id=preset.backend_id,
            name=preset.name,
            description=preset.description,
            icon=None,
            pics=[],
            config_json={"context": copy.deepcopy(preset.context)},
            share_config=DEFAULT_SHARE_CONFIG.copy(),
            visibility="shared",
            is_builtin=True,
            is_default=False,
            created_by=created_by,
            updated_by=created_by,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def list_visible(self, *, user: User) -> list[Agent]:
        """列出当前用户可见的智能体配置。"""
        visibility_user = await self._visibility_user(user)
        if visibility_user is None:
            return []
        stmt = select(Agent)
        result = await self.db.execute(stmt.order_by(Agent.is_default.desc(), Agent.id.asc()))
        agents = list(result.scalars().all())
        if visibility_user.role == "superadmin":
            return agents
        return [
            agent
            for agent in agents
            if (getattr(user, "user_kind", "human") != "end_user" or agent.visibility == "shared")
            and user_can_access_agent(visibility_user, agent)
        ]

    async def get_by_slug(self, slug: str, *, for_key_share: bool = False) -> Agent | None:
        """读取 Agent，创建 Thread 时可持有共享键锁直到提交。"""
        statement = select(Agent).where(Agent.slug == slug)
        if for_key_share:
            statement = statement.with_for_update(read=True, key_share=True).execution_options(populate_existing=True)
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def list_by_slugs(self, slugs: list[str]) -> list[Agent]:
        result = await self.db.execute(select(Agent).where(Agent.slug.in_(slugs)))
        return list(result.scalars().all())

    async def get_visible_by_slug(
        self,
        *,
        slug: str,
        user: User,
        for_key_share: bool = False,
        for_run: bool = True,
    ) -> Agent | None:
        """按 slug 读取并校验当前调用者的智能体权限。"""
        visibility_user = await self._visibility_user(user)
        if visibility_user is None:
            return None
        agent = await self.get_by_slug(slug, for_key_share=for_key_share)
        if not agent:
            return None
        if getattr(user, "user_kind", "human") == "end_user" and agent.visibility != "shared":
            return None
        if for_run and agent.visibility == "private" and not user_can_run_agent(user, agent):
            return None
        if not user_can_access_agent(visibility_user, agent):
            return None
        return agent

    async def _visibility_user(self, user: User) -> User | None:
        """终端用户只借用 Key 用户的 Agent 可见性，执行 UID 保持不变。"""
        if getattr(user, "user_kind", "human") != "end_user":
            return user
        owner = await self.db.scalar(
            select(User).where(
                User.id == user.owner_user_id,
                User.user_kind == "human",
                User.is_deleted == 0,
            )
        )
        if owner is None or user.is_deleted:
            return None
        return SimpleNamespace(uid=owner.uid, department_id=owner.department_id, role="user", is_deleted=0)

    async def set_default(self, *, agent: Agent, updated_by: str | None = None) -> Agent:
        if agent.visibility != "shared":
            raise ValueError("默认 Agent 必须为共享状态")
        if not is_builtin_agent(agent):
            raise ValueError("默认智能体已固定为内置智能助手")
        share_config = agent.share_config or DEFAULT_SHARE_CONFIG.copy()
        read_scope = share_config.get("read_scope") or {}
        if read_scope.get("access_level") != "global":
            raise ValueError("内置智能体必须全局共享")

        now = utc_now()
        await self.db.execute(update(Agent).where(Agent.is_default.is_(True)).values(is_default=False, updated_at=now))
        agent.is_default = True
        agent.updated_by = updated_by
        agent.updated_at = now
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def _slug_exists(self, slug: str) -> bool:
        result = await self.db.execute(select(Agent.id).where(Agent.slug == slug))
        return result.scalar_one_or_none() is not None

    async def _unique_slug(self, desired: str | None, name: str) -> str:
        base = _slugify(desired or name)
        candidate = base
        idx = 2
        while await self._slug_exists(candidate):
            suffix = f"-{idx}"
            candidate = f"{base[: 80 - len(suffix)]}{suffix}"
            idx += 1
        return candidate

    async def create(
        self,
        *,
        name: str,
        backend_id: str,
        slug: str | None = None,
        description: str | None = None,
        icon: str | None = None,
        pics: list[str] | None = None,
        config_json: dict | None = None,
        config_resource_access: dict[str, Collection[str]] | None = None,
        share_config: dict | None = None,
        is_default: bool = False,
        created_by: str | None = None,
        creator: User | None = None,
        visibility: Literal["private", "shared"] = "private",
        commit: bool = True,
    ) -> Agent:
        """校验定义并写入；联合创建由用例持有最终事务。"""
        if creator is None or creator.is_deleted or creator.user_kind == "end_user":
            raise ValueError("必须由有效产品用户创建智能体")
        if str(created_by) != str(creator.uid):
            raise ValueError("不能指定其他所有者")
        if visibility == "shared" and creator.role not in ADMIN_ROLES:
            raise ValueError("普通用户不能创建共享智能体")
        if visibility == "private" and share_config is not None:
            raise ValueError("私有智能体不接受共享授权")
        normalized_share_config = (
            await validate_shared_grants(self.db, share_config or DEFAULT_SHARE_CONFIG)
            if visibility == "shared"
            else {"version": 2, "read_scope": None, "manage_scope": None}
        )

        from yuxi.modules.agents.runtime.agent_backends import get_agent_backend

        agent = Agent(
            slug=await self._unique_slug(slug, name),
            backend_id=backend_id,
            name=name.strip() or "未命名智能体",
            description=description,
            icon=icon,
            pics=pics or [],
            config_json=merge_agent_config_json(
                {"context": {}},
                config_json or {},
                resource_access=config_resource_access or {},
                context_schema=get_agent_backend(backend_id).context_schema,
            ),
            share_config=normalized_share_config,
            visibility=visibility,
            is_builtin=False,
            is_default=False,
            created_by=created_by,
            updated_by=created_by,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.db.add(agent)
        if commit:
            await self.db.commit()
            await self.db.refresh(agent)
        else:
            await self.db.flush()
        if is_default:
            return await self.set_default(agent=agent, updated_by=created_by)
        return agent

    async def update(
        self,
        agent: Agent,
        *,
        name: str | None = None,
        description: str | None = None,
        icon: str | None = None,
        pics: list[str] | None = None,
        config_json: dict | None = None,
        share_config: dict | None = None,
        visibility: Literal["shared"] | None = None,
        updated_by: str | None = None,
        updater: User | None = None,
        fields_set: set[str] | None = None,
        commit: bool = True,
    ) -> Agent:
        current = await self.db.scalar(
            select(Agent).where(Agent.id == agent.id).with_for_update().execution_options(populate_existing=True)
        )
        if current is None:
            raise ValueError("智能体不存在")
        agent = current
        updater = await UserRepository(self.db).lock_active_human(updater.uid) if updater is not None else None
        if updater is None or not user_can_manage_agent(updater, agent):
            raise PermissionError("无权管理该智能体")
        from yuxi.modules.agents.runtime.agent_backends import get_agent_backend

        backend = get_agent_backend(agent.backend_id)
        sharing_private_agent = agent.visibility == "private" and visibility == "shared"
        if sharing_private_agent:
            if updater.role not in ADMIN_ROLES:
                raise PermissionError("仅管理员可共享智能体")
            if share_config is None:
                raise ValueError("共享智能体必须指定共享权限")
        config_resource_access = {}
        if config_json is not None:
            from yuxi.modules.agents.services.configuration import prepare_agent_config_write

            config_json, config_resource_access = await prepare_agent_config_write(
                config_json,
                context_schema=backend.context_schema,
                db=self.db,
                user=updater,
            )
        if share_config is not None and agent.visibility == "private" and not sharing_private_agent:
            raise ValueError("私有智能体不接受共享授权")
        if share_config is not None and is_builtin_agent(agent):
            raise ValueError("内置定义不接受共享配置写入")
        if name is not None:
            agent.name = name.strip() or "未命名智能体"
        if description is not None or "description" in (fields_set or set()):
            agent.description = description
        if icon is not None or "icon" in (fields_set or set()):
            agent.icon = icon
        if pics is not None:
            agent.pics = pics
        if config_json is not None:
            result = await self.db.execute(select(Agent.config_json).where(Agent.id == agent.id).with_for_update())
            row = result.one_or_none()
            if row is None:
                raise ValueError("智能体不存在")
            agent.config_json = merge_agent_config_json(
                row[0],
                config_json,
                resource_access=config_resource_access or {},
                context_schema=get_agent_backend(agent.backend_id).context_schema,
            )
        if share_config is not None:
            agent.share_config = await validate_shared_grants(self.db, share_config)
        if sharing_private_agent:
            agent.visibility = "shared"

        agent.updated_by = updated_by
        agent.updated_at = utc_now()
        if commit:
            await self.db.commit()
            await self.db.refresh(agent)
        else:
            await self.db.flush()
        return agent

    async def delete(self, *, agent: Agent, user: User, commit: bool = True) -> None:
        """锁定 Agent 与已有 Thread，拒绝仍由该 Agent 拥有的工作。"""
        current = await self.db.scalar(
            select(Agent).where(Agent.id == agent.id).with_for_update().execution_options(populate_existing=True)
        )
        if current is None:
            raise LookupError("智能体不存在")
        user = await UserRepository(self.db).lock_active_human(user.uid)
        if user is None or not user_can_manage_agent(user, current):
            raise PermissionError("不能删除非自己创建的智能体")
        if is_builtin_agent(current):
            raise ValueError("内置智能体不能删除")

        # Thread 是接收与调度的先行锁；按共同顺序锁定，随后读取持久工作事实。
        result = await self.db.execute(
            select(Session.thread_id).where(Session.agent_id == current.slug).order_by(Session.thread_id).with_for_update(key_share=True)
        )
        thread_ids = list(result.scalars())
        active_turn = await self.db.scalar(
            select(AgentTurn.id)
            .where(
                AgentTurn.thread_id.in_(thread_ids),
                AgentTurn.status.in_(("running", "waiting", "cancelling")),
            )
            .limit(1)
        )
        pending_input = await self.db.scalar(
            select(AgentInput.id)
            .where(
                or_(AgentInput.agent_slug == current.slug, AgentInput.thread_id.in_(thread_ids)),
                AgentInput.status == "pending",
            )
            .limit(1)
        )
        active_run = await self.db.scalar(
            select(AgentRun.id)
            .where(
                or_(AgentRun.agent_slug == current.slug, AgentRun.runtime_scope_id.in_(thread_ids)),
                or_(
                    AgentRun.status.notin_(AGENT_RUN_TERMINAL_STATUSES),
                    AgentRun.runtime_cleanup_pending.is_(True),
                ),
            )
            .limit(1)
        )
        if active_turn or pending_input or active_run:
            raise ValueError("智能体仍有活跃执行或待处理输入")

        await self.db.delete(current)
        if commit:
            await self.db.commit()
        else:
            await self.db.flush()

    async def serialize(
        self,
        agent: Agent,
        *,
        user: User,
        include_configurable_items: bool = False,
        backend_info_cache: dict[tuple[str, bool, str], dict] | None = None,
    ) -> dict[str, Any]:
        data = agent.to_dict()
        data["share_config_invalid"] = False
        try:
            data["share_config"] = normalize_permission_config(agent.share_config)
        except (TypeError, ValueError) as exc:
            if user.role != "superadmin":
                raise
            # 管理者需要读取原始坏配置进行修复，不将它解释为有效共享范围。
            data["share_config"] = agent.share_config
            data["share_config_invalid"] = True
            logger.warning("Invalid agent share config exposed for repair: slug={}, error={}", agent.slug, str(exc))
        permission = resolve_agent_permission(user, agent)
        is_builtin = is_builtin_agent(agent)
        data["can_manage"] = user_can_manage_agent(user, agent)
        data["can_run"] = user_can_run_agent(user, agent)
        data["can_share"] = data["can_manage"] and not is_builtin and (agent.visibility == "shared" or user.role in ADMIN_ROLES)
        data["can_transfer"] = agent.visibility == "shared" and user.role == "superadmin" and not is_builtin
        data["effective_permission"] = permission.value
        data["is_builtin"] = is_builtin
        data["permission_locked"] = is_builtin

        from yuxi.modules.agents.runtime.agent_backends import get_agent_backend

        backend = get_agent_backend(agent.backend_id)
        cache_key = (agent.backend_id, include_configurable_items, user.role)
        backend_info = backend_info_cache.get(cache_key) if backend_info_cache is not None else None
        if backend_info is None:
            backend_info = await backend.get_info(
                include_configurable_items=include_configurable_items,
                user_role=user.role,
                db=self.db if include_configurable_items else None,
                user=user if include_configurable_items else None,
            )
            if backend_info_cache is not None:
                backend_info_cache[cache_key] = backend_info
        data["metadata"] = backend_info.get("metadata", {})
        if include_configurable_items:
            data["configurable_items"] = backend_info.get("configurable_items", {})
        return data


def merge_agent_config_json(
    existing: dict | None,
    patch: dict,
    *,
    resource_access: dict[str, Collection[str]],
    context_schema: type[BaseContext] = BaseContext,
) -> dict:
    """合并 Agent 配置补丁，并在资源字段上保留旧的不可见引用。"""
    if not isinstance(patch, dict):
        raise ValueError("智能体配置必须是对象")

    current = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    patch_copy = copy.deepcopy(patch)
    merged = {**current, **patch_copy}
    if "context" not in patch:
        return merged

    patch_context = patch_copy["context"]
    if not isinstance(patch_context, dict):
        raise ValueError("智能体 context 配置必须是对象")

    current_context = current.get("context")
    if not isinstance(current_context, dict):
        current_context = {}
    merged_context = {**current_context, **patch_context}

    for field_name in context_schema.get_resource_fields().keys() & patch_context.keys():
        requested = validate_resource_selection(field_name, patch_context[field_name])
        if requested == "all" or not requested:
            merged_context[field_name] = requested
            continue

        if field_name not in resource_access:
            raise ValueError(f"智能体资源字段 {field_name} 未经过权限校验")
        accessible = {str(item) for item in resource_access[field_name]}
        previous = current_context.get(field_name, [])
        if previous == "all":
            previous = []
        previous = validate_resource_selection(field_name, previous)
        previous_set = set(previous)
        unauthorized_new = [item for item in requested if item not in accessible and item not in previous_set]
        if unauthorized_new:
            raise ValueError(f"无权新增智能体资源 {field_name}: {', '.join(unauthorized_new)}")

        requested_set = set(requested)
        kept_existing = [item for item in previous if item not in accessible or item in requested_set]
        new_visible = [item for item in requested if item in accessible and item not in previous_set]
        merged_context[field_name] = [*kept_existing, *new_visible]

    merged["context"] = merged_context
    return merged
