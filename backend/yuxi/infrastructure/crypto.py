"""部署级持久凭据加密。"""

import os

from cryptography.fernet import Fernet


def get_encryption_cipher() -> Fernet:
    """读取持久部署密钥，不自动生成或回退到身份签名密钥。"""
    value = os.getenv("YUXI_ENCRYPTION_KEY", "")
    try:
        return Fernet(value.encode())
    except ValueError as exc:
        raise ValueError("YUXI_ENCRYPTION_KEY 必须配置为持久 Fernet 密钥") from exc
