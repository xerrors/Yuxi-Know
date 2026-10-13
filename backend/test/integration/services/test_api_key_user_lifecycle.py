"""真实 PostgreSQL 上的用户删除与 API Key 创建串行化测试。"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.modules.identity.repositories.api_keys import APIKeyRepository, APIKeySubjectUnavailable
from yuxi.modules.identity.repositories.users import UserRepository
from yuxi.modules.identity.models import APIKey, User
from yuxi.modules.identity.security import AuthUtils

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


async def _create_user(factory: async_sessionmaker) -> int:
    """创建独立生命周期测试用户。"""

    suffix = uuid.uuid4().hex[:12]
    async with factory() as db:
        user = User(
            username=f"key_lifecycle_{suffix}",
            uid=f"key_lifecycle_{suffix}",
            password_hash="$argon2id$placeholder",
            role="user",
        )
        db.add(user)
        await db.commit()
        return user.id


async def _cleanup_user(factory: async_sessionmaker, user_id: int) -> None:
    """物理清理隔离测试事实。"""

    async with factory() as db:
        await db.execute(delete(APIKey).where(APIKey.user_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


def _api_key_args(user_id: int, request_id: str) -> dict:
    """生成一次 repository 创建调用的稳定参数。"""

    _secret, key_hash, key_prefix = AuthUtils.generate_api_key()
    return {
        "key_hash": key_hash,
        "key_prefix": key_prefix,
        "request_id": request_id,
        "name": "lifecycle lock",
        "user_id": user_id,
        "department_id": None,
        "expires_at": None,
        "created_by": str(user_id),
    }


async def test_delete_first_blocks_create_and_rechecks_active_user() -> None:
    """删除先持有 User 锁时，创建必须等待并在提交后拒绝。"""

    engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = await _create_user(factory)
    delete_ready = asyncio.Event()
    allow_delete_commit = asyncio.Event()
    create_started = asyncio.Event()

    async def delete_user() -> None:
        async with factory() as db:
            repository = UserRepository(db)
            user = await repository.get_active_by_id(user_id, for_update=True)
            assert user is not None
            await repository.delete_for_admin(user)
            delete_ready.set()
            await allow_delete_commit.wait()
            await db.commit()

    async def create_key() -> None:
        await delete_ready.wait()
        async with factory() as db:
            create_started.set()
            with pytest.raises(APIKeySubjectUnavailable):
                await APIKeyRepository(db).create(**_api_key_args(user_id, f"delete-first-{uuid.uuid4()}"))
            await db.rollback()

    delete_task = asyncio.create_task(delete_user())
    create_task = asyncio.create_task(create_key())
    try:
        await create_started.wait()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(create_task), timeout=0.2)
        allow_delete_commit.set()
        await asyncio.gather(delete_task, create_task)

        async with factory() as db:
            user = await db.get(User, user_id)
            key_count = await db.scalar(select(func.count(APIKey.id)).where(APIKey.user_id == user_id))
        assert user is not None and user.is_deleted == 1
        assert key_count == 0
    finally:
        allow_delete_commit.set()
        await asyncio.gather(delete_task, create_task, return_exceptions=True)
        await _cleanup_user(factory, user_id)
        await engine.dispose()


async def test_create_first_makes_delete_revoke_committed_key() -> None:
    """创建先持有 User 锁时，删除必须等待并撤销刚提交的 Key。"""

    engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = await _create_user(factory)
    create_ready = asyncio.Event()
    allow_create_commit = asyncio.Event()
    delete_started = asyncio.Event()
    created_key_id: int | None = None

    async def create_key() -> None:
        nonlocal created_key_id
        async with factory() as db:
            api_key = await APIKeyRepository(db).create(**_api_key_args(user_id, f"create-first-{uuid.uuid4()}"))
            created_key_id = api_key.id
            create_ready.set()
            await allow_create_commit.wait()
            await db.commit()

    async def delete_user() -> None:
        await create_ready.wait()
        async with factory() as db:
            delete_started.set()
            repository = UserRepository(db)
            user = await repository.get_active_by_id(user_id, for_update=True)
            assert user is not None
            await repository.delete_for_admin(user)
            await db.commit()

    create_task = asyncio.create_task(create_key())
    delete_task = asyncio.create_task(delete_user())
    try:
        await delete_started.wait()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(delete_task), timeout=0.2)
        allow_create_commit.set()
        await asyncio.gather(create_task, delete_task)

        assert created_key_id is not None
        async with factory() as db:
            api_key = await db.get(APIKey, created_key_id)
            user = await db.get(User, user_id)
        assert user is not None and user.is_deleted == 1
        assert api_key is not None and api_key.is_enabled is False
        assert api_key.revoked_at is not None
    finally:
        allow_create_commit.set()
        await asyncio.gather(create_task, delete_task, return_exceptions=True)
        await _cleanup_user(factory, user_id)
        await engine.dispose()
