"""Agent 知识工具的 MCP 边界、会话范围。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.modules.extensions.tools.knowledge import tools
from yuxi.modules.extensions.tools.knowledge.client import INTERNAL_KNOWLEDGE_MCP, KnowledgeMCPError, KnowledgeMCPUnavailable

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("selection", ["all", [], ["kb-selected"]])
@pytest.mark.parametrize(
    "name,arguments",
    [
        ("list_kbs", {"dummy": "ignored"}),
        ("query_kb", {"kb_id": "kb-selected", "query_text": "needle"}),
        ("open_kb_document", {"kb_id": "kb-selected", "file_id": "file", "offset": 12}),
        ("find_kb_document", {"kb_id": "kb-selected", "file_id": "file", "patterns": ["needle"]}),
        ("search_file", {"kb_id": "kb-selected", "offset": 300}),
    ],
)
async def test_tools_delegate_trusted_identity_and_selection_without_changing_results(monkeypatch, name, arguments, selection):
    """模型参数不拥有身份；显式空选择仍按空集合发送。"""
    expected = [{"kb_id": "kb-selected"}] if name == "list_kbs" else {"results": [{"content": "evidence", "file_id": "file"}]}
    remote = AsyncMock(return_value=expected)
    monkeypatch.setattr(tools, "call_knowledge_mcp", remote)
    runtime = SimpleNamespace(context=SimpleNamespace(uid="real-user", knowledges=selection, run_id="run"))
    result = await getattr(tools, name).coroutine(**arguments, runtime=runtime)
    assert result == expected
    actual_name, wire_arguments = remote.call_args.args
    assert actual_name == name
    assert remote.call_args.kwargs == {"uid": "real-user", "selection": selection, "run_id": "run"}
    assert "uid" not in wire_arguments and "selection" not in wire_arguments


async def test_unavailable_mcp_marks_existing_capability_failure_and_raises_safe_tool_error(monkeypatch):
    """离线服务产生失败状态而非空结果或本地查询。"""
    monkeypatch.setattr(tools, "call_knowledge_mcp", AsyncMock(side_effect=KnowledgeMCPUnavailable("知识库 MCP 不可用")))
    runtime = SimpleNamespace(context=SimpleNamespace(uid="user", knowledges="all", mcp_unavailable={}))
    with pytest.raises(KnowledgeMCPError, match="不可用"):
        await tools.query_kb.coroutine(kb_id="kb", query_text="q", runtime=runtime)
    assert runtime.context.mcp_unavailable == {INTERNAL_KNOWLEDGE_MCP: "知识库 MCP 不可用"}


async def test_internal_success_cannot_clear_same_named_external_mcp_failure(monkeypatch):
    """平台知识能力恢复不能清除用户自建 knowledge 服务的真实故障。"""
    monkeypatch.setattr(tools, "call_knowledge_mcp", AsyncMock(return_value={"results": []}))
    runtime = SimpleNamespace(
        context=SimpleNamespace(
            uid="u",
            knowledges=[],
            mcp_unavailable={
                "knowledge": "外部服务失联",
                INTERNAL_KNOWLEDGE_MCP: "内部服务失联",
            },
        )
    )
    assert await tools.query_kb.coroutine(kb_id="kb", query_text="q", runtime=runtime) == {"results": []}
    assert runtime.context.mcp_unavailable == {"knowledge": "外部服务失联"}


async def test_internal_failure_does_not_disable_same_named_external_mcp(monkeypatch):
    """内部故障标识进入真实运行策略后，合法同名外部服务仍可调用。"""
    from contextlib import asynccontextmanager

    from yuxi.modules.agents.runtime.middlewares import authorization

    monkeypatch.setattr(tools, "call_knowledge_mcp", AsyncMock(side_effect=KnowledgeMCPUnavailable("内部服务失联")))
    context = SimpleNamespace(uid="u", knowledges=[], mcps=["knowledge"], mcp_unavailable={}, skill_runtime_snapshot=None)
    with pytest.raises(KnowledgeMCPUnavailable):
        await tools.query_kb.coroutine(kb_id="kb", query_text="q", runtime=SimpleNamespace(context=context))
    assert context.mcp_unavailable == {INTERNAL_KNOWLEDGE_MCP: "内部服务失联"}

    @asynccontextmanager
    async def session():
        """隔离数据库，只保留运行策略的真实故障过滤逻辑。"""
        yield object()

    monkeypatch.setattr(authorization.pg_manager, "get_async_session_context", session)
    monkeypatch.setattr(authorization, "_require_execution_actor", AsyncMock(return_value=(SimpleNamespace(id=1), None, None)))
    monkeypatch.setattr(authorization, "refresh_agent_context_resources", AsyncMock())
    monkeypatch.setattr(authorization, "available_mcp_servers", AsyncMock(return_value={"knowledge": SimpleNamespace(disabled_tools=[])}))
    assert await authorization._refresh_execution_resources(context) == {"knowledge": set()}
