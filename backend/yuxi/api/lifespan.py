from contextlib import asynccontextmanager

from fastapi import FastAPI

from yuxi.bootstrap.api import _close_neo4j_connection, _shutdown_component, _startup
from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.infrastructure.redis.queue import close_queue_clients
from yuxi.modules.agents.runtime.sandbox import shutdown_sandbox_provider


@asynccontextmanager
async def lifespan(app: FastAPI):
    """确保 startup 任意阶段失败时仍执行已取得资源的补偿清理。"""

    app.state.startup_complete = False
    app.state.startup_components = {}
    try:
        await _startup(app)
        async with app.state.knowledge_mcp.manager.run():
            yield
    finally:
        app.state.startup_complete = False
        await _shutdown_component("sandbox_provider", shutdown_sandbox_provider)
        await _shutdown_component("queue_clients", close_queue_clients)
        await _shutdown_component("neo4j", _close_neo4j_connection)
        await _shutdown_component("postgres", pg_manager.close)
