"""Public Agent 目录与可见性查询。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.modules.agents.models.definitions import Agent
from yuxi.modules.agents.repositories.definitions import AgentRepository
from yuxi.modules.agents.permissions import user_can_run_agent
from yuxi.modules.identity.models import User
from yuxi.shared.errors import ResourceNotFoundError


async def list_public_agents(*, user: User, db: AsyncSession) -> list[Agent]:
    """列出当前身份可调用的主 Agent。"""
    agents = await AgentRepository(db).list_visible(user=user)
    return [agent for agent in agents if agent.visibility == "shared" or user_can_run_agent(user, agent)]


async def get_public_agent(*, agent_id: str, user: User, db: AsyncSession) -> Agent:
    """按后端可见性读取主 Agent。"""
    agent = await AgentRepository(db).get_visible_by_slug(slug=agent_id, user=user)
    if agent is None:
        raise ResourceNotFoundError("智能体不存在")
    return agent
