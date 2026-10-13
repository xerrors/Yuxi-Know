"""ARQ 消费心跳契约与轻量 Compose 健康检查。"""

import sys

from yuxi.infrastructure.redis import RedisConfig, sync_redis_client
from yuxi.infrastructure.worker_health import WORKER_HEALTH_KEY, WORKER_HEALTH_MAX_TTL_MS


def main() -> int:
    """读取有界心跳租约，失败时仅输出错误类型以避免泄露连接凭据。"""
    try:
        config = RedisConfig.from_env(socket_timeout=2, socket_connect_timeout=2)
        with sync_redis_client(config, ping=False) as client:
            with client.pipeline() as pipeline:
                pipeline.get(WORKER_HEALTH_KEY)
                pipeline.pttl(WORKER_HEALTH_KEY)
                value, ttl_ms = pipeline.execute()
        if not value or not 0 < ttl_ms <= WORKER_HEALTH_MAX_TTL_MS:
            print("worker health lease missing or invalid", file=sys.stderr)
            return 1
    except Exception as exc:
        print(f"worker health check failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
