"""实际压测入口须保持当前 worker 装配与注册语义。"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


@pytest.mark.parametrize("fine_timing", ["0", "1"])
def test_probe_assembles_shipping_worker_without_losing_registration(fine_timing):
    """独立进程安装真实探针，保留 Agent 与后台作业的 ARQ 注册策略。"""
    script = textwrap.dedent(
        """
        from dataclasses import fields
        import yuxi.workers.arq as arq_entry
        from yuxi.workers.settings import WorkerSettings
        from test.performance import probe

        original = WorkerSettings.functions[0]
        other_functions = WorkerSettings.functions[1:]
        original_startup = WorkerSettings.on_startup
        calls = []
        arq_entry.run_worker = calls.append
        probe.run()

        assert calls == [WorkerSettings]
        registered = WorkerSettings.functions[0]
        assert registered.coroutine.__wrapped__ is original.coroutine
        for field in fields(original):
            if field.name != 'coroutine':
                assert getattr(registered, field.name) == getattr(original, field.name), field.name
        assert WorkerSettings.functions[1:] == other_functions
        assert WorkerSettings.on_startup is not original_startup
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[3],
        env=os.environ | {"MATRIX_FINE_TIMING": fine_timing},
        text=True,
        capture_output=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr
