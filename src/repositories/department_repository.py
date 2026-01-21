"""部门数据访问层 - Repository"""

from typing import Any

from sqlalchemy import func, select

from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import Department


class DepartmentRepository:
    """部门数据访问层"""

    async def get_by_id(self, id: int) -> Department | None:
        """根据 ID 获取部门"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(Department).where(Department.id == id))
            return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Department | None:
        """根据名称获取部门"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(Department).where(Department.name == name))
            return result.scalar_one_or_none()

    async def list_departments(self) -> list[Department]:
        """获取所有部门列表"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(Department).order_by(Department.created_at.desc()))
            return list(result.scalars().all())

    async def list_with_user_count(self) -> list[dict[str, Any]]:
        """获取所有部门列表，包含用户数量"""
        async with pg_manager.get_async_session_context() as session:
            from src.storage.postgres.models_business import User

            result = await session.execute(select(Department).order_by(Department.created_at.desc()))
            departments = result.scalars().all()

            department_list = []
            for dep in departments:
                user_count_result = await session.execute(
                    select(func.count(User.id)).where(User.department_id == dep.id, User.is_deleted == 0)
                )
                user_count = user_count_result.scalar()
                dep_dict = dep.to_dict()
                dep_dict["user_count"] = user_count
                department_list.append(dep_dict)

            return department_list

    async def create(self, data: dict[str, Any]) -> Department:
        """创建部门"""
        async with pg_manager.get_async_session_context() as session:
            department = Department(**data)
            session.add(department)
        return department

    async def update(self, id: int, data: dict[str, Any]) -> Department | None:
        """更新部门"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(Department).where(Department.id == id))
            department = result.scalar_one_or_none()
            if department is None:
                return None
            for key, value in data.items():
                if key != "id":
                    setattr(department, key, value)
        return department

    async def delete(self, id: int) -> bool:
        """删除部门"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(Department).where(Department.id == id))
            department = result.scalar_one_or_none()
            if department is None:
                return False
            await session.delete(department)
        return True

    async def count_users(self, id: int) -> int:
        """统计部门用户数量"""
        async with pg_manager.get_async_session_context() as session:
            from src.storage.postgres.models_business import User

            result = await session.execute(
                select(func.count(User.id)).where(User.department_id == id, User.is_deleted == 0)
            )
            return result.scalar() or 0

    async def exists_by_name(self, name: str) -> bool:
        """检查部门名称是否存在"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(Department.id).where(Department.name == name))
            return result.scalar_one_or_none() is not None
