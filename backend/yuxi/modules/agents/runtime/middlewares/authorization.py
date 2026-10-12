"""模型和工具执行边界重新读取身份与授权。"""

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from sqlalchemy import select

from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.agents.repositories.definitions import AgentRepository
from yuxi.modules.agents.runtime.context import refresh_agent_context_resources
from yuxi.modules.agents.services.event_writer import append_run_event_best_effort
from yuxi.modules.extensions.mcp.models import MCPServer
from yuxi.modules.extensions.skills.runtime import sync_agent_context_skills
from yuxi.modules.extensions.tools.builtin import BASE_TOOL_NAMES
from yuxi.modules.identity.models import User


class AgentExecutionRevoked(PermissionError):
    """账号或 Agent 使用权撤销，必须使执行形成失败终态。"""


class RuntimeAuthorizationMiddleware(AgentMiddleware):
    """每个新模型和工具调用使用当前调用者权限。"""

    async def abefore_model(self, state, runtime):
        """刷新 Skill 输入，投影同步留给实际请求边界。"""
        await _refresh_execution_resources(runtime.context)

    async def aafter_model(self, state, runtime):
        """模型返回后、审批或工具路由前复查账号与 Agent。"""
        async with pg_manager.get_async_session_context() as db:
            await _require_execution_actor(runtime.context, db=db)

    async def awrap_model_call(self, request, handler):
        """隐藏本轮已撤销的已注册工具，执行处仍再次检查。"""
        context = request.runtime.context
        await refresh_execution_authorization(context)
        tools = [tool for tool in request.tools if tool_allowed(context, tool.name, request.state)]
        return await handler(request.override(tools=tools))

    async def awrap_tool_call(self, request, handler):
        """Agent 失权终止，依赖失权返回不含资源信息的错误。"""
        context = request.runtime.context
        await refresh_execution_authorization(context)
        name = request.tool_call["name"]
        if not tool_allowed(context, name, request.state):
            if context.run_id and not getattr(context, "_capability_warning_sent", False):
                await append_run_event_best_effort(
                    context.run_id,
                    {
                        "type": "yuxi.session.turn.capability_limited",
                        "session_id": context.thread_id,
                        "turn_id": context._authorization_turn_id,
                        "yuxi": {"run_id": context.run_id},
                        "message": "部分配置能力不可用，已按当前调用者权限过滤。",
                    },
                )
                context._capability_warning_sent = True
            return ToolMessage(content="能力受限：当前调用者无权使用该工具。", tool_call_id=request.tool_call["id"], status="error")
        return await handler(request)


def tool_allowed(context, name: str, state: dict) -> bool:
    """按当前资源和已授权 Skill 依赖检查已注册工具。"""
    servers = getattr(context, "mcp_tool_servers", None)
    registered = getattr(context, "registered_builtin_tool_names", None)
    snapshot = getattr(context, "skill_runtime_snapshot", None)
    if servers is None or registered is None or snapshot is None:
        return False
    allowed_mcps = set(context.mcps)
    allowed_tools = set(context.tools) | set(BASE_TOOL_NAMES)
    active = set(state.get("activated_skills", [])) | set(snapshot["preloaded_skills"])
    for slug in active & set(snapshot["effective_skills"]):
        allowed_tools.update(snapshot["runtime_skills"][slug]["tools"])
        allowed_mcps.update(snapshot["runtime_skills"][slug]["mcps"])
    server = servers.get(name)
    if server:
        return server in allowed_mcps and server in context.disabled_mcp_tools and name not in context.disabled_mcp_tools[server]
    if name in registered:
        return name in allowed_tools
    return name in getattr(context, "middleware_tool_names", set())


async def refresh_execution_authorization(context) -> None:
    """在实际模型、摘要与工具请求前解析当前权限并同步投影。"""
    await _refresh_execution_resources(context)
    await sync_agent_context_skills(context)


async def _refresh_execution_resources(context) -> None:
    """刷新模型输入与工具可见性，读取资源不扫描投影。"""
    async with pg_manager.get_async_session_context() as db:
        user, agent, run = await _require_execution_actor(context, db=db)
        await refresh_agent_context_resources(context, db=db, user=user, agent=agent)
        rows = await db.execute(select(MCPServer.slug, MCPServer.disabled_tools).where(MCPServer.enabled == 1))
        context.disabled_mcp_tools = {slug: set(disabled or []) for slug, disabled in rows}
        if context._capability_limited and not getattr(context, "_capability_warning_sent", False) and run is not None:
            await append_run_event_best_effort(
                run.id,
                {
                    "type": "yuxi.session.turn.capability_limited",
                    "session_id": run.thread_id,
                    "turn_id": run.turn_id,
                    "message": "部分配置能力不可用，已按当前调用者权限过滤。",
                    "yuxi": {"run_id": run.id},
                },
            )
            context._capability_warning_sent = True


async def _require_execution_actor(context, *, db):
    """复查持久执行身份与 Agent 可见性，返回阶段不扫描资源。"""
    user = await db.scalar(select(User).where(User.uid == context.uid, User.is_deleted == 0))
    run = await db.get(AgentRun, context.run_id) if context.run_id else None
    if context.run_id and run is None:
        raise AgentExecutionRevoked("执行记录已失效")
    if user is None:
        raise AgentExecutionRevoked("执行账号已失效")
    if run is not None:
        context._authorization_turn_id = run.turn_id
        agent = await AgentRepository(db).get_visible_by_slug(
            slug=run.agent_slug,
            user=user,
        )
        if agent is None:
            raise AgentExecutionRevoked("Agent 使用权限已撤销")
    else:
        # 主动压缩没有 Run，使用已绑定调用者的 Thread 找到当前 Agent。
        thread = await db.scalar(
            select(Session).where(
                Session.thread_id == context.thread_id,
                Session.uid == user.uid,
                Session.status == "active",
            )
        )
        if thread is None:
            raise AgentExecutionRevoked("执行对话已失效")
        agent = await AgentRepository(db).get_visible_by_slug(slug=thread.agent_id, user=user)
        if agent is None:
            raise AgentExecutionRevoked("Agent 使用权限已撤销")
    context.agent_slug = agent.slug
    return user, agent, run
