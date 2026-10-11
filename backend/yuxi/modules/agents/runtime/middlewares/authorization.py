"""模型和工具执行边界重新读取身份与授权。"""

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from sqlalchemy import select

from yuxi.infrastructure.postgres.manager import pg_manager
from yuxi.modules.agents.models.runs import AgentRun
from yuxi.modules.agents.models.sessions import Session
from yuxi.modules.agents.repositories.definitions import AgentRepository
from yuxi.modules.agents.runtime.context import normalize_agent_context_config
from yuxi.modules.agents.services.event_writer import append_run_event_best_effort
from yuxi.modules.extensions.mcp.models import MCPServer
from yuxi.modules.extensions.skills.runtime import resolve_runtime_skills_for_context, sync_agent_context_skills
from yuxi.modules.identity.models import User


class AgentExecutionRevoked(PermissionError):
    """账号或 Agent 使用权撤销，必须使执行形成失败终态。"""


class RuntimeAuthorizationMiddleware(AgentMiddleware):
    """每个新模型和工具调用使用当前调用者权限。"""

    async def abefore_model(self, state, runtime):
        """模型轮次前收敛当前可用依赖。"""
        await refresh_execution_authorization(runtime.context)

    async def aafter_model(self, state, runtime):
        """模型返回后、审批或工具路由前复查账号与 Agent。"""
        await refresh_execution_authorization(runtime.context)

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
    if name == "mark_for_improvement":
        return bool(context.run_id)
    allowed_mcps = set(context.mcps)
    allowed_tools = set(context.tools)
    snapshot = context._skill_runtime_snapshot
    active = set(state.get("activated_skills", [])) | set(snapshot["preloaded_skills"])
    for slug in active & set(snapshot["effective_skills"]):
        allowed_tools.update(snapshot["runtime_skills"][slug]["tools"])
        allowed_mcps.update(snapshot["runtime_skills"][slug]["mcps"])
    server = getattr(context, "_mcp_tool_servers", {}).get(name)
    if server:
        return server in allowed_mcps and server in context._enabled_mcps and name not in context._enabled_mcps[server]
    return name not in getattr(context, "_registered_builtin_tool_names", set()) or name in allowed_tools


async def refresh_execution_authorization(context) -> None:
    """从持久 Run 绑定身份读取最新账号、Agent 和依赖授权。"""
    async with pg_manager.get_async_session_context() as db:
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
        resources = type(context).get_resource_fields()
        selections = getattr(context, "_resource_selections", {name: getattr(context, name) for name in resources})
        normalized = await normalize_agent_context_config(selections, db=db, user=user, context_schema=type(context))
        for name in resources:
            setattr(context, name, normalized[name])
        previous = getattr(context, "_skill_runtime_snapshot", {})
        current = await resolve_runtime_skills_for_context(context, db=db, user=user)
        # 每个执行边界重新授权；已经注入的专属根文本保持该 Run 准备时的快照。
        for slug, metadata in previous.get("skill_metadata", {}).items():
            if metadata.get("source_scope") == "agent_bound" and slug in current["preloaded_skill_contents"]:
                current["preloaded_skill_contents"][slug] = previous["preloaded_skill_contents"][slug]
        context._skill_runtime_snapshot = current
        rows = await db.execute(select(MCPServer.slug, MCPServer.disabled_tools).where(MCPServer.enabled == 1))
        context._enabled_mcps = {slug: set(disabled or []) for slug, disabled in rows}
        limited = any(
            isinstance(selections[name], list) and set(selections[name]) - set(normalized[name]) for name in resources
        ) or context._skill_runtime_snapshot.get(
            "capability_limited",
            False,
        )
        if limited and not getattr(context, "_capability_warning_sent", False) and run is not None:
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
    await sync_agent_context_skills(context)
