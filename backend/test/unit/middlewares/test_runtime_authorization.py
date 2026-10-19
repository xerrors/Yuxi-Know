"""已注册工具也必须符合最新授权与 Skill 激活状态。"""

from types import SimpleNamespace

import pytest

from yuxi.modules.agents.runtime.middlewares.authorization import tool_allowed


@pytest.fixture
def context():
    """构图时注册工具、执行时权限独立变化的 Context。"""
    return SimpleNamespace(
        tools=[],
        mcps=[],
        registered_builtin_tool_names={"skill_tool"},
        mcp_tool_servers={"remote_tool": "remote"},
        skill_runtime_snapshot={
            "effective_skills": ["skill"],
            "preloaded_skills": [],
            "runtime_skills": {"skill": {"tools": ["skill_tool"], "mcps": ["remote"]}},
        },
    )


@pytest.fixture
def mcp_policy():
    """本次 service 查询结果只在当前调用内传递。"""
    return {"remote": set()}


def test_unactivated_skill_cannot_execute_registered_local_or_mcp_dependency(context, mcp_policy):
    """直接调用隐藏工具不能代替读取或预加载 Skill。"""
    assert not tool_allowed(context, "skill_tool", {}, mcp_policy)
    assert not tool_allowed(context, "remote_tool", {}, mcp_policy)
    assert tool_allowed(context, "skill_tool", {"activated_skills": ["skill"]}, mcp_policy)
    context.skill_runtime_snapshot["effective_skills"] = []
    assert not tool_allowed(context, "skill_tool", {"activated_skills": ["skill"]}, mcp_policy)


def test_mcp_single_tool_or_server_disable_rejects_old_registration(context, mcp_policy):
    """启停服务器和单工具都不能被既有对象绕过。"""
    state = {"activated_skills": ["skill"]}
    assert tool_allowed(context, "remote_tool", state, mcp_policy)
    mcp_policy["remote"] = {"remote_tool"}
    assert not tool_allowed(context, "remote_tool", state, mcp_policy)
    mcp_policy.clear()
    assert not tool_allowed(context, "remote_tool", state, mcp_policy)


def test_direct_mcp_disconnect_rejects_registered_tool_before_outbound(context, mcp_policy):
    """直接配置的旧工具也复用本轮连接查询，断开后不能继续出站。"""
    context.mcps = ["remote"]
    mcp_policy = {}
    assert not tool_allowed(context, "remote_tool", {}, mcp_policy)


@pytest.mark.parametrize("name", ["ask_user_question", "mark_for_improvement"])
def test_base_tool_is_allowed_without_configuration_skill_or_run(context, mcp_policy, name):
    """基础工具使用统一白名单，不依赖配置、Skill 或 Run 是否存在。"""
    context.registered_builtin_tool_names.add(name)
    assert tool_allowed(context, name, {}, mcp_policy)
    context.mcp_tool_servers[name] = "remote"
    assert not tool_allowed(context, name, {}, mcp_policy)


@pytest.mark.asyncio
async def test_network_retry_rechecks_before_each_model_request(monkeypatch, context):
    """网络失败同时撤权后，不得发送第二个实际模型请求。"""
    from langchain.agents import create_agent
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from yuxi.modules.agents.runtime.middlewares import authorization
    from yuxi.modules.agents.runtime.middlewares.network_retry import NetworkRetryMiddleware

    requests = []
    revoked = False

    class ReplayModel(BaseChatModel):
        """首次网络失败将身份置为撤权，独立记录真正的模型调用。"""

        @property
        def _llm_type(self):
            """返回本地测试模型类型。"""
            return "authorization-retry"

        def _generate(self, *args, **kwargs):
            """本测试只使用真实异步图。"""
            raise NotImplementedError

        async def _agenerate(self, *args, **kwargs):
            """记录请求后模拟连接失败。"""
            nonlocal revoked
            requests.append(revoked)
            if len(requests) == 1:
                revoked = True
                raise ConnectionError("network interrupted")
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="forbidden"))])

    async def check(_context, **_kwargs):
        """授权 oracle 与模型请求记录独立。"""
        if revoked:
            raise authorization.AgentExecutionRevoked("revoked")
        return {}

    monkeypatch.setattr(authorization, "refresh_execution_authorization", check)
    monkeypatch.setattr(authorization, "_refresh_execution_resources", check)
    graph = create_agent(
        model=ReplayModel(),
        middleware=[
            NetworkRetryMiddleware(max_retries=0, network_initial_delay=0.001, network_budget_seconds=1),
            authorization.RuntimeAuthorizationMiddleware(),
        ],
    )
    with pytest.raises(authorization.AgentExecutionRevoked):
        await graph.ainvoke({"messages": [HumanMessage(content="test")]}, context=context)
    assert requests == [False]


