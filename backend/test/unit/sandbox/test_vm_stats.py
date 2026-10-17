"""验证实时 VM 计数只读取控制面，并在上游失败时明确拒绝。"""

from types import SimpleNamespace

from cubesandbox import Config
import httpx
import pytest

from test.unit.sandbox.test_cube_health import http_server
from yuxi.modules.agents.runtime.sandbox.cube import CubeAdapter
from yuxi.modules.agents.services import sandbox
from yuxi.shared.errors import UpstreamError


@pytest.mark.parametrize(
    "instances,expected",
    [
        ([], {"active_vms": 0, "total_vms": 0}),
        (
            [{"state": "running"}, {"state": "paused"}, {"state": "running"}, {"state": "creating"}],
            {"active_vms": 2, "total_vms": 4},
        ),
        ([{"state": "paused"}], {"active_vms": 0, "total_vms": 1}),
    ],
)
def test_vm_stats_count_all_instances_without_connect(instances, expected):
    """只提供列表 GET 的服务即可计数，休眠和过渡实例不算运行中。"""
    with http_server({"/v2/sandboxes": (200, instances)}) as port:
        adapter = CubeAdapter(Config(api_url=f"http://127.0.0.1:{port}"))
        assert adapter.vm_stats() == expected


@pytest.mark.parametrize("payload", [{}, [None], [{}], [{"state": None}]])
def test_vm_stats_reject_invalid_control_response(payload):
    """畸形响应不能变成零值或遗漏实例的成功计数。"""
    with http_server({"/v2/sandboxes": (200, payload)}) as port:
        adapter = CubeAdapter(Config(api_url=f"http://127.0.0.1:{port}"))
        with pytest.raises(ValueError, match="实例列表格式异常"):
            adapter.vm_stats()


@pytest.mark.asyncio
async def test_vm_stats_report_unavailable_instead_of_zero(monkeypatch):
    """上游错误穿过用例边界后保留不可用语义。"""
    with http_server({"/v2/sandboxes": (503, {})}) as port:
        adapter = CubeAdapter(Config(api_url=f"http://127.0.0.1:{port}"))
        monkeypatch.setattr(sandbox, "get_sandbox_provider", lambda: SimpleNamespace(adapter=adapter))
        with pytest.raises(UpstreamError, match="VM 统计暂不可用") as result:
            await sandbox.get_vm_stats()
        assert isinstance(result.value.__cause__, httpx.HTTPStatusError)
