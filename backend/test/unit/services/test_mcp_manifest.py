"""远程 MCP 清单的正向与拒绝边界。"""

import pytest

from yuxi.modules.extensions.mcp.builtin import BUILTIN_MCP_MANIFEST
from yuxi.modules.extensions.mcp.config import normalize_mcp_manifest_entry
from yuxi.modules.extensions.mcp import runtime


def test_builtin_manifest_normalizes_deepwiki_connection_and_display():
    config = normalize_mcp_manifest_entry("deepwiki-official", BUILTIN_MCP_MANIFEST["mcpServers"]["deepwiki-official"])
    assert config["transport"] == "streamable_http"
    assert config["url"] == "https://mcp.deepwiki.com/mcp"
    assert config["name"] == "DeepWiki"
    assert not {"icon", "tags"} & config.keys()
    assert not {"command", "args", "env", "extra_data"} & config.keys()


@pytest.mark.parametrize(
    "entry,reason",
    [
        ({"type": "stdio", "url": "https://example.com/mcp"}, "transport"),
        ({"type": "http", "command": "sh"}, "连接字段"),
        ({"type": "http", "env": {}}, "连接字段"),
        ({"type": "http", "args": []}, "连接字段"),
        ({"type": "http", "transport": "sse"}, "不一致"),
        ({"type": "http", "url": "file:///tmp/mcp"}, "HTTP URL"),
        ({"type": "http", "url": "https://example.com:bad/mcp"}, "HTTP URL"),
        ({"type": "http", "url": "https://example.com:65536/mcp"}, "HTTP URL"),
        ({"type": "http", "url": "https://exa mple.com/mcp"}, "HTTP URL"),
        ({"type": "http", "url": "https://example.com/\u0000mcp"}, "HTTP URL"),
        ({"type": "http", "url": "https://example.com", "headers": {"X": 1}}, "headers"),
        ({"type": "http", "url": "https://example.com", "timeout": 0}, "timeout"),
        ({"type": "http", "url": "https://example.com", "timeout": True}, "timeout"),
        ({"type": "http", "extra_data": {"command": "sh"}}, "extra_data"),
        ({"type": "http", "extra_data": None}, "extra_data"),
        ({"type": "http", "extra_data": {"icon": "📚"}}, "extra_data"),
        ({"type": "http", "extra_data": {"tags": ["docs"]}}, "extra_data"),
    ],
)
def test_manifest_rejects_invalid_remote_entry(entry, reason):
    with pytest.raises(ValueError, match=reason):
        normalize_mcp_manifest_entry("example", entry)


@pytest.mark.parametrize("field,value", [("command", "sh"), ("args", []), ("env", {})])
async def test_remote_runtime_rejects_process_fields_before_client(monkeypatch, field, value):
    def unexpected_client(*_args, **_kwargs):
        pytest.fail("进程字段到达客户端")

    monkeypatch.setattr(runtime, "MultiServerMCPClient", unexpected_client)
    config = {"transport": "streamable_http", "url": "https://example.com/mcp", field: value}
    with pytest.raises(ValueError, match="进程字段"):
        await runtime.get_mcp_client({"example": config})
    with pytest.raises(ValueError, match="进程字段"):
        await runtime.get_mcp_tools("example", config)
