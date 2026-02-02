"""自定义文件系统后端模块"""

from src.agents.common.backends.minio_backend import MinIOBackend, init_attachment_bucket

__all__ = ["MinIOBackend", "init_attachment_bucket"]
