"""知识库节点名称及导入路径的统一边界。"""

import os
import unicodedata

from yuxi.shared.errors import InvalidInputError

MAX_NAME_LENGTH = 512
MAX_IMPORT_ITEMS = 500
MAX_DIRECTORY_DEPTH = 32


def normalize_name(value: str) -> str:
    """保留展示大小写；比较键由 PostgreSQL NFC/lower 表达式拥有。"""
    if not isinstance(value, str):
        raise InvalidInputError("名称必须为字符串")
    name = unicodedata.normalize("NFC", value.strip(" "))
    if not name or name in {".", ".."} or any(c in "/\\" or unicodedata.category(c) == "Cc" for c in name):
        raise InvalidInputError("名称不能为空、点目录或包含分隔符与控制字符")
    if len(name) > MAX_NAME_LENGTH:
        raise InvalidInputError("名称不能超过 512 个字符")
    return name


def source_segments(value: str) -> list[str]:
    """严格解析相对来源路径，不静默修正非法段或跳出目标目录。"""
    if not isinstance(value, str):
        raise InvalidInputError("来源路径必须为字符串")
    value = value.replace("\\", "/")
    if value.startswith("/") or (len(value) > 1 and value[1] == ":"):
        raise InvalidInputError("来源路径必须为相对路径")
    segments = [normalize_name(part) for part in value.split("/")]
    if len(segments) > MAX_DIRECTORY_DEPTH or len(value) > 4096:
        raise InvalidInputError("来源路径过深或过长")
    return segments


def suffixed_name(name: str, number: int) -> str:
    """为叶子文件分配后缀，保留最后扩展名及数据库长度预算。"""
    stem, extension = os.path.splitext(name)
    suffix = f" ({number})"
    budget = MAX_NAME_LENGTH - len(extension) - len(suffix)
    if budget < 1:
        raise InvalidInputError("扩展名过长，无法分配冲突后缀")
    return f"{stem[:budget]}{suffix}{extension}"
