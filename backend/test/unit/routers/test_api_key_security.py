from __future__ import annotations

from datetime import timedelta

import pytest
import pytest_asyncio
from yuxi.shared.errors import PermissionDeniedError
from sqlalchemy.ext.asyncio import async_sessionmaker

from test.support.sqlite import create_utc_sqlite_engine

from yuxi.api.routers.identity.auth import delete_user
from yuxi.api.routers.identity.users import APIKeyCreate, create_api_key, get_accessible_api_key
from yuxi.modules.identity.services.public_auth import verify_api_key
from yuxi.modules.identity.repositories.api_keys import APIKeyRepository
from yuxi.modules.identity.models import APIKey, Department, User
from yuxi.infrastructure.postgres.base import Base
from yuxi.modules.identity.security import AuthUtils
from yuxi.shared.datetime import utc_now

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


@pytest.fixture(autouse=True)
def api_key_derivation_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY_DERIVATION_SECRET", "test-api-key-derivation-secret-32-chars")


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeApiKeySession:
    def __init__(self, api_key: APIKey):
        self.api_key = api_key
        self.execute_calls = 0

    async def execute(self, _statement):
        self.execute_calls += 1
        return _ScalarResult(self.api_key)


@pytest_asyncio.fixture()
async def session():
    engine = create_utc_sqlite_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        dept_a = Department(name="Dept A")
        dept_b = Department(name="Dept B")
        superadmin = User(
            username="Super Admin",
            uid="superadmin",
            password_hash="$argon2id$placeholder",
            role="superadmin",
            department=dept_a,
        )
        dept_b_admin = User(
            username="Dept B Admin",
            uid="dept_b_admin",
            password_hash="$argon2id$placeholder",
            role="admin",
            department=dept_b,
        )
        regular_user = User(
            username="Regular",
            uid="regular",
            password_hash="$argon2id$placeholder",
            role="user",
            department=dept_a,
        )
        deleted_user = User(
            username="Deleted",
            uid="deleted",
            password_hash="$argon2id$placeholder",
            role="user",
            department=dept_a,
            is_deleted=1,
        )
        db.add_all([dept_a, dept_b, superadmin, dept_b_admin, regular_user, deleted_user])
        await db.commit()
        for item in [dept_a, dept_b, superadmin, dept_b_admin, regular_user, deleted_user]:
            await db.refresh(item)
        yield {
            "db": db,
            "dept_a": dept_a,
            "dept_b": dept_b,
            "superadmin": superadmin,
            "dept_b_admin": dept_b_admin,
            "regular_user": regular_user,
            "deleted_user": deleted_user,
        }
    await engine.dispose()


async def test_api_key_rejects_deleted_bound_user_without_department_or_superadmin_fallback(session):
    db = session["db"]
    secret, key_hash, key_prefix = AuthUtils.generate_api_key()
    api_key = APIKey(
        key_hash=key_hash,
        key_prefix=key_prefix,
        name="deleted user key",
        user_id=session["deleted_user"].id,
        department_id=session["dept_b"].id,
        created_by=str(session["deleted_user"].id),
    )
    db.add(api_key)
    await db.commit()

    user, verified_key = await verify_api_key(secret, db)

    assert user is None
    assert verified_key is None


async def test_api_key_without_user_binding_is_rejected_before_department_mapping(session):
    secret, key_hash, key_prefix = AuthUtils.generate_api_key()
    api_key = APIKey(
        key_hash=key_hash,
        key_prefix=key_prefix,
        name="department key",
        user_id=None,
        department_id=session["dept_b"].id,
        created_by=str(session["superadmin"].id),
    )
    fake_db = _FakeApiKeySession(api_key)

    user, verified_key = await verify_api_key(secret, fake_db)

    assert user is None
    assert verified_key is None
    assert fake_db.execute_calls == 1


async def test_create_api_key_rejects_mismatched_department(session):
    db = session["db"]

    with pytest.raises(PermissionDeniedError) as exc:
        await create_api_key(
            APIKeyCreate(
                request_id="request-wrong-department",
                name="wrong department",
                department_id=session["dept_b"].id,
            ),
            current_user=session["regular_user"],
            db=db,
        )

    assert exc.value.message


async def test_create_api_key_allows_current_user_department(session):
    db = session["db"]

    response = await create_api_key(
        APIKeyCreate(
            request_id="request-own-department",
            name="own department",
            department_id=session["dept_a"].id,
        ),
        current_user=session["regular_user"],
        db=db,
    )

    assert response["api_key"]["user_id"] == session["regular_user"].id
    assert response["api_key"]["department_id"] == session["dept_a"].id
    assert response["secret"].startswith(response["api_key"]["key_prefix"])


async def test_api_key_repository_enforces_requester_visibility(session):
    """非超级管理员的查询必须在 repository 层过滤其他用户的 Key。"""
    db = session["db"]
    _secret, key_hash, key_prefix = AuthUtils.generate_api_key()
    api_key = APIKey(
        key_hash=key_hash,
        key_prefix=key_prefix,
        name="regular user key",
        user_id=session["regular_user"].id,
        department_id=session["dept_a"].id,
        created_by=str(session["regular_user"].id),
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    repository = APIKeyRepository(db)

    foreign_access = await repository.get_accessible(
        api_key_id=api_key.id,
        requester_user_id=session["dept_b_admin"].id,
        is_superadmin=False,
    )
    assert foreign_access.api_key is None
    assert foreign_access.exists is True

    with pytest.raises(PermissionDeniedError) as exc:
        await get_accessible_api_key(repository, api_key.id, session["dept_b_admin"])
    assert exc.value.message

    superadmin_access = await repository.get_accessible(
        api_key_id=api_key.id,
        requester_user_id=session["superadmin"].id,
        is_superadmin=True,
    )
    assert superadmin_access.api_key is api_key


async def test_delete_user_disables_owned_api_keys(session):
    db = session["db"]
    _secret, key_hash, key_prefix = AuthUtils.generate_api_key()
    api_key = APIKey(
        key_hash=key_hash,
        key_prefix=key_prefix,
        name="owned key",
        user_id=session["regular_user"].id,
        created_by=str(session["regular_user"].id),
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    result = await delete_user(session["regular_user"].id, session["superadmin"], db)
    await db.refresh(api_key)

    assert result["success"] is True
    assert api_key.is_enabled is False


@pytest.mark.parametrize("key_state", ["valid", "disabled", "revoked", "expired"])
async def test_identity_verifies_api_key_lifecycle(session, key_state):
    """只有未停用、未撤销、未过期的凭据返回绑定身份。"""
    db = session["db"]
    owner = session["regular_user"]
    secret, key_hash, key_prefix = AuthUtils.generate_api_key()
    key = APIKey(
        key_hash=key_hash,
        key_prefix=key_prefix,
        name="lifecycle key",
        user_id=owner.id,
        created_by=str(owner.id),
        is_enabled=key_state != "disabled",
        revoked_at=utc_now() if key_state == "revoked" else None,
        expires_at=utc_now() - timedelta(seconds=1) if key_state == "expired" else None,
    )
    db.add(key)
    await db.commit()

    result = await verify_api_key(secret, db)
    assert result == ((owner, key) if key_state == "valid" else (None, None))
    assert await verify_api_key("yxkey_unknown", db) == (None, None)
