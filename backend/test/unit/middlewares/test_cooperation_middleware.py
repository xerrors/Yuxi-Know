"""协作工具只接受直属成员名称，路径由执行身份生成。"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import SystemMessage
from pydantic import ValidationError

from yuxi.modules.agents.runtime.middlewares.cooperation import CooperationMiddleware

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_identity_prompt_uses_persisted_member_and_refreshes_for_new_run(monkeypatch):
    """身份来自持久成员，同 Run 复用，换 Run 后更新父子身份。"""
    from yuxi.modules.agents.runtime.middlewares import cooperation
    from yuxi.modules.agents.services.cooperation import SessionCooperationService

    @asynccontextmanager
    async def database():
        yield object()

    root = SimpleNamespace(
        thread_id="root-id",
        cooperation_name="root",
        cooperation_path="/root",
        parent_thread_id=None,
        tree_root_thread_id="root-id",
    )
    child = SimpleNamespace(
        thread_id="child-id",
        cooperation_name="researcher",
        cooperation_path="/root/researcher",
        parent_thread_id="root-id",
        tree_root_thread_id="root-id",
    )
    from yuxi.modules.agents.repositories.input import AgentInputRepository

    monkeypatch.setattr(
        AgentInputRepository, "input_ids_for_runs", AsyncMock(side_effect=[{"run-1": ["input-1"]}, {"run-2": ["input-2", "input-3"]}])
    )
    caller = AsyncMock(
        side_effect=[
            (SimpleNamespace(id="run-1", turn_id="turn-1", input_id="input-1"), root),
            (SimpleNamespace(id="run-2", turn_id="turn-2", input_id="input-2"), child),
        ]
    )
    monkeypatch.setattr(cooperation.pg_manager, "get_async_session_context", database)
    monkeypatch.setattr(SessionCooperationService, "caller", caller)
    context = SimpleNamespace(run_id="run-1", uid="user-id")
    request = SimpleNamespace(
        runtime=SimpleNamespace(context=context),
        system_message=SystemMessage(content="原始 Agent 指令"),
        override=lambda **values: SimpleNamespace(**values),
    )
    middleware = CooperationMiddleware()
    handler = AsyncMock()
    await middleware.awrap_model_call(request, handler)
    await middleware.awrap_model_call(request, handler)
    assert caller.await_count == 1
    first = "\n".join(block["text"] for block in handler.call_args.args[0].system_message.content)
    assert '"role": "根会话"' in first and '"session_id": "root-id"' in first
    assert "原始 Agent 指令" in first
    assert "@agent:<id>" in first
    assert "create_session 的 agent_id" in first
    assert "不要求无条件创建子会话" in first
    context.run_id = "run-2"
    await middleware.awrap_model_call(request, handler)
    second = "\n".join(block["text"] for block in handler.call_args.args[0].system_message.content)
    assert caller.await_count == 2
    assert '"role": "子会话"' in second
    assert '"name": "researcher"' in second and '"path": "/root/researcher"' in second
    assert '"parent_session_id": "root-id"' in second and '"run_id": "run-2"' in second
    assert '"run_id": "run-1"' not in second
    assert '"input_ids": ["input-2", "input-3"]' in second


@pytest.mark.asyncio
async def test_identity_lookup_failure_does_not_call_model(monkeypatch):
    """执行身份失效时保留来源错误，不调用模型或缓存伪造身份。"""
    from yuxi.modules.agents.runtime.middlewares import cooperation
    from yuxi.modules.agents.services.cooperation import SessionCooperationService

    @asynccontextmanager
    async def database():
        yield object()

    monkeypatch.setattr(cooperation.pg_manager, "get_async_session_context", database)
    monkeypatch.setattr(SessionCooperationService, "caller", AsyncMock(side_effect=ValueError("执行归属已失效")))
    request = SimpleNamespace(runtime=SimpleNamespace(context=SimpleNamespace(run_id="run-1", uid="user-id")))
    handler = AsyncMock()
    with pytest.raises(ValueError, match="执行归属已失效"):
        await CooperationMiddleware().awrap_model_call(request, handler)
    handler.assert_not_awaited()


def test_list_sessions_schema_has_no_pagination_arguments():
    """模型一次读取完整协作摘要，无需携带游标或页大小。"""
    tool = next(tool for tool in CooperationMiddleware().tools if tool.name == "list_sessions")
    assert tool.tool_call_schema.model_json_schema()["properties"] == {}


def test_agent_directory_schema_uses_persisted_execution_identity():
    """目录参数不能由模型指定用户或 APP 扩大范围。"""
    tool = next(tool for tool in CooperationMiddleware().tools if tool.name == "list_agents")
    assert tool.tool_call_schema.model_json_schema()["properties"] == {}


def test_create_session_schema_exposes_local_name_without_parent_or_path():
    """模型仅看到带局部名称约束的创建参数。"""
    tool = CooperationMiddleware().tools[0]
    schema = tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"name", "description", "agent_id"}
    assert set(schema["required"]) == {"name", "description"}
    assert schema["properties"]["agent_id"]["default"] is None
    name = schema["properties"]["name"]
    assert name["pattern"] == "^[A-Za-z0-9_-]+$"
    assert name["minLength"] == 1 and name["maxLength"] == 64
    assert "直属" in name["description"] and "路径" in name["description"]


@pytest.mark.parametrize("name", ["/root/aaa/bbb", "aaa/bbb", "/root/name", "../bbb", r"aaa\bbb", "", "a" * 65])
def test_create_session_tool_arguments_reject_paths(name):
    """路径与无效名称在工具参数边界被拒绝。"""
    tool = CooperationMiddleware().tools[0]
    with pytest.raises(ValidationError) as rejected:
        tool.tool_call_schema.model_validate({"name": name, "description": "完成独立工作"})
    assert any(error["loc"] == ("name",) for error in rejected.value.errors())


@pytest.mark.parametrize("name", ["aaa", "worker-1", "review_2", "a" * 64])
def test_create_session_tool_arguments_accept_local_names(name):
    """合法局部名称保留原值供服务生成路径。"""
    tool = CooperationMiddleware().tools[0]
    arguments = tool.tool_call_schema.model_validate({"name": name, "description": "完成独立工作"})
    assert arguments.name == name


@pytest.mark.asyncio
@pytest.mark.parametrize("known", [True, False])
async def test_create_session_exposes_only_owned_depth_denial_as_error_tool_result(monkeypatch, known):
    """有明确来源的深度拒绝可给模型，其他异常继续由通用保护层脱敏。"""
    from yuxi.modules.agents.runtime.middlewares import cooperation
    from yuxi.modules.agents.services.cooperation import SessionCooperationService
    from yuxi.shared.errors import InvalidOperationError

    @asynccontextmanager
    async def database():
        """隔离事务边界，不创建测试之外的持久资源。"""
        yield object()

    code = "cooperation_depth_exceeded" if known else "untrusted_failure"
    error = InvalidOperationError("协作深度 3 超过最大协作深度 2" if known else "PRIVATE_ERROR_DETAIL", code=code)
    monkeypatch.setattr(cooperation.pg_manager, "get_async_session_context", database)
    monkeypatch.setattr(SessionCooperationService, "create_session", AsyncMock(side_effect=error))
    runtime = SimpleNamespace(context=SimpleNamespace(run_id="run", uid="user", _cooperation_config_snapshot={}), tool_call_id="create")
    tool = next(tool for tool in CooperationMiddleware().tools if tool.name == "create_session")
    if known:
        result = await tool.coroutine(name="child", description="task", runtime=runtime)
        assert result.status == "error" and result.tool_call_id == "create"
        assert result.content == error.message
    else:
        with pytest.raises(InvalidOperationError) as rejected:
            await tool.coroutine(name="child", description="task", runtime=runtime)
        assert rejected.value is error
