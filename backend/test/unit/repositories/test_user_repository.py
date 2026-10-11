"""用户 repository 的凭据撤销测试。"""

from __future__ import annotations

from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from test.support.sqlite import create_utc_sqlite_engine
from yuxi.modules.identity.repositories.users import UserRepository
from yuxi.modules.identity.models import APIKey, Department, User
from yuxi.infrastructure.postgres.base import Base
from yuxi.modules.identity.security import AuthUtils
from yuxi.shared.datetime import utc_now

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


@pytest_asyncio.fixture()
async def user_session():
    """创建带活动 Key 与历史 tombstone 的 SQLite 会话。"""

    engine = create_utc_sqlite_engine()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        user = User(
            username="Delete User",
            uid="delete_user",
            password_hash="$argon2id$placeholder",
            role="user",
        )
        session.add(user)
        await session.flush()
        keys = []
        for name in ("active", "already revoked"):
            _secret, key_hash, key_prefix = AuthUtils.generate_api_key()
            keys.append(
                APIKey(
                    key_hash=key_hash,
                    key_prefix=key_prefix,
                    name=name,
                    user_id=user.id,
                    created_by=str(user.id),
                )
            )
        previous_revocation = utc_now() - timedelta(days=1)
        keys[1].is_enabled = False
        keys[1].revoked_at = previous_revocation
        session.add_all(keys)
        await session.commit()
        yield session, user, keys, previous_revocation
    await engine.dispose()


async def test_user_page_filters_before_pagination_and_excludes_deleted_users(user_session) -> None:
    """分页过滤必须作用于全部有效用户，而不是只过滤当前页。"""

    session, user, _keys, _previous_revocation = user_session
    department = Department(name="Paged Department")
    session.add(department)
    await session.flush()
    users = [
        User(
            username=f"Page User {index}",
            uid=f"page_user_{index}",
            phone_number=f"1380000000{index}",
            password_hash="$argon2id$placeholder",
            role="user" if index < 3 else "admin",
            department_id=department.id,
            is_deleted=1 if index == 1 else 0,
        )
        for index in range(4)
    ]
    session.add_all(users)
    await session.commit()

    rows, total = await UserRepository(session).list_page_with_department(
        offset=1,
        limit=1,
        department_id=department.id,
        role="user",
        search="page_user_",
    )

    assert total == 2
    assert [row[0].uid for row in rows] == ["page_user_2"]
    assert rows[0][1] == department.name
    assert all(row[0].is_deleted == 0 for row in rows)


async def test_soft_delete_tombstones_all_api_keys_without_rewriting_history(user_session) -> None:
    """通用软删除入口也必须阻止旧请求复活凭据。"""

    session, user, keys, previous_revocation = user_session

    deleted = await UserRepository(session).soft_delete(user.id, username=user.username)

    assert deleted is True
    assert user.is_deleted == 1
    assert keys[0].is_enabled is False
    assert keys[0].revoked_at is not None
    assert keys[1].is_enabled is False
    assert keys[1].revoked_at == previous_revocation


async def test_user_page_defaults_to_humans_and_filters_kind_before_counting(user_session) -> None:
    """按真实类型筛选，长 ID 前缀不影响系统用户的可见性。"""
    session, owner, _keys, _revocation = user_session
    human = User(username="endusr_human", uid="endusr_human", password_hash="!disabled", role="user")
    end_user = User(
        username="visitor",
        uid="endusr_visitor",
        password_hash="!disabled",
        role="user",
        user_kind="end_user",
        owner_user_id=owner.id,
        app_id="support-app",
        end_user_id="visitor",
    )
    session.add_all([human, end_user])
    await session.commit()
    repo = UserRepository(session)
    rows, total = await repo.list_page_with_department(offset=0, limit=1, search="endusr_")
    assert total == 1
    assert [row[0].id for row in rows] == [human.id]
    rows, total = await repo.list_page_with_department(offset=0, limit=1, search="endusr_", user_kind="end_user")
    assert total == 1
    assert [row[0].id for row in rows] == [end_user.id]
    rows, total = await repo.list_page_with_department(offset=1, limit=1, search="endusr_", user_kind=None)
    assert total == 2
    assert [row[0].id for row in rows] == [end_user.id]

    assert [item.id for item in await repo.list_users(skip=1, limit=1)] == [human.id]
    assert [item.id for item in await repo.list_users(skip=2, limit=1)] == []
    assert [row[0].id for row in await repo.list_with_department(skip=1, limit=1)] == [human.id]
    assert [row[0].id for row in await repo.list_with_department(skip=2, limit=1)] == []
    assert await repo.count() == 2
    assert end_user.uid in await repo.get_all_uids()
    assert (await repo.get_by_uid(end_user.uid)).id == end_user.id
    assert (await repo.get_by_username(end_user.username)).id == end_user.id
