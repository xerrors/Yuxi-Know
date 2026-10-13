"""真实 PostgreSQL 证明角色与最后系统管理员的并发约束。"""

import asyncio
import os
import uuid

import asyncpg
import pytest

from yuxi.migrations.schema import IDENTITY_PERMISSION_STATEMENTS


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.self_managed_resources
async def test_role_downgrade_and_concurrent_last_superadmin_deletion():
    """两个连接竞争删除时仍保留一个有效账号，直接 SQL 不能降级。"""
    schema = f"permission_{uuid.uuid4().hex}"
    dsn = os.environ["POSTGRES_URL"].replace("+asyncpg", "")
    connections = [await asyncpg.connect(dsn) for _ in range(3)]
    owner, first, second = connections
    try:
        await owner.execute(f'CREATE SCHEMA "{schema}"')
        for connection in connections:
            await connection.execute(f'SET search_path TO "{schema}"')
        await owner.execute("CREATE TABLE users (id int PRIMARY KEY, role text, is_deleted int)")
        for statement in IDENTITY_PERMISSION_STATEMENTS:
            await owner.execute(statement)
        await owner.execute("INSERT INTO users VALUES (1, 'superadmin', 0), (2, 'superadmin', 0)")
        with pytest.raises(asyncpg.CheckViolationError, match="禁止降级"):
            await owner.execute("UPDATE users SET role='admin' WHERE id=1")
        transaction = first.transaction()
        await transaction.start()
        await first.execute("UPDATE users SET is_deleted=1 WHERE id=1")
        pending = asyncio.create_task(second.execute("UPDATE users SET is_deleted=1 WHERE id=2"))
        try:
            for _ in range(100):
                waiting = await owner.fetchval("SELECT wait_event = 'advisory' FROM pg_stat_activity WHERE pid=$1", second.get_server_pid())
                if waiting:
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("第二条删除没有到达共同事务锁")
            await transaction.commit()
            with pytest.raises(asyncpg.CheckViolationError, match="保留一个"):
                await asyncio.wait_for(pending, 5)
        finally:
            if not pending.done():
                await transaction.rollback()
                await pending
        assert await owner.fetchval("SELECT count(*) FROM users WHERE role='superadmin' AND is_deleted=0") == 1
        with pytest.raises(asyncpg.CheckViolationError, match="保留一个"):
            await owner.execute("DELETE FROM users WHERE id=2")
        assert await owner.fetchval("SELECT role FROM users WHERE id=2") == "superadmin"
    finally:
        await owner.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        for connection in connections:
            await connection.close()