@pytest.mark.asyncio
async def test_context_overflow_does_not_send_summary_after_revocation(monkeypatch, context):
    """上下文溢出期间撤权后，独立摘要模型也不能发送新请求。"""
    from deepagents.backends import CompositeBackend
    from deepagents.backends.protocol import WriteResult
    from langchain.agents import create_agent
    from langchain_core.exceptions import ContextOverflowError
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from yuxi.modules.agents.runtime.middlewares import authorization, summary as summary_module

    requests, summaries = [], []
    revoked = False

    class ReplayModel(BaseChatModel):
        """独立模拟撤权后的上下文溢出响应。"""

        @property
        def _llm_type(self):
            """返回测试模型类型。"""
            return "authorization-overflow"

        def _generate(self, *args, **kwargs):
            """本测试只使用异步执行。"""
            raise NotImplementedError

        async def _agenerate(self, *args, **kwargs):
            """首个请求失败并撤销权限。"""
            nonlocal revoked
            requests.append(revoked)
            if len(requests) == 1:
                revoked = True
                raise ContextOverflowError("context overflow after revocation")
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="forbidden"))])

    class SummaryModel:
        """独立记录摘要请求。"""

        _llm_type = "review-summary"
        profile = {"max_input_tokens": 128000}

        def _get_ls_params(self):
            """提供测试模型的 tracing 类型。"""
            return {"ls_provider": "openai"}

        def with_retry(self, **kwargs):
            """保持摘要构造器协议。"""
            return self

        async def ainvoke(self, *args, **kwargs):
            """记录实际摘要调用而不是中间件次数。"""
            summaries.append(revoked)
            return AIMessage(content="forbidden summary")

    class MemoryBackend:
        """提供摘要文件协议，隔离模型调用 oracle。"""

        async def awrite(self, path, content):
            """返回已写入协议结果。"""
            return WriteResult(path=path, error=None)

        async def adownload_files(self, paths):
            """测试历史不含已存在媒体。"""
            return [SimpleNamespace(content=None, error="file_not_found") for _ in paths]

    async def check(_context, **_kwargs):
        """模型返回后按当前事实拒绝授权。"""
        if revoked:
            raise authorization.AgentExecutionRevoked("revoked")
        return {}

    monkeypatch.setattr(authorization, "refresh_execution_authorization", check)
    monkeypatch.setattr(authorization, "_refresh_execution_resources", check)
    summary = summary_module.YuxiSummarizationMiddleware(
        model=SummaryModel(),
        backend=CompositeBackend(default=MemoryBackend(), routes={}, artifacts_root="/outputs"),
        trigger=("messages", 100),
        keep=("messages", 1),
        trim_tokens_to_summarize=None,
    )
    # 与 shipping factory 注入同一真实调用者 Context。
    summary.authorization_context = context
    graph = create_agent(model=ReplayModel(), middleware=[summary, authorization.RuntimeAuthorizationMiddleware()])
    with pytest.raises(authorization.AgentExecutionRevoked):
        await graph.ainvoke(
            {"messages": [HumanMessage(content="old"), AIMessage(content="old answer"), HumanMessage(content="now")]},
            context=context,
        )
    assert summaries == []
    assert requests == [False]
