"""SubAgent 数据访问层"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.storage.postgres.models_business import SubAgent
from yuxi.utils.datetime_utils import utc_now_naive


class SubAgentRepository:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def list_all(self) -> list[SubAgent]:
        """获取所有 SubAgent，按 updated_at 降序"""
        result = await self.db.execute(select(SubAgent).order_by(SubAgent.updated_at.desc()))
        return list(result.scalars().all())

    async def get_by_name(self, name: str) -> SubAgent | None:
        """根据名称获取 SubAgent"""
        result = await self.db.execute(select(SubAgent).where(SubAgent.name == name))
        return result.scalar_one_or_none()

    async def exists_name(self, name: str) -> bool:
        """检查名称是否存在"""
        return (await self.get_by_name(name)) is not None

    async def create(
        self,
        *,
        name: str,
        description: str,
        system_prompt: str,
        tools: list[str] | None,
        model: str | None,
        is_builtin: bool,
        created_by: str | None,
    ) -> SubAgent:
        now = utc_now_naive()
        item = SubAgent(
            name=name,
            description=description,
            system_prompt=system_prompt,
            tools=tools or [],
            model=model,
            is_builtin=is_builtin,
            created_by=created_by,
            updated_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def update(
        self,
        item: SubAgent,
        *,
        description: str | None,
        system_prompt: str | None,
        tools: list[str] | None,
        model: str | None,
        model_provided: bool = False,
        updated_by: str | None,
    ) -> SubAgent:
        if description is not None:
            item.description = description
        if system_prompt is not None:
            item.system_prompt = system_prompt
        if tools is not None:
            item.tools = tools
        if model_provided:
            item.model = model
        item.updated_by = updated_by
        item.updated_at = utc_now_naive()
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def delete(self, item: SubAgent) -> None:
        """删除 SubAgent"""
        await self.db.delete(item)
        await self.db.commit()

    async def upsert(self, data: dict[str, Any], created_by: str | None) -> SubAgent:
        """Upsert 操作，如果存在则更新，否则创建"""
        name = data["name"]
        existing = await self.get_by_name(name)
        if existing:
            return await self.update(
                existing,
                description=data.get("description", existing.description),
                system_prompt=data.get("system_prompt", existing.system_prompt),
                tools=data.get("tools", existing.tools),
                model=data.get("model", existing.model),
                model_provided="model" in data,
                updated_by=created_by,
            )
        else:
            return await self.create(
                name=name,
                description=data["description"],
                system_prompt=data["system_prompt"],
                tools=data.get("tools"),
                model=data.get("model"),
                is_builtin=data.get("is_builtin", False),
                created_by=created_by,
            )
