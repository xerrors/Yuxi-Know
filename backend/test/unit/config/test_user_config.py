from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from test.support.sqlite import create_utc_sqlite_engine

from yuxi.modules.identity.preferences import UserConfig, UserConfigSchema
from yuxi.modules.identity.services.preferences import save_user_config
from yuxi.infrastructure.postgres.base import Base
from yuxi.modules.identity.models import Department, User
from yuxi.modules.identity.models import UserConfig as UserConfigRecord

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


@pytest_asyncio.fixture()
async def session():
    engine = create_utc_sqlite_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        department = Department(name="Config Dept")
        user = User(
            username="Config User",
            uid="config_user",
            password_hash="$argon2id$placeholder",
            role="user",
            department=department,
        )
        db.add_all([department, user])
        await db.commit()
        await db.refresh(user)
        yield db, user
    await engine.dispose()


async def test_user_config_load_returns_defaults_without_creating_row(session):
    db, user = session

    user_config = await UserConfig.load(db, user.uid)
    dumped = user_config.dump_config()

    assert dumped["uid"] == user.uid
    assert dumped["enable_memory"] is True

    result = await db.execute(select(UserConfigRecord).filter(UserConfigRecord.uid == user.uid))
    assert result.scalar_one_or_none() is None


async def test_user_config_save_persists_user_specific_values(session):
    db, user = session

    saved = await save_user_config(db, uid=user.uid, schema=UserConfigSchema(enable_memory=False))
    loaded = await UserConfig.load(db, user.uid)

    assert saved.dump_config()["enable_memory"] is False
    assert loaded.dump_config()["enable_memory"] is False
    result = await db.execute(select(UserConfigRecord).filter(UserConfigRecord.uid == user.uid))
    assert result.scalar_one().enable_memory is False


async def test_new_user_config_record_defaults_to_enabled(session):
    """新记录默认启用，实际持久化值与配置缺省一致。"""
    db, user = session
    db.add(UserConfigRecord(uid=user.uid))
    await db.commit()

    record = await db.scalar(select(UserConfigRecord).filter(UserConfigRecord.uid == user.uid))
    assert record.enable_memory is True
