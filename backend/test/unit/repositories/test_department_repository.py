"""部门 repository 的事务行为测试。"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.repositories.department_repository import DepartmentRepository
from yuxi.storage.postgres.models_business import APIKey, Base, Department, User
from yuxi.utils.auth_utils import AuthUtils

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


@pytest_asyncio.fixture()
async def department_session():
    """创建包含默认部门和待删除部门的 SQLite 会话。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        default_department = Department(name="默认部门")
        deleted_department = Department(name="待删除部门")
        session.add_all([default_department, deleted_department])
        await session.flush()
        user = User(
            username="Department User",
            uid="department_user",
            password_hash="$argon2id$placeholder",
            role="user",
            department_id=deleted_department.id,
        )
        session.add(user)
        await session.flush()
        _secret, key_hash, key_prefix = AuthUtils.generate_api_key()
        api_key = APIKey(
            key_hash=key_hash,
            key_prefix=key_prefix,
            name="department key",
            user_id=user.id,
            department_id=deleted_department.id,
            created_by=str(user.id),
        )
        session.add(api_key)
        await session.commit()
        yield session, default_department, deleted_department, user, api_key
    await engine.dispose()


async def test_delete_department_migrates_users_and_revokes_department_keys(department_session):
    """部门删除必须在一次提交中迁移用户并撤销部门 Key。"""
    session, default_department, deleted_department, user, api_key = department_session

    result = await DepartmentRepository(session).delete_and_migrate_users(
        deleted_department.id,
        default_department_id=default_department.id,
    )

    assert result is not None
    assert result.name == "待删除部门"
    assert result.migrated_user_count == 1
    assert user.department_id == default_department.id
    assert await session.scalar(select(User.id).where(User.id == user.id)) == user.id
    assert await session.get(Department, deleted_department.id) is None
    key_result = await session.execute(select(APIKey).where(APIKey.id == api_key.id))
    persisted_key = key_result.scalar_one()
    assert persisted_key.is_enabled is False
    assert persisted_key.revoked_at is not None
    assert persisted_key.department_id is None


class _CountingSession:
    """记录 execute 次数的会话代理，用于守卫聚合查询不随部门数放大。"""

    def __init__(self, session):
        self._session = session
        self.execute_count = 0

    async def execute(self, *args, **kwargs):
        self.execute_count += 1
        return await self._session.execute(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._session, name)


async def test_list_with_user_count_uses_bounded_queries(department_session):
    """部门目录用户计数必须是单次聚合查询，不得逐部门 COUNT（负向：恢复 N+1 循环后计数超过 2）。"""
    session, _default_department, deleted_department, user, _api_key = department_session
    counting = _CountingSession(session)
    departments = await DepartmentRepository(counting).list_with_user_count()
    assert len(departments) == 2
    assert counting.execute_count == 2
    counts = {department["id"]: department["user_count"] for department in departments}
    assert counts[deleted_department.id] == 1
    assert counts[_default_department.id] == 0
