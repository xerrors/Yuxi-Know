"""API 进程启动组件、readiness 状态与资源关闭适配。"""

import inspect
from collections.abc import Callable

from fastapi import FastAPI
from yuxi import get_version
from yuxi.infrastructure.observability.logging import logger
from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.infrastructure.postgres.schema import require_current_schema
from yuxi.modules.agents.runtime.sandbox.provider import check_sandbox_provider
from yuxi.modules.agents.services.transport import get_redis_client
from yuxi.modules.extensions.mcp.service import ensure_builtin_mcp_servers_in_db
from yuxi.modules.identity.oidc import get_oidc_config
from yuxi.modules.identity.security import AuthUtils
from yuxi.modules.models.providers.service import ensure_builtin_model_providers_in_db


class RequiredStartupComponentError(RuntimeError):
    """核心启动组件失败且当前进程不得继续接流量。"""

    def __init__(self, component: str, code: str):
        self.component = component
        self.code = code
        super().__init__(f"Required startup component failed: component={component}, type={code}")


async def _startup(app: FastAPI) -> None:
    """取得 API 运行资源并发布结构化启动状态。"""

    app.state.startup_complete = False
    app.state.startup_components = {}

    await _initialize_startup_component(
        app,
        name="security_secrets",
        required=True,
        operation=AuthUtils.require_security_secrets,
    )

    await _initialize_startup_component(
        app,
        name="oidc_config",
        required=True,
        operation=get_oidc_config,
    )

    # Schema 只由 Compose 中的 schema-init 修改；运行进程仅校验兼容版本。
    pg_manager.initialize()
    await require_current_schema(pg_manager)

    from yuxi.bootstrap.options import ensure_options_in_db
    from yuxi.modules.system.options import system_options
    from yuxi.modules.system.services.options import invalidate_option_cache

    async with pg_manager.get_async_session_context() as session:
        await ensure_options_in_db(session)
        await session.commit()
    await invalidate_option_cache(system_options.key)

    await _initialize_startup_component(
        app,
        name="builtin_mcp_servers",
        required=False,
        operation=ensure_builtin_mcp_servers_in_db,
    )

    async def initialize_builtin_skills() -> None:
        """在独立事务中安装内置 Skills。"""

        from yuxi.modules.extensions.skills.builtin.sync import init_builtin_skills

        async with pg_manager.get_async_session_context() as session:
            await init_builtin_skills(session)

    await _initialize_startup_component(
        app,
        name="builtin_skills",
        required=True,
        operation=initialize_builtin_skills,
    )

    async def initialize_default_agents() -> None:
        """确保平台至少具有可用的默认 Agent 定义。"""

        from yuxi.modules.agents.services.configuration import initialize_agent_presets

        async with pg_manager.get_async_session_context() as session:
            await initialize_agent_presets(session)

    await _initialize_startup_component(
        app,
        name="default_agents",
        required=True,
        operation=initialize_default_agents,
    )

    # 初始化内置模型供应商配置
    async def initialize_model_providers() -> None:
        """确保内置模型供应商定义可以从数据库读取。"""

        async with pg_manager.get_async_session_context() as session:
            await ensure_builtin_model_providers_in_db(session)

    await _initialize_startup_component(
        app,
        name="model_providers",
        required=True,
        operation=initialize_model_providers,
    )

    # 初始化模型缓存（v2 模型选择使用）
    async def initialize_model_cache() -> None:
        """用 PostgreSQL 当前供应商事实重建进程内模型缓存。"""

        from yuxi.modules.models.providers.cache import model_cache
        from yuxi.modules.models.providers.service import get_all_model_providers

        async with pg_manager.get_async_session_context() as session:
            providers = await get_all_model_providers(session)
            model_cache.rebuild(providers)

    await _initialize_startup_component(
        app,
        name="model_cache",
        required=True,
        operation=initialize_model_cache,
    )

    # 初始化知识库管理器
    from yuxi.modules.knowledge.runtime import knowledge_base

    await _initialize_startup_component(
        app,
        name="knowledge_base",
        required=True,
        operation=knowledge_base.initialize,
    )

    # 预热 Redis（run 队列）
    try:
        redis = await get_redis_client()
        await redis.ping()
    except Exception as e:
        logger.warning(f"Run queue redis unavailable on startup: {e}")

    await _initialize_startup_component(
        app,
        name="sandbox_provider",
        required=True,
        operation=check_sandbox_provider,
    )

    app.state.startup_complete = True
    logger.info(f"""

░██     ░██                       ░██
 ░██   ░██
  ░██ ░██   ░██    ░██ ░██    ░██ ░██
   ░████    ░██    ░██  ░██  ░██  ░██
    ░██     ░██    ░██   ░█████   ░██
    ░██     ░██   ░███  ░██  ░██  ░██
    ░██      ░█████░██ ░██    ░██ ░██  v{get_version()}

    """)
    logger.info("Yuxi backend startup complete")


async def _shutdown_component(name: str, operation: Callable[[], object]) -> None:
    """尽力释放一个已取得或部分取得的资源，并继续执行后续清理。"""

    try:
        result = operation()
        if inspect.isawaitable(result):
            await result
    except Exception as exc:
        logger.error(f"Shutdown component failed: component={name}, type={type(exc).__name__}")


def _close_neo4j_connection() -> object:
    """关闭共享图数据库连接。"""

    from yuxi.infrastructure.neo4j import close_shared_neo4j_connection

    return close_shared_neo4j_connection()


async def _initialize_startup_component(
    app: FastAPI,
    *,
    name: str,
    required: bool,
    operation: Callable[[], object],
) -> None:
    """执行启动组件并保存非敏感、可供 readiness 使用的能力状态。"""

    try:
        result = operation()
        if inspect.isawaitable(result):
            await result
    except Exception as exc:
        code = type(exc).__name__
        app.state.startup_components[name] = {
            "status": "error",
            "required": required,
            "code": code,
        }
        logger.error(f"Startup component failed: component={name}, required={required}, type={code}")
        if required:
            raise RequiredStartupComponentError(name, code) from None
    else:
        app.state.startup_components[name] = {"status": "ok", "required": required}
