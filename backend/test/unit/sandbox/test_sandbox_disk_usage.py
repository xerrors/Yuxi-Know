"""磁盘用量边界拒绝失败输出，不把未知空间显示为零。"""

import pytest

from yuxi.modules.agents.runtime.sandbox.provider import CubeSandboxProvider
from yuxi.shared.errors import UpstreamError


def test_disk_usage_keeps_available_space_distinct_from_reserved_space(monkeypatch):
    """保留文件系统返回的可用空间，不用总量减已用伪造它。"""
    provider = CubeSandboxProvider()
    monkeypatch.setattr(provider, "execute", lambda *args, **kwargs: ("1000 300 600\n", 0, False))
    assert provider.disk_usage("fixture") == {"used_bytes": 300, "available_bytes": 600}


@pytest.mark.parametrize(
    "result",
    [
        ("1000 300 600", 1, False),
        ("1000 300 600", 0, True),
        ("", 0, False),
        ("1000 300", 0, False),
        ("1000 300 600 unexpected", 0, False),
        ("1000 unknown 600", 0, False),
        ("0 0 0", 0, False),
        ("1000 -1 600", 0, False),
        ("1000 300 -1", 0, False),
        ("1000 300 800", 0, False),
    ],
)
def test_disk_usage_rejects_failed_or_invalid_results(monkeypatch, result):
    """非法计数和命令失败必须拒绝，不能提供假用量。"""
    provider = CubeSandboxProvider()
    monkeypatch.setattr(provider, "execute", lambda *args, **kwargs: result)
    with pytest.raises(UpstreamError, match="磁盘用量读取失败"):
        provider.disk_usage("fixture")
