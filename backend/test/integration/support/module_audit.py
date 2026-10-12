"""模块缺陷测试的隔离数据库与真实 HTTP 生命周期。"""

import asyncio
import socket
from contextlib import asynccontextmanager

import httpx
import uvicorn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from test.integration.support.postgres_schema import create_isolated_manager, drop_isolated_schema
from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.infrastructure.redis import close_async_redis_client, get_async_redis_client
from yuxi.migrations.schema import create_business_tables, create_knowledge_tables
from yuxi.modules.knowledge.models import KnowledgeBase


@asynccontextmanager
async def isolated_audit_store(monkeypatch):
    """每个用例创建独立 Schema，沿用真实 session 提交边界。"""
    schema, admin, engine, manager = await create_isolated_manager("pytest_module_audit")
    manager.AsyncSession = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(pg_manager, "get_async_session_context", manager.get_async_session_context)
    try:
        await create_business_tables(manager)
        await create_knowledge_tables(manager)
        yield manager, manager.AsyncSession
    finally:
        async with manager.AsyncSession() as db:
            kb_ids = list((await db.scalars(select(KnowledgeBase.kb_id))).all())
        if kb_ids:
            redis = await get_async_redis_client()
            await redis.delete(
                *[
                    key
                    for kb_id in kb_ids
                    for key in (f"yuxi:knowledge_base:{kb_id}", f"yuxi:knowledge_base:{kb_id}:lock", f"yuxi:kb_file_stats:{kb_id}")
                ]
            )
        await close_async_redis_client()
        await drop_isolated_schema(schema, admin, engine)


@asynccontextmanager
async def serve_http(app):
    """经真实 TCP 请求执行路由，退出时停止服务。"""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        server = uvicorn.Server(uvicorn.Config(app, lifespan="off", log_level="error"))
        serving = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(10):
                while not server.started:
                    if serving.done():
                        serving.result()
                    await asyncio.sleep(0.01)
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{listener.getsockname()[1]}") as client:
                yield client
        finally:
            server.should_exit = True
            await asyncio.wait_for(serving, timeout=10)
