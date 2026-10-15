"""嵌套执行节点的外层共享文件队列约束。"""

import re

import pytest
from test.unit.config._shared import project_root


def _assert_shared_queue_configuration(source: str) -> None:
    """固定上游示例的显式队列配置。"""
    device = re.search(r"vhost-user-fs-pci,([^\s]+)", source)
    assert device is not None, "缺少外层 virtiofs 设备"
    queue = re.search(r"(?:^|,)queue-size=(\d+)(?:,|$)", device.group(1))
    assert queue is not None and int(queue.group(1)) == 1024, "外层 virtiofs 队列未使用上游示例配置"


def test_nested_node_has_explicit_shared_queue_configuration() -> None:
    """外层共享文件设备的队列必须显式覆盖 QEMU 默认值。"""
    _assert_shared_queue_configuration((project_root() / "docker/cube/run-vm.sh").read_text())


@pytest.mark.parametrize("queue", ["", "queue-size=128,"])
def test_queue_guard_rejects_default_or_small_queue(queue: str) -> None:
    """恢复缺失或默认队列时，配置约束必须失败。"""
    with pytest.raises(AssertionError, match="未使用上游示例配置"):
        _assert_shared_queue_configuration(f"-device vhost-user-fs-pci,{queue}chardev=fs,tag=yuxi_shared")
