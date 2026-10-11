"""统一解析 Agent、Skill 与知识库的共享权限。"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from yuxi.infrastructure.observability.logging import logger


class ResourcePermission(StrEnum):
    """资源权限等级，数值顺序用于判断权限是否足够。"""

    NONE = "none"
    READ = "read"
    MANAGE = "manage"


class ResourcePermissionDenied(PermissionError):
    """当前用户的资源权限不足。"""


class ShareableResource(Protocol):
    """声明可通过共享配置进行权限解析的资源字段。"""

    created_by: str | None
    share_config: dict | None


@dataclass(frozen=True)
class ResourcePermissionPolicy:
    """声明资源类型允许的角色上限，不包含共享范围匹配逻辑。"""

    role_ceiling: dict[str, ResourcePermission]


RESOURCE_PERMISSION_ORDER = {
    ResourcePermission.NONE: 0,
    ResourcePermission.READ: 1,
    ResourcePermission.MANAGE: 2,
}

DEFAULT_SCOPE = {"access_level": "global", "department_ids": [], "user_uids": []}
KNOWLEDGE_BASE_PERMISSION_POLICY = ResourcePermissionPolicy(
    role_ceiling={
        "user": ResourcePermission.READ,
        "admin": ResourcePermission.MANAGE,
        "superadmin": ResourcePermission.MANAGE,
    }
)
AGENT_PERMISSION_POLICY = ResourcePermissionPolicy(
    role_ceiling={
        "user": ResourcePermission.READ,
        "admin": ResourcePermission.MANAGE,
        "superadmin": ResourcePermission.MANAGE,
    }
)
SKILL_PERMISSION_POLICY = AGENT_PERMISSION_POLICY


def _normalize_scope(scope: dict | None) -> dict | None:
    """规范化共享范围并校验其访问级别与成员列表。"""

    if scope is None:
        return None
    if not isinstance(scope, dict):
        raise ValueError("权限范围必须是对象")

    access_level = scope.get("access_level")
    if access_level is not None and not isinstance(access_level, str):
        raise ValueError("资源权限访问级别必须是字符串")
    access_level = access_level or "global"
    if access_level not in {"global", "department", "user"}:
        raise ValueError("无效的资源权限范围")

    if access_level == "global":
        return DEFAULT_SCOPE.copy()
    if access_level == "department":
        members = scope.get("department_ids")
        if not isinstance(members, list) or any(type(value) not in (int, str) for value in members):
            raise ValueError("部门权限成员必须是整数或整数字符串组成的列表")
        department_ids = sorted({int(value) for value in members})
        if not department_ids:
            raise ValueError("部门权限至少需要选择一个部门")
        return {"access_level": access_level, "department_ids": department_ids, "user_uids": []}

    members = scope.get("user_uids")
    if not isinstance(members, list) or any(not isinstance(value, str) for value in members):
        raise ValueError("用户权限成员必须是字符串列表")
    user_uids = sorted({value.strip() for value in members if value.strip()})
    if not user_uids:
        raise ValueError("指定用户权限至少需要选择一个用户")
    return {"access_level": access_level, "department_ids": [], "user_uids": user_uids}


def _validate_manage_scope(read_scope: dict | None, manage_scope: dict | None) -> None:
    """确保管理范围不会超出读取范围。"""

    if not manage_scope:
        return
    if not read_scope:
        raise ValueError("管理范围必须包含在读取范围内")
    if read_scope["access_level"] == "global":
        return

    read_level = read_scope["access_level"]
    manage_level = manage_scope["access_level"]
    if manage_level != read_level:
        raise ValueError("管理范围必须包含在读取范围内")
    if read_level == manage_level == "department":
        if not set(manage_scope["department_ids"]).issubset(read_scope["department_ids"]):
            raise ValueError("管理范围必须包含在读取范围内")
    elif read_level == manage_level == "user":
        if not set(manage_scope["user_uids"]).issubset(read_scope["user_uids"]):
            raise ValueError("管理范围必须包含在读取范围内")


def normalize_permission_config(
    share_config: dict | None,
    *,
    allowed_access_levels: Collection[str] | None = None,
    unauthorized_access_level_message: str = "当前用户无权使用该资源共享范围",
    strict: bool = False,
) -> dict:
    """规范化并校验 v2 共享配置。"""

    config = share_config if isinstance(share_config, dict) else {}
    if config.get("version") == 2:
        read_scope = _normalize_scope(config.get("read_scope"))
        manage_scope = _normalize_scope(config.get("manage_scope"))
        try:
            _validate_manage_scope(read_scope, manage_scope)
        except ValueError:
            if strict:
                raise
            # 读取历史配置时保持原值；保存时由 strict 校验拒绝越界配置。
        normalized = {
            "version": 2,
            "read_scope": read_scope,
            "manage_scope": manage_scope,
        }
        if allowed_access_levels is not None:
            for scope in (normalized["read_scope"], normalized["manage_scope"]):
                if scope and scope["access_level"] not in allowed_access_levels:
                    raise ValueError(unauthorized_access_level_message)
        return normalized
    raise ValueError("资源共享配置必须使用 version 2")


def scope_matches(user: Any, scope: dict | None) -> bool:
    """判断用户是否命中一个共享范围。"""

    if not scope:
        return False
    access_level = scope.get("access_level")
    if access_level == "global":
        return True
    if access_level == "department":
        department_id = _value(user, "department_id")
        try:
            return department_id is not None and int(department_id) in scope.get("department_ids", [])
        except (TypeError, ValueError):
            return False
    if access_level == "user":
        return str(_value(user, "uid", "") or "") in scope.get("user_uids", [])
    return False


def _value(source: Any, key: str, default: Any = None) -> Any:
    """从字典或对象读取属性，统一权限解析的输入访问方式。"""

    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _minimum_permission(left: ResourcePermission, right: ResourcePermission) -> ResourcePermission:
    """按权限等级顺序返回两者中更低的权限。"""

    return left if RESOURCE_PERMISSION_ORDER[left] <= RESOURCE_PERMISSION_ORDER[right] else right


def resolve_resource_permission(
    user: Any,
    resource: ShareableResource,
    policy: ResourcePermissionPolicy,
) -> ResourcePermission:
    """解析资源所有权、共享范围和角色上限后的有效权限。"""

    if _value(user, "is_deleted", 0):
        return ResourcePermission.NONE
    if _value(user, "role") == "superadmin":
        return ResourcePermission.MANAGE

    raw_share_config = _value(resource, "share_config")
    try:
        config = normalize_permission_config(raw_share_config)
    except (TypeError, ValueError) as exc:
        logger.warning(
            "Invalid resource share config; denying access: resource_type={}, resource_id={}, user_uid={}, error={}",
            type(resource).__name__,
            _value(resource, "id", _value(resource, "slug", "unknown")),
            _value(user, "uid", "unknown"),
            str(exc),
        )
        return ResourcePermission.NONE
    if (
        _value(user, "role") == "admin"
        and _value(user, "uid")
        and (str(_value(resource, "created_by", "") or "") == str(_value(user, "uid")))
    ):
        return ResourcePermission.MANAGE
    if scope_matches(user, config["manage_scope"]) and scope_matches(user, config["read_scope"]):
        granted = ResourcePermission.MANAGE
    elif scope_matches(user, config["read_scope"]):
        granted = ResourcePermission.READ
    else:
        granted = ResourcePermission.NONE

    ceiling = policy.role_ceiling.get(_value(user, "role"), ResourcePermission.READ)
    return _minimum_permission(granted, ceiling)


def require_resource_permission(
    actual: ResourcePermission,
    required: ResourcePermission,
) -> None:
    """在权限不足时显式失败。"""

    if RESOURCE_PERMISSION_ORDER[actual] < RESOURCE_PERMISSION_ORDER[required]:
        raise ResourcePermissionDenied(f"需要 {required.value} 权限，当前为 {actual.value}")


def resolve_knowledge_base_permission(user: Any, resource: ShareableResource) -> ResourcePermission:
    """解析知识库权限，普通用户最多只能获得只读权限。"""

    return resolve_resource_permission(
        user,
        resource,
        KNOWLEDGE_BASE_PERMISSION_POLICY,
    )


def require_knowledge_base_permission(
    user: Any,
    resource: ShareableResource,
    required: ResourcePermission,
) -> ResourcePermission:
    """校验用户是否具备知识库所需权限，并返回实际权限。"""

    actual = resolve_knowledge_base_permission(user, resource)
    require_resource_permission(actual, required)
    return actual


def resolve_agent_permission(user: Any, resource: ShareableResource) -> ResourcePermission:
    """私有定义只供所有者管理，系统管理员拥有治理权限。"""
    if _value(user, "is_deleted", 0):
        return ResourcePermission.NONE
    if _value(resource, "visibility") == "private":
        if _value(user, "user_kind") == "end_user":
            return ResourcePermission.NONE
        if _value(user, "role") == "superadmin" or (
            _value(user, "uid") and str(_value(user, "uid")) == str(_value(resource, "created_by"))
        ):
            return ResourcePermission.MANAGE
        return ResourcePermission.NONE
    if _value(resource, "is_builtin", False) or _value(resource, "slug") == "default-chatbot":
        permission = resolve_resource_permission(user, resource, AGENT_PERMISSION_POLICY)
        return permission if _value(user, "role") == "superadmin" else _minimum_permission(permission, ResourcePermission.READ)
    return resolve_resource_permission(
        user,
        resource,
        AGENT_PERMISSION_POLICY,
    )


def resolve_skill_permission(user: Any, resource: ShareableResource) -> ResourcePermission:
    """解析 Skill 权限。"""

    if _value(resource, "bound_agent_id") is not None:
        agent = _value(resource, "bound_agent")
        if agent is None:
            return ResourcePermission.NONE
        if _value(user, "user_kind") == "end_user":
            owner = _value(user, "owner_user")
            if _value(user, "is_deleted", 0) or owner is None or _value(owner, "is_deleted", 0):
                return ResourcePermission.NONE
            if _value(agent, "visibility") != "shared":
                return ResourcePermission.NONE
            # 绑定资源复用 APP 的 Agent 可见性，角色上限保持实际终端用户的读取权限。
            user = {"uid": _value(owner, "uid"), "department_id": _value(owner, "department_id"), "role": "user"}
        return resolve_agent_permission(user, agent)

    if _value(resource, "source_scope") == "personal":
        if str(_value(resource, "created_by", "") or "") == str(_value(user, "uid", "") or ""):
            return ResourcePermission.MANAGE
        return ResourcePermission.NONE

    permission = resolve_resource_permission(
        user,
        resource,
        SKILL_PERMISSION_POLICY,
    )
    if _value(resource, "source_type") == "builtin" and _value(user, "role") != "superadmin":
        return _minimum_permission(permission, ResourcePermission.READ)
    return permission
