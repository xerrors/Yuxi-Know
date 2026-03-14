"""
MinIO Backend for Deep Agents

基于 S3_backend 适配的 MinIO 后端实现。
使用环境变量配置 MinIO 连接，专用于 Agent 状态存储。
"""

from __future__ import annotations

import os

from src.utils.S3_backend import S3Backend, S3Config

__all__ = ["MinIOBackend", "get_minio_backend"]


def get_minio_backend(runtime) -> MinIOBackend:
    thread_id = getattr(runtime, "config", {}).get("configurable", {}).get("thread_id")
    """获取 MinIO 后端实例（单例）"""
    return MinIOBackend(thread_id)


class MinIOBackend(S3Backend):
    """
    基于 S3Backend 的 MinIO 后端。

    使用环境变量配置：
        - MINIO_URI: MinIO 端点地址（默认: http://milvus-minio:9000）
        - MINIO_ACCESS_KEY: 访问密钥（默认: minioadmin）
        - MINIO_SECRET_KEY: 密钥（默认: minioadmin）

    默认配置：
        - bucket: "state-bucket"
        - prefix: "threads"
    """

    def __init__(self, thread_id: str) -> None:
        endpoint = os.getenv("MINIO_URI") or "http://milvus-minio:9000"
        access_key = os.getenv("MINIO_ACCESS_KEY") or "minioadmin"
        secret_key = os.getenv("MINIO_SECRET_KEY") or "minioadmin"
        

        # 从 endpoint 提取 region（MinIO 通常用 us-east-1）
        region = os.getenv("MINIO_REGION") or "us-east-1"

        config = S3Config(
            bucket="agent-state-bucket",
            prefix=f"threads/{thread_id}",
            region=region,
            endpoint_url=endpoint,
            access_key_id=access_key,
            secret_access_key=secret_key,
            use_ssl=endpoint.startswith("https://"),
            max_pool_connections=50,
            connect_timeout=5.0,
            read_timeout=30.0,
            max_retries=3,
        )
        super().__init__(config)