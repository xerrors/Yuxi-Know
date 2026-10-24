"""Knowledge MCP 适配留在业务模块，通用调用方只导入其公开入口。"""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[3] / "yuxi"
CALLERS = (
    "modules/agents/services/references.py",
    "modules/extensions/mcp/builtin.py",
    "modules/extensions/mcp/service.py",
    "modules/extensions/mcp/runtime.py",
    "modules/identity/security.py",
)


def assert_no_knowledge_adapter(source):
    """只检查已发生过的业务泄漏，不建立跨仓库规则或注册机制。"""
    tree = ast.parse(source)
    knowledge_literals = {
        "list_kbs",
        "query_kb",
        "search_file",
        "open_kb_document",
        "find_kb_document",
        "yuxi-knowledge-mcp",
        "agent-knowledge-read",
        "mcp_server_scopes",
    }
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            assert "knowledge" not in node.name.lower(), f"Knowledge 适配定义泄漏: {node.name}"
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert node.value not in knowledge_literals, f"Knowledge 协议字段泄漏: {node.value}"
        if isinstance(node, ast.Attribute):
            assert node.attr != "mcp_server_scopes", "Knowledge 选择被复制为额外 MCP scope"


@pytest.mark.parametrize("relative_path", CALLERS)
def test_knowledge_adapter_has_only_one_business_owner(relative_path):
    """当前通用调用方可以导入业务函数，不能实现知识工具或委托协议。"""
    assert_no_knowledge_adapter((PACKAGE / relative_path).read_text())


@pytest.mark.parametrize(
    "source,reason",
    [
        ("def _knowledge_sources(payload, tool_name, kb_id):\n    return []\n", "适配定义泄漏"),
        ("REFERENCE_TOOLS = {'query_kb', 'open_kb_document'}\n", "协议字段泄漏"),
        ("KNOWLEDGE_MCP_AUDIENCE = 'yuxi-knowledge-mcp'\n", "协议字段泄漏"),
        ("context.mcp_server_scopes['knowledge'] = {'knowledges': context.knowledges}\n", "额外 MCP scope"),
    ],
)
def test_boundary_rejects_previous_adapter_shapes(source, reason):
    """恢复上一版实际适配形态后，同一边界校验必须因具体违规失败。"""
    with pytest.raises(AssertionError, match=reason):
        assert_no_knowledge_adapter(source)


def test_imported_knowledge_functions_are_allowed():
    """公开导入和函数调用属于允许的模块协作。"""
    assert_no_knowledge_adapter(
        "from yuxi.modules.knowledge.mcp.references import knowledge_reference_sources\n"
        "sources = knowledge_reference_sources(payload, tool_name, resource_id)\n"
    )


def test_obsolete_knowledge_adapter_locations_are_removed():
    """旧目录不能继续拥有第二条客户端或协议实现。"""
    for relative_path in (
        "modules/extensions/tools/knowledge",
        "modules/extensions/mcp/integrations/knowledge.py",
        "modules/extensions/mcp/delegation.py",
        "modules/identity/services/knowledge_delegation.py",
    ):
        path = PACKAGE / relative_path
        assert not path.is_file() and not (path.is_dir() and any(path.glob("*.py"))), relative_path
    context = ast.parse((PACKAGE / "modules/agents/runtime/context.py").read_text())
    assert not any(isinstance(node, ast.Name) and node.id == "mcp_server_scopes" for node in ast.walk(context))
