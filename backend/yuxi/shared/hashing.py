"""跨域稳定标识和哈希值生成工具。"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable


def hashstr(input_string: object, length: int | None = None, with_salt: bool = False, salt: str | None = None) -> str:
    """生成字符串的 SHA-256 哈希值，可选截断和加盐。"""
    try:
        encoded_string = str(input_string).encode("utf-8")
    except UnicodeEncodeError:
        encoded_string = str(input_string).encode("utf-8", errors="replace")

    if with_salt:
        if not salt:
            salt = f"{time.time()}_{uuid.uuid4().hex[:8]}"
        encoded_string = (encoded_string.decode("utf-8") + salt).encode("utf-8")

    digest = hashlib.sha256(encoded_string).hexdigest()
    if length:
        return digest[:length]
    return digest


def hash_id(prefix: str, value: object, length: int = 48) -> str:
    digest_length = max(0, length - len(prefix))
    digest = hashstr(value, length=digest_length) if digest_length else ""
    return f"{prefix}{digest}"


def json_intent_hash(value: object, *, default: Callable[[object], object] | None = None) -> str:
    """按既有规范 JSON 字节生成意图指纹，保留显式类型适配。"""
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=default)
    return hashlib.sha256(encoded.encode()).hexdigest()
