"""
MinIO 存储模块
简化的对象存储功能
"""

# 导出核心功能
from .client import MinIOClient, StorageError, UploadResult, aupload_file_to_minio, get_minio_client
from .utils import generate_unique_filename, get_file_size

# 为了向后兼容，导出常用的函数
__all__ = [
    # 核心功能
    "MinIOClient",
    "get_minio_client",
    "aupload_file_to_minio",
    # 异常类
    "StorageError",
    "UploadResult",
    # 工具函数
    "get_file_size",
    "generate_unique_filename",
]
