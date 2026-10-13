"""真实 PostgreSQL 上的组织身份用例事务测试。"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from yuxi.modules.identity.services.administration import (
    DepartmentAdminCreation,
    IdentityConflictError,
    SystemAlreadyInitializedError,
    create_department_with_admin,
    initialize_system_admin,
)
from yuxi.bootstrap.models import load_models
from yuxi.infrastructure.postgres.base import Base
from yuxi.modules.identity.models import Department, User

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.self_managed_resources]


async def test_user_conflict_rolls_back_new_department() -> None:
    """管理员插入失败时不得留下无管理员部门。"""

    unique = uuid.uuid4().hex[:8]
    conflict_department_name = f"uow-conflict-{unique}"
    attempted_department_name = f"uow-attempt-{unique}"
    conflicting_username = f"uow_admin_{unique}"
    conflicting_uid = f"uow_other_{unique}"
    engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    conflict_id: int | None = None
    conflict_department_id: int | None = None

    try:
        async with factory() as db:
            conflict_department = Department(name=conflict_department_name)
            db.add(conflict_department)
            await db.flush()
            conflict_department_id = conflict_department.id
            conflict = User(
                username=conflicting_username,
                uid=conflicting_uid,
                password_hash="$argon2id$placeholder",
                role="user",
                department_id=conflict_department.id,
            )
            db.add(conflict)
            await db.commit()
            conflict_id = conflict.id

        async with factory() as db:
            with pytest.raises(IdentityConflictError):
                await create_department_with_admin(
                    db,
                    name=attempted_department_name,
                    description="must rollback",
                    admin_uid=conflicting_username,
                    admin_password="valid-password-123",
                    admin_phone=None,
                )

        async with factory() as db:
            attempted_department = await db.scalar(select(Department).where(Department.name == attempted_department_name))
            attempted_admin = await db.scalar(select(User).where(User.uid == conflicting_username))

        assert attempted_department is None
        assert attempted_admin is None
    finally:
        async with factory() as db:
            if conflict_id is not None:
                await db.execute(delete(User).where(User.id == conflict_id))
            if conflict_department_id is not None:
                await db.execute(delete(Department).where(Department.id == conflict_department_id))
            await db.commit()
        await engine.dispose()


async def test_concurrent_initialization_has_exactly_one_atomic_winner() -> None:
    """干净 schema 的并发首次初始化必须只产生一套完整身份事实。"""

    load_models()
    schema = f"pytest_init_{uuid.uuid4().hex[:16]}"
    admin_uids = (f"init_a_{uuid.uuid4().hex[:8]}", f"init_b_{uuid.uuid4().hex[:8]}")
    admin_engine = create_async_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    scoped_engine = None

    try:
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))

        scoped_engine = create_async_engine(
            os.environ["POSTGRES_URL"],
            pool_pre_ping=True,
            connect_args={"server_settings": {"search_path": schema}},
        )
        async with scoped_engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(scoped_engine, expire_on_commit=False)

        async def initialize(uid: str):
            async with factory() as db:
                try:
                    return await initialize_system_admin(
                        db,
                        uid=uid,
                        password="valid-password-123",
                        phone_number=None,
                    )
                except Exception as exc:
                    return exc

        results = await asyncio.gather(*(initialize(uid) for uid in admin_uids))

        async with factory() as db:
            department_count = await db.scalar(select(func.count(Department.id)))
            user_count = await db.scalar(select(func.count(User.id)))
            operation_log_table = await db.scalar(text("SELECT to_regclass(:table)"), {"table": f"{schema}.operation_logs"})

        assert sum(isinstance(result, DepartmentAdminCreation) for result in results) == 1
        assert sum(isinstance(result, SystemAlreadyInitializedError) for result in results) == 1
        assert department_count == 1
        assert user_count == 1
        assert operation_log_table is None
    finally:
        if scoped_engine is not None:
            await scoped_engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin_engine.dispose()
