"""部门数据访问层 - Repository"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import APIKey, Department, User
from yuxi.utils.datetime_utils import utc_now_naive


@dataclass(frozen=True)
class DepartmentDeletionResult:
    """部门删除结果。"""

    name: str
    migrated_user_count: int


class DepartmentRepository:
    """部门数据访问层"""

    def __init__(self, db_session: AsyncSession | None = None):
        self.db_session = db_session

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        """复用请求会话，未注入时创建独立事务会话。"""
        if self.db_session is not None:
            yield self.db_session
            return
        async with pg_manager.get_async_session_context() as session:
            yield session

    async def get_by_id(self, id: int) -> Department | None:
        """根据 ID 获取部门"""
        async with self._session() as session:
            result = await session.execute(select(Department).where(Department.id == id))
            return result.scalar_one_or_none()

    async def get_name_by_id(self, id: int) -> str | None:
        """根据 ID 获取部门名称。"""
        async with self._session() as session:
            result = await session.execute(select(Department.name).where(Department.id == id))
            return result.scalar_one_or_none()

    async def get_with_user_count(self, id: int) -> dict[str, Any] | None:
        """获取部门及其未删除用户数量。"""
        async with self._session() as session:
            result = await session.execute(select(Department).where(Department.id == id))
            department = result.scalar_one_or_none()
            if department is None:
                return None
            count_result = await session.execute(
                select(func.count(User.id)).where(User.department_id == id, User.is_deleted == 0)
            )
            return {**department.to_dict(), "user_count": count_result.scalar() or 0}

    async def get_by_name(self, name: str) -> Department | None:
        """根据名称获取部门"""
        async with self._session() as session:
            result = await session.execute(select(Department).where(Department.name == name))
            return result.scalar_one_or_none()

    async def list_departments(self) -> list[Department]:
        """获取所有部门列表"""
        async with self._session() as session:
            result = await session.execute(select(Department).order_by(Department.created_at.desc()))
            return list(result.scalars().all())

    async def list_with_user_count(self) -> list[dict[str, Any]]:
        """获取所有部门列表，包含用户数量。

        单次 GROUP BY 聚合替代逐部门 COUNT：单位目录会被智能体共享等弹窗高频拉取，
        N+1 查询随用户表行数线性放大（6k 用户实测 ~200ms）。
        """
        async with self._session() as session:
            result = await session.execute(select(Department).order_by(Department.created_at.desc()))
            departments = list(result.scalars().all())
            counts_result = await session.execute(
                select(User.department_id, func.count(User.id))
                .where(User.is_deleted == 0, User.department_id.is_not(None))
                .group_by(User.department_id)
            )
            user_counts = dict(counts_result.all())
            return [{**dep.to_dict(), "user_count": user_counts.get(dep.id, 0)} for dep in departments]

    async def create(self, data: dict[str, Any]) -> Department:
        """创建部门"""
        async with self._session() as session:
            department = Department(**data)
            session.add(department)
            await session.flush()
            await session.refresh(department)
        return department

    async def update(self, id: int, data: dict[str, Any]) -> Department | None:
        """更新部门"""
        async with self._session() as session:
            result = await session.execute(select(Department).where(Department.id == id))
            department = result.scalar_one_or_none()
            if department is None:
                return None
            for key, value in data.items():
                if key != "id":
                    setattr(department, key, value)
            await session.flush()
            await session.refresh(department)
        return department

    async def delete(self, id: int) -> bool:
        """删除部门"""
        async with self._session() as session:
            result = await session.execute(select(Department).where(Department.id == id))
            department = result.scalar_one_or_none()
            if department is None:
                return False
            await session.delete(department)
            await session.flush()
        return True

    async def delete_and_migrate_users(
        self, id: int, *, default_department_id: int = 1
    ) -> DepartmentDeletionResult | None:
        """迁移部门用户、删除关联 API Key，并原子删除部门。"""
        async with self._session() as session:
            result = await session.execute(select(Department).where(Department.id == id))
            department = result.scalar_one_or_none()
            if department is None:
                return None

            user_result = await session.execute(select(User).where(User.department_id == id))
            users = list(user_result.scalars().all())
            for user in users:
                user.department_id = default_department_id

            await session.execute(
                update(APIKey)
                .where(APIKey.department_id == id)
                .values(is_enabled=False, revoked_at=utc_now_naive(), department_id=None)
            )
            await session.delete(department)
            await session.flush()
            return DepartmentDeletionResult(name=department.name, migrated_user_count=len(users))

    async def count_users(self, id: int) -> int:
        """统计部门用户数量"""
        async with self._session() as session:
            result = await session.execute(
                select(func.count(User.id)).where(User.department_id == id, User.is_deleted == 0)
            )
            return result.scalar() or 0

    async def exists_by_name(self, name: str) -> bool:
        """检查部门名称是否存在"""
        async with self._session() as session:
            result = await session.execute(select(Department.id).where(Department.name == name))
            return result.scalar_one_or_none() is not None
