"""ARQ worker 的任务注册、并发配置与生命周期回调。"""

from __future__ import annotations

import os

from arq import cron
from arq.worker import func
from yuxi.bootstrap.worker import _worker_shutdown, _worker_startup
from yuxi.infrastructure.redis import get_arq_redis_settings
from yuxi.infrastructure.runtime_settings import get_int_env
from yuxi.infrastructure.worker_health import WORKER_HEALTH_INTERVAL_SECONDS, WORKER_HEALTH_KEY
from yuxi.modules.agents.services.runner import MAX_RUN_TRIES, process_agent_run
from yuxi.modules.background_jobs.dispatch import BACKGROUND_JOB_DEFAULT_TIMEOUT_SECONDS
from yuxi.modules.knowledge.services.background_jobs import process_knowledge_projections
from yuxi.workers.background_jobs import process_background_job


def worker_max_jobs() -> int:
    """读取单个 ARQ worker 的并发任务上限。"""
    return get_int_env("ARQ_MAX_JOBS", 10)


class WorkerSettings:
    """为 ARQ 提供 Yuxi 任务、并发和生命周期配置。"""

    functions = [
        func(process_agent_run, keep_result=0),
        func(process_background_job, timeout=BACKGROUND_JOB_DEFAULT_TIMEOUT_SECONDS + 30),
    ]
    cron_jobs = [cron(process_knowledge_projections, second={15, 45}, run_at_startup=True)]
    max_jobs = worker_max_jobs()
    # 交互请求避免继承 ARQ 默认的 500ms 空闲轮询等待。
    poll_delay = 0.05
    max_tries = MAX_RUN_TRIES
    retry_jobs = True
    # 单任务最长执行时间（秒），可配置：超长图谱构建/深度检索场景需调大，
    # 避免长任务被 arq 取消并误标为 cancelled。
    job_timeout = int(os.getenv("YUXI_JOB_TIMEOUT_SECONDS", "3600"))
    keep_result = 60
    health_check_interval = WORKER_HEALTH_INTERVAL_SECONDS
    health_check_key = WORKER_HEALTH_KEY
    on_startup = _worker_startup
    on_shutdown = _worker_shutdown
    redis_settings = get_arq_redis_settings()
