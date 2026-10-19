"""通过实际文件日志格式验证依赖故障可见性。"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.infrastructure.observability import logging as logging_module
from yuxi.modules.extensions.mcp import runtime as mcp_runtime
from yuxi.modules.extensions.web import services as web_services
from yuxi.modules.models.providers import cache as cache_module

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("component", "expected_fields"),
    [
        ("web_search", ["reason=credentials_missing"]),
        ("model_cache", ["error_type=ConnectionError"]),
        ("mcp", ["server_slug=fixture-unavailable", "error_type=ConnectionError"]),
    ],
)
async def test_dependency_failure_fields_reach_shipping_file_log(monkeypatch, tmp_path, component, expected_fields):
    """实际日志文件保留组件、故障原因及不可用状态。"""
    log_file = tmp_path / "dependency-failure.log"
    try:
        with monkeypatch.context() as logging_patch:
            logging_patch.setattr(logging_module, "LOG_DIR", tmp_path)
            logging_patch.setattr(logging_module, "LOG_FILE", str(log_file))
            logging_module.setup_logger("audit-test", console=False)

            if component == "web_search":
                monkeypatch.setattr(
                    web_services, "get_web_configuration", AsyncMock(return_value={"search": None, "fetch": None, "keys": {}})
                )
                assert await web_services.available_web_tools() == set()
            elif component == "model_cache":

                @contextmanager
                def refused_redis():
                    """在真实缓存读取边界注入连接失败。"""
                    raise ConnectionError("fixture-credential-must-not-appear")
                    yield

                monkeypatch.setattr(cache_module, "sync_redis_client", refused_redis)
                with pytest.raises(RuntimeError, match="模型缓存不可用"):
                    cache_module.ModelCache().get_all_specs()
            else:
                client = SimpleNamespace(get_tools=AsyncMock(side_effect=ConnectionError("fixture-credential-must-not-appear")))
                monkeypatch.setattr(mcp_runtime, "get_mcp_client", AsyncMock(return_value=client))
                with pytest.raises(RuntimeError, match="MCP.*失败"):
                    await mcp_runtime.get_mcp_tools(
                        "fixture-unavailable",
                        {"transport": "streamable_http", "url": "https://example.com/mcp"},
                    )

            logging_module.logger.complete()
            output = log_file.read_text(encoding="utf-8")
            assert f"component={component}" in output
            assert "available=false" in output
            assert all(field in output for field in expected_fields)
            assert "fixture-credential-must-not-appear" not in output
    finally:
        logging_module.setup_logger("Yuxi")
