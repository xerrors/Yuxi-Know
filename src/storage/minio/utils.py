"""
MinIO 存储工具函数
简化的存储操作辅助函数
"""

import os


def get_file_size(file_path: str) -> int:
    """获取文件大小"""
    return os.path.getsize(file_path)


def generate_unique_filename(original_name: str) -> str:
    """生成唯一的文件名"""
    import uuid

    name_parts = original_name.rsplit(".", 1)
    base_name = name_parts[0] if len(name_parts) == 2 else original_name
    extension = f".{name_parts[1]}" if len(name_parts) == 2 else ""
    return f"{base_name}_{uuid.uuid4().hex[:8]}{extension}"
