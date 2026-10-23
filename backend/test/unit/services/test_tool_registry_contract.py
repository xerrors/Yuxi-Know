"""独立目录读取不会改变注册容器，动态注册立即可发现。"""

from types import SimpleNamespace

from yuxi.modules.extensions.tools import registry
from yuxi.modules.extensions.tools.catalog import get_tool_metadata


def test_registry_and_catalog_reads_do_not_expose_mutable_global_containers(monkeypatch):
    """修改读结果后再次读取，注册事实和嵌套元数据保持原值。"""
    monkeypatch.setattr(registry, "_all_tool_instances", [])
    monkeypatch.setattr(registry, "_extra_registry", {})
    first = SimpleNamespace(name="first", description="fixture", metadata={"nested": ["original"]}, args_schema=None)
    metadata = registry.ToolExtraMetadata(category="builtin", tags=["original"], display_name="First")
    registry.register_tool(first, metadata)
    assert get_tool_metadata()[0]["slug"] == "first"
    registry.get_all_tool_instances().clear()
    assert registry.get_all_tool_instances() == [first]
    registry.get_all_extra_metadata()["first"].tags.clear()
    registry.get_extra_metadata("first").tags.clear()
    metadata.tags.clear()
    view = get_tool_metadata()
    view[0]["tags"].clear()
    view[0]["metadata"]["nested"].clear()
    view.clear()
    assert registry.get_all_tool_instances() == [first]
    assert get_tool_metadata()[0]["tags"] == ["original"]
    assert get_tool_metadata()[0]["metadata"]["nested"] == ["original"]
    second = SimpleNamespace(name="second", description="fixture", metadata={}, args_schema=None)
    registry.register_tool(second, registry.ToolExtraMetadata(category="builtin"))
    assert [item["slug"] for item in get_tool_metadata()] == ["first", "second"]


def test_documented_knowledge_tool_collection_uses_registered_instances():
    """正式 Python 扩展入口继续返回五个已注册知识库工具。"""
    from yuxi.modules.extensions.tools.knowledge.tools import get_common_kb_tools

    tools = get_common_kb_tools()
    assert {tool.name for tool in tools} == {
        "list_kbs",
        "query_kb",
        "find_kb_document",
        "open_kb_document",
        "search_file",
    }
    registered = registry.get_all_tool_instances()
    assert all(any(tool is item for item in registered) for tool in tools)
