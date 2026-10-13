"""API 与 worker 共用的有界心跳协议；键值保持部署兼容。"""

import os

from yuxi.infrastructure.redis import get_async_redis_client

WORKER_HEALTH_CONTRACT = "agent-run-v1"
WORKER_HEALTH_KEY = f"yuxi:worker:health:{WORKER_HEALTH_CONTRACT}"
WORKER_HEALTH_INTERVAL_SECONDS = float(os.getenv("WORKER_HEALTH_INTERVAL_SECONDS", "5"))
if not 0 < WORKER_HEALTH_INTERVAL_SECONDS <= 10:
    raise ValueError("WORKER_HEALTH_INTERVAL_SECONDS 必须大于 0 且不超过 10")
WORKER_HEALTH_MAX_TTL_MS = int((WORKER_HEALTH_INTERVAL_SECONDS + 1) * 1000)
JOB_RECONCILIATION_SECONDS = 30.0
JOB_RECONCILIATION_HEALTH_KEY = "yuxi:worker:health:background-job-reconciliation-v1"
JOB_RECONCILIATION_HEALTH_TTL_SECONDS = int(JOB_RECONCILIATION_SECONDS * 2 + 5)

RUN_RECONCILIATION_SECONDS = 30
WORKER_RECONCILIATION_HEALTH_KEY = f"{WORKER_HEALTH_KEY}:lease-reconciliation"
WORKER_RECONCILIATION_HEALTH_TTL_SECONDS = RUN_RECONCILIATION_SECONDS * 2 + 5


async def publish_worker_health(key: str, worker_id: str, ttl_seconds: int) -> None:
    """按调用方指定的有界 TTL 续租 worker 能力事实。"""
    redis = await get_async_redis_client()
    await redis.set(key, worker_id, ex=ttl_seconds)
