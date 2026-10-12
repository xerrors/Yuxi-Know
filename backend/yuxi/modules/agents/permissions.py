"""Agent 可见、管理与运行的权限谓词。"""

from yuxi.modules.agents.models.definitions import Agent
from yuxi.modules.agents.presets.default_chatbot import PRESET
from yuxi.modules.identity.models import User
from yuxi.modules.identity.permissions import ResourcePermission, resolve_agent_permission

DEFAULT_AGENT_SLUG = PRESET.slug


def is_builtin_agent(agent: Agent) -> bool:
    """识别内置助手与显式内置定义。"""
    return bool(getattr(agent, "is_builtin", False)) or agent.slug == DEFAULT_AGENT_SLUG


def user_can_access_agent(user: User, agent: Agent) -> bool:
    """按当前资源权限判断定义可见性。"""
    return resolve_agent_permission(user, agent) != ResourcePermission.NONE


def user_can_manage_agent(user: User, agent: Agent) -> bool:
    """内置定义仅超级管理员可管理，其余遵循共享权限。"""
    if is_builtin_agent(agent):
        return user.role == "superadmin"
    return resolve_agent_permission(user, agent) == ResourcePermission.MANAGE


def user_can_run_agent(user: User, agent: Agent) -> bool:
    """私有治理权限不赋予冒用所有者运行的能力。"""
    if agent.visibility == "private":
        return not user.is_deleted and user.user_kind != "end_user" and user.uid == agent.created_by
    return user_can_access_agent(user, agent)
