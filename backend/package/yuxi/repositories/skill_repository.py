from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.storage.postgres.models_business import Skill
from yuxi.utils.datetime_utils import utc_now_naive


class SkillRepository:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def list_all(self) -> list[Skill]:
        result = await self.db.execute(select(Skill).order_by(Skill.updated_at.desc(), Skill.id.desc()))
        return list(result.scalars().all())

    async def get_by_slug(self, slug: str) -> Skill | None:
        result = await self.db.execute(select(Skill).where(Skill.slug == slug))
        return result.scalar_one_or_none()

    async def exists_slug(self, slug: str) -> bool:
        return (await self.get_by_slug(slug)) is not None

    async def create(
        self,
        *,
        slug: str,
        name: str,
        description: str,
        tool_dependencies: list[str] | None,
        mcp_dependencies: list[str] | None,
        skill_dependencies: list[str] | None,
        dir_path: str,
        version: str | None = None,
        is_builtin: bool = False,
        content_hash: str | None = None,
        created_by: str | None,
    ) -> Skill:
        now = utc_now_naive()
        item = Skill(
            slug=slug,
            name=name,
            description=description,
            tool_dependencies=tool_dependencies or [],
            mcp_dependencies=mcp_dependencies or [],
            skill_dependencies=skill_dependencies or [],
            dir_path=dir_path,
            version=version,
            is_builtin=is_builtin,
            content_hash=content_hash,
            created_by=created_by,
            updated_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def update_builtin_install(
        self,
        item: Skill,
        *,
        version: str,
        content_hash: str,
        updated_by: str | None,
    ) -> Skill:
        item.version = version
        item.content_hash = content_hash
        item.is_builtin = True
        item.updated_by = updated_by
        item.updated_at = utc_now_naive()
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def update_dependencies(
        self,
        item: Skill,
        *,
        tool_dependencies: list[str],
        mcp_dependencies: list[str],
        skill_dependencies: list[str],
        updated_by: str | None,
    ) -> Skill:
        item.tool_dependencies = tool_dependencies
        item.mcp_dependencies = mcp_dependencies
        item.skill_dependencies = skill_dependencies
        item.updated_by = updated_by
        item.updated_at = utc_now_naive()
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def update_metadata(
        self,
        item: Skill,
        *,
        name: str,
        description: str,
        updated_by: str | None,
    ) -> Skill:
        item.name = name
        item.description = description
        item.updated_by = updated_by
        item.updated_at = utc_now_naive()
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def delete(self, item: Skill) -> None:
        await self.db.delete(item)
        await self.db.commit()
