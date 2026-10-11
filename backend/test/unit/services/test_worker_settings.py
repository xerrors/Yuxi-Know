from __future__ import annotations

import os
import subprocess
import sys

import pytest

import yuxi.modules.background_jobs.dispatch as job_service
import yuxi.workers.settings as worker_settings


def test_background_job_outer_timeout_tracks_configured_worker_default():
    durable_function = next(
        function
        for function in worker_settings.WorkerSettings.functions
        if getattr(function, "name", getattr(function, "__name__", None)) == "process_background_job"
    )

    assert durable_function.timeout_s == job_service.BACKGROUND_JOB_DEFAULT_TIMEOUT_SECONDS + 30


def test_worker_settings_max_jobs_uses_environment():
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("ARQ_MAX_JOBS", "50")

        assert worker_settings.worker_max_jobs() == 50


async def test_worker_polls_new_requests_within_interactive_latency_budget():
    """真实 ARQ 配置必须把空闲队列轮询等待限制在 50ms 内。"""
    from arq.worker import create_worker

    worker = create_worker(worker_settings.WorkerSettings, handle_signals=False)
    assert 0 < worker.poll_delay_s <= 0.05


def test_background_job_shipping_worker_accepts_default_above_24_hours():
    env = os.environ.copy()
    env["BACKGROUND_JOB_DEFAULT_TIMEOUT_SECONDS"] = "172800"
    script = """
from yuxi.workers.settings import WorkerSettings
from yuxi.modules.background_jobs.dispatch import resolve_job_timeout

durable = next(
    function
    for function in WorkerSettings.functions
    if getattr(function, "name", getattr(function, "__name__", None)) == "process_background_job"
)
assert resolve_job_timeout(None) == 172800
assert durable.timeout_s == 172830
"""

    completed = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, check=False)

    assert completed.returncode == 0, completed.stderr


def test_worker_settings_reject_invalid_redis_dsn_instead_of_using_arq_default():
    env = os.environ.copy()
    env["REDIS_URL"] = "http://configured-redis.invalid:6379/0"

    completed = subprocess.run(
        [sys.executable, "-c", "import yuxi.workers.settings"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "invalid DSN scheme" in completed.stderr


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "-inf"])
def test_background_job_worker_rejects_invalid_default_timeout_at_configuration(value):
    """无效执行预算在 worker 装配时失败，不能先进入 ready。"""
    env = os.environ.copy()
    env["BACKGROUND_JOB_DEFAULT_TIMEOUT_SECONDS"] = value
    result = subprocess.run(
        [sys.executable, "-c", "from yuxi.workers.settings import WorkerSettings"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "positive finite number of seconds" in result.stderr


def test_worker_settings_publish_short_ttl_versioned_health_contract():
    assert worker_settings.WorkerSettings.max_jobs == worker_settings.worker_max_jobs()
    assert worker_settings.WorkerSettings.health_check_key == "yuxi:worker:health:agent-run-v1"
    assert 0 < worker_settings.WorkerSettings.health_check_interval <= 10
