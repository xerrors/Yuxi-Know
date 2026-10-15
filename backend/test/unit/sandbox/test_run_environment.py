"""Run 快照与独立操作的环境变量边界。"""

import asyncio
import base64
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from yuxi.modules.agents.runtime.sandbox.cube import Environment
from yuxi.modules.agents.runtime.sandbox.provider import CubeSandboxProvider, sandbox_run_env


@pytest.fixture
def provider(monkeypatch):
    """用执行协议输出实际收到的环境，其他生命周期保持最小替身。"""

    @contextmanager
    def user_lock(uid):
        """环境领取不连接数据库。"""
        yield None

    def stream(environment, command, cwd, command_id, envs, **kwargs):
        """协议输出可独立比对的配置，而非只记录调用次数。"""
        yield {"data": {"stdout": base64.b64encode(json.dumps(envs).encode()).decode()}}
        yield {"end": {"exitCode": 0}}

    repository = SimpleNamespace(user_lock=user_lock, environment=lambda *args: {"generation": 1}, finish_command=lambda *args: None)
    adapter = SimpleNamespace(stream=stream, cancel=lambda *args, **kwargs: None)
    value = CubeSandboxProvider(adapter=adapter, repository=repository)
    monkeypatch.setattr(value, "_ensure", lambda *args: Environment("fixture", "", ""))
    monkeypatch.setattr(value, "_add_command", lambda *args: None)
    return value


@pytest.mark.parametrize("env", [{}, {"RUN_VALUE": "original"}])
async def test_parallel_run_commands_use_snapshot_including_empty_configuration(provider, monkeypatch, env):
    """空配置也必须固定，线程和并发 Run 不能串用或重新查询配置。"""

    def unexpected_read(uid):
        """恢复逐命令读库时，测试必须在正确原因上失败。"""
        raise AssertionError("Run command must not read current configuration")

    monkeypatch.setattr("yuxi.modules.agents.runtime.sandbox.provider.AgentEnvRepository.load_for_sync_runtime", unexpected_read)

    async def execute(snapshot):
        """每个并发执行拥有独立上下文。"""
        token = sandbox_run_env.set(snapshot)
        try:
            results = await asyncio.gather(*(asyncio.to_thread(provider.execute, "fixture", "print-env", "/", 10) for _ in range(2)))
            return [json.loads(result[0]) for result in results]
        finally:
            sandbox_run_env.reset(token)

    assert await asyncio.gather(execute(env), execute({"RUN_VALUE": "other"})) == [
        [env, env],
        [{"RUN_VALUE": "other"}, {"RUN_VALUE": "other"}],
    ]
    assert sandbox_run_env.get() is None


def test_standalone_operations_read_latest_while_file_processes_have_clean_environment(provider, monkeypatch):
    """独立验证读取新值，文件进程不继承用户配置。"""
    current = {"RUN_VALUE": "before"}
    monkeypatch.setattr("yuxi.modules.agents.runtime.sandbox.provider.AgentEnvRepository.load_for_sync_runtime", lambda uid: dict(current))
    assert json.loads(provider.execute("fixture", "print-env", "/", 10)[0]) == current
    current["RUN_VALUE"] = "after"
    assert json.loads(provider.execute("fixture", "print-env", "/", 10)[0]) == current
    token = sandbox_run_env.set(current)
    try:
        assert json.loads(provider.execute("fixture", "print-env", "/", 10, python=True)[0]) == {}
    finally:
        sandbox_run_env.reset(token)
